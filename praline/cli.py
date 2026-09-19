"""Praline command interface. Compiler semantics are delegated to the core API."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
from praline.doctor import detect
from praline.execution import core
from praline.execution.compile import compile_pair, source_hash
from praline.execution.validate import validate_pair
from praline.execution.benchmark import benchmark_pair
from praline.report.html import render_report


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def integers(text: str) -> list[int]:
    try:
        values = [int(v) for v in text.split(',')]
        if not values or any(v < 0 for v in values):
            raise ValueError
        return values
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use comma-separated nonnegative integers') from exc


def analysis_options(parser):
    parser.add_argument('--clang', default=os.environ.get('PRALINE_CLANG','clang'))
    parser.add_argument('--clang-arg', action='append', default=[])
    parser.add_argument('--extent', action='append', default=[])
    parser.add_argument('--assume-disjoint', action='append', default=[])


def configuration(args):
    extents, pairs = {}, []
    for text in args.extent:
        name, sep, value = text.partition('=')
        if not sep or not name.isidentifier() or not value:
            raise ValueError('Extent syntax is NAME=EXPR')
        extents[name] = value
    for text in args.assume_disjoint:
        pair = tuple(text.split(','))
        if len(pair) != 2 or any(not p.isidentifier() for p in pair) or pair[0] == pair[1]:
            raise ValueError('Disjoint syntax is A,B with distinct buffer names')
        pairs.append(pair)
    return dict(clang=args.clang, clang_args=args.clang_arg, extents=extents,
                assume_disjoint=pairs, timeout=args.timeout)


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def report_directory(root: Path):
    return render_report(load(root/'analysis.json'), root, validation=load(root/'validation.json'),
                         benchmark=load(root/'benchmark.json'),doctor=load(root/'doctor.json'))


def execution_stage(report, name, evidence, root):
    status = evidence['status']
    if status not in ('passed','failed','unavailable','measured'):
        status = 'failed'
    report[name] = dict(status=status, reason=evidence.get('reason'), results=evidence)
    report['artifacts'][name] = name+'.json'
    report['artifacts']['report'] = 'report.html'
    write_json(root/'analysis.json',report)


def analysis_run(args, transform=False):
    root = Path(args.out)
    input_path = Path(args.source).resolve()
    if any(input_path == (root/name).resolve() for name in ('analysis.json','generated.c','patch.diff','validation.json','benchmark.json','report.html','runtime.h')):
        raise ValueError('Run artifacts would overwrite input source; choose a different --out directory')
    root.mkdir(parents=True,exist_ok=True)
    previous = load(root/'analysis.json')
    if previous and previous['source']['sha256'] != source_hash(args.source):
        raise ValueError('Run directory contains a different/stale source; choose a new --out directory')
    report = core.analyze(args.source, **configuration(args))
    # New compiler work invalidates execution evidence from prior generations.
    for name in ('validation.json','benchmark.json','compilation.json','generated.c','patch.diff'):
        if (root/name).exists():
            (root/name).unlink()
    report['artifacts']['analysis'] = 'analysis.json'
    report['artifacts']['report'] = 'report.html'
    write_json(root/'analysis.json',report)
    if report['status'] == 'error':
        report_directory(root)
        print(json.dumps(report['errors']),file=sys.stderr)
        return 1
    if transform:
        try:
            result = core.transform(args.source,report,target=args.target,out=root)
        except Exception as exc:
            report['errors'].append({'code':getattr(exc,'code','TRANSFORMATION_ERROR'),'message':str(exc)})
            write_json(root/'analysis.json',report)
            report_directory(root)
            print(str(exc),file=sys.stderr)
            return 2
        report = result['report']
        report['artifacts']['analysis'] = 'analysis.json'
        report['artifacts']['report'] = 'report.html'
        write_json(root/'analysis.json',report)
        # Includes resolve relative to the original source directory on compile.
        # Keep an adapter header beside generated source for portable evidence.
        header = Path(args.source).resolve().parent/'runtime.h'
        if header.exists() and header.resolve() != (root/'runtime.h').resolve():
            shutil.copyfile(header,root/'runtime.h')
    report_directory(root)
    print(root/'report.html')
    return 0


def execution_run(args, benchmark=False):
    if not Path(args.source).is_file() or not Path(args.generated).is_file():
        raise ValueError('Both source and generated files must exist')
    if any(n > 4194304 for n in args.sizes):
        raise ValueError('Example execution adapter limits sizes to 4194304')
    if any(s > 4294967295 for s in args.seeds):
        raise ValueError('Seeds must fit unsigned 32-bit integers')
    threads = args.threads if benchmark else [args.threads]
    if any(t < 1 for t in threads):
        raise ValueError('Thread counts must be positive')
    root = Path(args.out)
    protected = {Path(args.source).resolve(),Path(args.generated).resolve()}
    if any((root/name).resolve() in protected for name in ('analysis.json','doctor.json','compilation.json','validation.json','benchmark.json','report.html')):
        raise ValueError('Execution artifacts would overwrite source; choose a different --out directory')
    root.mkdir(parents=True,exist_ok=True)
    report = load(root/'analysis.json')
    if report and report['source']['sha256'] != source_hash(args.source):
        raise ValueError('Run directory contains analysis for a different/stale source')
    if report is None:
        try:
            report = core.analyze(args.source, **configuration(args))
        except RuntimeError:
            report = None  # execution-only evidence never imitates compiler analysis
    if (root/'benchmark.json').exists():
        (root/'benchmark.json').unlink()
    if report:
        report['benchmark'] = dict(status='not_run', reason='New execution invalidates prior benchmark evidence', results=None)
        report['artifacts']['benchmark'] = None
    doctor = detect(args.cc, timeout=args.timeout)
    write_json(root/'doctor.json',doctor)
    compiled = compile_pair(args.source,args.generated,root/'bin',doctor,target=args.target,
                            timeout=args.timeout,extra_flags=args.cflag)
    write_json(root/'compilation.json',compiled)
    validation = None
    for count in threads:
        checked = validate_pair(compiled,sizes=args.sizes,seeds=args.seeds,threads=count,
                                target=args.target,timeout=args.timeout,numeric=args.numeric,
                                atol=args.atol,rtol=args.rtol,independent_reference=not args.no_reference)
        if validation is None:
            validation = checked
            validation['thread_counts'] = threads
        else:
            validation['cases'].extend(checked['cases'])
            if checked['status'] != 'passed':
                validation['status'] = checked['status']
    write_json(root/'validation.json',validation)
    if report:
        execution_stage(report,'validation',validation,root)
    result = validation
    if benchmark:
        result = benchmark_pair(compiled,validation,sizes=args.sizes,seeds=args.seeds,
                    thread_counts=threads,trials=args.trials,warmups=args.warmups,
                    target=args.target,timeout=args.timeout,environment=doctor['environment'])
        write_json(root/'benchmark.json',result)
        if report:
            execution_stage(report,'benchmark',result,root)
    report_directory(root)
    print(root/'report.html')
    return 0 if result['status'] in ('passed','measured') else 1


def demo(args):
    examples = Path(args.examples).resolve()
    root = Path(args.out)
    shared = dict(clang=args.clang,clang_arg=[],extent=[],assume_disjoint=[],timeout=args.timeout)
    original = examples/'helper_map.c'
    transform_args = argparse.Namespace(source=str(original),out=str(root/'map-cpu'),target='cpu',**shared)
    code = analysis_run(transform_args,True)
    if code:
        return code
    execute_args = argparse.Namespace(source=str(original),generated=str(root/'map-cpu/generated.c'),
        out=str(root/'map-cpu'),target='cpu',cc=args.cc,cflag=[],sizes=args.sizes,seeds=[1,7],
        threads=[1,2,4],trials=5,warmups=1,numeric='integer',atol=0,rtol=0,no_reference=False,**shared)
    code = execution_run(execute_args,True)
    for name in ('global_write','prefix_dependency','scatter_write','alias_unknown','unknown_call'):
        negative = argparse.Namespace(source=str(examples/(name+'.c')),out=str(root/name),**shared)
        code = max(code,analysis_run(negative))
    gpu_config = {**shared, 'extent':['input=n','output=n']}
    gpu_args = argparse.Namespace(source=str(original),out=str(root/'map-gpu'),target='gpu',**gpu_config)
    gpu_code = analysis_run(gpu_args,True)
    if gpu_code:
        print('GPU generation refused; see GPU report',file=sys.stderr)
    print('Demo evidence:',root)
    return code


def parser():
    p = argparse.ArgumentParser(prog='praline',description='Local compiler and execution evidence')
    sub = p.add_subparsers(dest='command',required=True)
    doctor = sub.add_parser('doctor')
    doctor.add_argument('--out')
    doctor.add_argument('--cc')
    doctor.add_argument('--timeout',type=float,default=30)
    for command in ('analyze','transform'):
        q = sub.add_parser(command)
        q.add_argument('source')
        q.add_argument('--out',required=True)
        q.add_argument('--timeout',type=float,default=30)
        analysis_options(q)
        if command == 'transform':
            q.add_argument('--target',choices=['cpu','gpu'],required=True)
    for command in ('validate','benchmark'):
        q = sub.add_parser(command)
        q.add_argument('source')
        q.add_argument('--generated',required=True)
        q.add_argument('--out',default='runs/execution')
        q.add_argument('--sizes',type=integers,default=[1024,65536,1048576])
        q.add_argument('--seeds',type=integers,default=[1,7])
        q.add_argument('--threads',type=integers if command == 'benchmark' else int,default=[1,2,4] if command == 'benchmark' else 2)
        q.add_argument('--target',choices=['cpu','gpu'],default='cpu')
        q.add_argument('--cc')
        q.add_argument('--cflag',action='append',default=[])
        q.add_argument('--timeout',type=float,default=30)
        q.add_argument('--numeric',choices=['integer','float'],default='integer')
        q.add_argument('--atol',type=float,default=0)
        q.add_argument('--rtol',type=float,default=0)
        q.add_argument('--no-reference',action='store_true',help='Disable independent reference mode for an external protocol adapter')
        analysis_options(q)
        if command == 'benchmark':
            q.add_argument('--trials',type=int,default=5)
            q.add_argument('--warmups',type=int,default=1)
    q = sub.add_parser('report')
    q.add_argument('run_dir')
    q = sub.add_parser('demo')
    q.add_argument('--out',default='runs/demo')
    q.add_argument('--examples',default='examples')
    q.add_argument('--sizes',type=integers,default=[0,1,1024,65536,1048576])
    q.add_argument('--clang',default='clang')
    q.add_argument('--cc')
    q.add_argument('--timeout',type=float,default=30)
    q = sub.add_parser('serve', help='Run the local browser interface')
    q.add_argument('--host', default='127.0.0.1')
    q.add_argument('--port', type=int, default=8000)
    q.add_argument('--no-open', action='store_true', help='Do not open a browser automatically')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if hasattr(args,'timeout') and (not math.isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError('Timeout must be positive')
        if args.command == 'doctor':
            result = detect(args.cc,timeout=args.timeout)
            if args.out:
                write_json(Path(args.out)/'doctor.json',result)
            print(json.dumps(result,indent=2))
            return 0 if result['status'] == 'ok' else 1
        if args.command in ('analyze','transform'):
            return analysis_run(args,args.command == 'transform')
        if args.command in ('validate','benchmark'):
            return execution_run(args,args.command == 'benchmark')
        if args.command == 'report':
            root = Path(args.run_dir)
            if not any((root/n).exists() for n in ('analysis.json','validation.json','doctor.json')):
                raise ValueError('No run evidence found')
            print(report_directory(root))
            return 0
        if args.command == 'serve':
            if not 0 <= args.port <= 65535:
                raise ValueError('Port must be between 0 and 65535')
            from praline.web import serve
            serve(args.host, args.port, open_browser=not args.no_open)
            return 0
        return demo(args)
    except ValueError as exc:
        print(str(exc),file=sys.stderr)
        return 2
    except (OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
