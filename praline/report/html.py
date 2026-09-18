"""Plain HTML rendering of the frozen compiler contract and execution evidence."""
from __future__ import annotations
import html
import json
from pathlib import Path


def escape(value) -> str:
    return html.escape(str(value))


def pretty(value) -> str:
    return '<pre>'+escape(json.dumps(value, indent=2, ensure_ascii=False))+'</pre>'


def table(headers, rows) -> str:
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(cell if cell is not None else '—')+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def badge(value) -> str:
    tone = value if value in ('safe', 'unsafe', 'unknown', 'passed', 'failed') else 'neutral'
    return '<span class="badge '+tone+'">'+escape(str(value).replace('_', ' '))+'</span>'


def code(text, start=1, diff=False) -> str:
    lines = str(text or 'Unavailable').splitlines()
    return '<pre class="code"><code>'+''.join(
        '<span class="code-line '+('added' if diff and line.startswith('+') else 'removed' if diff and line.startswith('-') else '')+'"><span class="line-number" aria-hidden="true">'+str(i)+'</span>'+escape(line.rstrip())+'\n</span>'
        for i, line in enumerate(lines, start))+'</code></pre>'


def reasons(items) -> str:
    return ''.join('<div class="reason"><code>'+escape(r.get('code', ''))+'</code><p>'+escape(r.get('message', ''))+'</p><small>Line '+escape((r.get('span') or {}).get('line', 'unavailable'))+' · '+escape(' → '.join(r.get('helper_chain', [])) or 'Direct analysis')+'</small></div>' for r in items) or '<p class="muted">No reasons recorded.</p>'


def effects(items) -> str:
    return table(['Access', 'Name', 'Index', 'Storage', 'Call path'], [(e.get('kind'), e.get('name'), e.get('index'), e.get('storage'), ' → '.join(e.get('helper_chain', []))) for e in items])


def render_report(report: dict | None, out: str | Path, *, validation=None,
                  benchmark=None, doctor=None) -> Path:
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    report = report or {}
    validation = validation or report.get('validation',{}).get('results')
    benchmark = benchmark or report.get('benchmark',{}).get('results')
    loops = report.get('loops', [])
    sections = ['<header><div class="eyebrow">PRALINE</div><h1>'+escape(Path(report.get('source', {}).get('path', 'Execution report')).name)+'</h1><p class="muted">Start with the loop decision, review the code, then check validation and timing.</p><div class="status-strip">'+''.join('<span>'+str(sum(l.get('decision') == state for l in loops))+' '+badge(state)+'</span>' for state in ('safe', 'unsafe', 'unknown'))+'<span>Validation '+badge((validation or {}).get('status', 'not run'))+'</span></div></header>']
    sections += ['<details class="metadata"><summary>Run details and files</summary>', table(['Field','Value'], [
        ('Run ID',report.get('run_id','Execution-only run; compiler core unavailable')),
        ('Timestamp',report.get('created_at', (benchmark or {}).get('timestamp','Unavailable'))),
        ('Static stage',report.get('status','Unavailable')),
        ('Source',report.get('source',{}).get('path','Unavailable')),
        ('Source SHA-256',report.get('source',{}).get('sha256','Unavailable'))])]
    links = [(name,name) for name in ('analysis.json','doctor.json','generated.c','patch.diff','validation.json','benchmark.json') if (root/name).is_file()]
    sections.append('<p>Raw evidence: '+ ' · '.join('<a href="'+escape(name)+'">'+escape(label)+'</a>' for name,label in links)+'</p></details>')
    sections += ['<section id="loops"><h2>Loop decisions</h2><p class="muted">Safe means independent under the recorded assumptions. Unsafe means a conflict was found. Unknown means independence could not be established.</p><div class="loop-index">'+''.join('<a href="#loop-'+str(i)+'">'+escape(l.get('function', 'Loop'))+' · line '+escape(l.get('span', {}).get('line', '—'))+' '+badge(l.get('decision', 'unknown'))+'</a>' for i,l in enumerate(loops))+'</div>']
    loops = report.get('loops',[])
    if not loops:
        sections.append('<p>No analyzed loop evidence is available.</p>')
    for i, loop in enumerate(loops):
        sections += ['<article id="loop-'+str(i)+'"><h3>'+escape(loop['function'])+' <small>line '+escape(loop.get('span', {}).get('line','—'))+' · '+escape(loop['id'])+'</small> '+badge(loop['decision'])+'</h3><div class="decision-grid"><div>'+code(loop.get('source',''), loop.get('span', {}).get('line',1))+'</div><div><h4>Why this decision?</h4>'+reasons(loop['reasons'])+'</div></div>',
                     '<h4>Assumptions and bounds</h4><ul>'+''.join('<li>'+escape(a)+'</li>' for a in loop.get('assumptions',[]))+'</ul><p>Trip count: <code>'+escape(loop.get('trip_count'))+'</code> · Eligible targets: '+escape(', '.join(loop.get('eligible_targets',[])) or 'None')+'</p>',
                     '<details><summary>Access effects and data mapping</summary>'+effects(loop.get('effects',[]))+table(['Buffer','Direction','Extent','Extent source'], [(m.get('name'),m.get('direction'),m.get('extent'),m.get('extent_source')) for m in loop.get('mappings',[])])+'</details>',
                     '<details><summary>What limits code generation?</summary>'+reasons(loop.get('generation_reasons',[]))+'</details><p class="muted">'+escape(loop.get('recommendation',{}).get('reason',''))+'</p></article>']
    sections += ['</section><section id="helpers"><h2>Helper effects</h2><p class="muted">Effect purity alone does not establish iteration independence.</p>']
    for function in report.get('functions',[]):
        span = function.get('span') or {}
        text = report.get('source',{}).get('text','')
        sections += ['<details><summary><code>'+escape(function['name'])+'</code> <span class="muted">'+('No impure or unknown effects recorded' if function['pure'] else 'Impure or unresolved effects')+'</span></summary>', code(text[span.get('start',0):span.get('end',0)],span.get('line',1)), effects(function.get('effects',[])), reasons(function.get('unknown_reasons',[])), '<details><summary>Raw function evidence</summary>'+pretty(function)+'</details></details>']
    sections += ['</section><section id="source"><h2>Source and generated code</h2><details open><summary>Original C source</summary>'+code(report.get('source',{}).get('text'))+'</details><details open><summary>Generated C source</summary>'+ (code((root/'generated.c').read_text()) if (root/'generated.c').is_file() else '<p>No generated source in this run.</p>')+'</details><h3>Target recommendation</h3>', '<p>'+escape(report.get('recommendation',{}).get('reason','No calibrated prediction is available'))+'</p>',
                 '<p>Effect purity alone does not establish iteration independence. Measured speedups below apply only to the recorded workload and environment.</p>']
    sections += ['<h2>Generated source diff</h2>']
    sections.append('<details open><summary>Patch diff</summary>'+code((root/'patch.diff').read_text(),diff=True)+'</details>' if (root/'patch.diff').exists() else '<p>Unavailable: transformation has not produced a patch.</p>')
    sections += ['</section><section id="validation"><h2>Whole-output validation</h2>']
    if validation:
        cases = validation['cases']
        sections += ['<p>'+badge(validation['status'])+' · '+str(sum(c.get('status') == 'passed' for c in cases))+' / '+str(len(cases))+' recorded cases passed. Tested equivalence is not a proof for arbitrary inputs.</p>',
                     '<p>Comparison mode: '+escape(validation['numeric'])+', atol='+escape(validation['atol'])+', rtol='+escape(validation['rtol'])+'</p>',
                     table(['Size','Seed','Threads','Result','Mismatched elements','Independent reference'],[(c['size'],c['seed'],c['threads'],c['status'],c.get('comparison',{}).get('mismatches','Unavailable'),c.get('reference_comparison',{}).get('status','Unavailable')) for c in validation['cases']])]
        if validation.get('reason'):
            sections.append('<p>'+escape(validation['reason'])+'</p>')
    else:
        sections.append('<p>Unavailable: validation has not run.</p>')
    sections += ['</section><section id="timing"><h2>Measured runtime</h2>']
    if benchmark:
        sections += ['<p>Benchmark status: '+badge(benchmark['status'])+'</p>', table(['Timing scope','What is included'],benchmark['timing_scope'].items()), '<p class="muted">Speedup is serial time / generated time. Below 1× means slower, not faster.</p>']
        rows = []
        for item in benchmark['measurements']:
            if item['status'] == 'measured':
                s,g = item['variants']['sequential'],item['variants']['generated']
                rows.append((item['size'],item['seed'],item['threads'],f"{s['kernel']['median_seconds']*1000:.6f}",f"{g['kernel']['median_seconds']*1000:.6f}",f"{g['kernel']['spread_seconds']*1000:.6f}",f"{item['kernel_speedup']:.3f}" if item['kernel_speedup'] is not None else 'Unavailable',f"{item['end_to_end_speedup']:.3f}" if item['end_to_end_speedup'] is not None else 'Unavailable'))
        sections.append(table(['Size','Seed','Threads','Serial kernel ms','Generated kernel ms','Generated spread ms','Kernel speedup','End-to-end speedup'],rows))
        missing = [item for item in benchmark['measurements'] if item['status'] != 'measured']
        if missing:
            sections.append(table(['Size','Seed','Threads','Status','Reason'], [(item.get('size'),item.get('seed'),item.get('threads'),item.get('status'),item.get('reason')) for item in missing]))
        sections.append('<p>Every trial, command, timer resolution and warmup is retained in benchmark.json. Timing spread is max minus min. Ratios at or below timer resolution are unavailable. Slowdowns are valid evidence.</p>')
        if benchmark.get('reason'):
            sections.append('<p>'+escape(benchmark['reason'])+'</p>')
    else:
        sections.append('<p>Unavailable: no timing measurements.</p>')
    gpu = report.get('gpu') or (doctor or {}).get('gpu') or {'status':'unavailable','reason':'No device evidence'}
    sections += ['</section><section id="gpu"><h2>GPU verification</h2><p>Generation and device execution are separate stages.</p><p>'+badge(gpu.get('status','unavailable'))+' · '+escape(gpu.get('reason') or 'No further device evidence recorded')+'</p>', table(['Evidence','Recorded result'], [('Device',gpu.get('device')),('Mandatory offload',gpu.get('mandatory_offload')),('Ran on initial / host device',gpu.get('is_initial_device'))]), '<details><summary>Raw GPU evidence</summary>'+pretty(gpu)+'</details>',
                 '<p>Host fallback does not count as GPU execution. GPU timing requires mandatory offload and evidence from the actual generated kernel.</p>',
                 '</section><section id="environment"><h2>Compiler and environment</h2><details><summary>Environment details</summary>',pretty({'compiler':report.get('compiler'), 'doctor':doctor}),'</details>',
                 '<h2>Errors and limitations</h2>',reasons(report.get('errors',[])) if report.get('errors') else '<p>No compiler errors recorded.</p>', '<ul>'+''.join('<li>'+escape(item)+'</li>' for item in report.get('limitations',[]))+'</ul>',
                 '</section>']
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Praline · '+escape(Path(report.get('source',{}).get('path','Report')).name)+'</title><style>'+STYLE+'</style><body><aside><a class="brand" href="#">Praline</a><p>REPORT</p><nav>'+''.join('<a href="#'+key+'">'+label+'</a>' for key,label in [('loops','Loop decisions'),('source','Source & code'),('validation','Validation'),('timing','Timing'),('helpers','Helper effects'),('gpu','GPU verification'),('environment','Run details')])+'</nav></aside><main>'+''.join(sections)+'</main></body></html>'
    destination = root/'report.html'
    destination.write_text(document)
    return destination


STYLE = '''
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:#fafbf9;color:#202c32;font:15px/1.6 Helvetica,Arial,sans-serif}aside{position:fixed;inset:0 auto 0 0;width:210px;padding:30px 22px;border-right:1px solid #dce2df;background:#f0f3ef}.brand{font-size:25px;font-weight:750;letter-spacing:-1px;text-decoration:none;color:#223c31}aside p,.eyebrow{font-size:11px;letter-spacing:1.8px;font-weight:700;color:#67766e}aside p{margin-top:40px}nav a{display:block;padding:9px 10px;margin:3px -10px;text-decoration:none;color:#46554e;border-radius:4px}nav a:nth-child(5){border-top:1px solid #dce2df;border-radius:0;margin-top:20px;padding-top:20px}nav a:hover,nav a:focus{background:#dfe7df;color:#163d2b}main{margin-left:210px;max-width:1510px;padding:36px 48px 80px}header{border-bottom:1px solid #dce2df;padding-bottom:24px}h1{font-size:34px;letter-spacing:-1px;margin:6px 0}h2{font-size:24px;letter-spacing:-.5px;margin:0 0 12px}h3{font-size:19px;margin:0 0 18px}h4{font-size:14px;margin:16px 0 8px}p{margin:8px 0 16px}small,.muted{color:#63716b}h3 small{font-size:12px;font-weight:400;margin:0 12px}a{color:#28644d}section{padding:30px 0;border-bottom:1px solid #dce2df}article{padding:24px 0;border-top:1px solid #dce2df}.badge{display:inline-block;font-size:12px;font-weight:650;border:1px solid #d4ddd7;padding:2px 9px;border-radius:4px;background:#edf0ed;color:#56665d;text-transform:capitalize}.safe,.passed{background:#e5f2e9;border-color:#bad9c5;color:#23633c}.unsafe,.failed{background:#faeae5;border-color:#eac6b8;color:#9a3e26}.unknown{background:#fcf2d9;border-color:#e5d5a5;color:#805e16}.status-strip{display:flex;gap:24px;flex-wrap:wrap;margin-top:22px}.status-strip .badge{margin-left:5px}.metadata{margin-top:20px}.loop-index{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.loop-index a{padding:8px 12px;border:1px solid #dce2df;text-decoration:none;background:white}.decision-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:26px}.decision-grid h4{margin-top:0}.reason{border-left:3px solid #c2cec4;padding:4px 16px;margin-bottom:16px}.reason code{font-size:11px;color:#51635a}.reason p{margin:5px 0;line-height:1.55}.reason small{font-size:12px}pre{background:#edf1ee;padding:18px;overflow:auto;font:12px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid #dce2df;border-radius:4px}.code{background:#18252a;color:#e5ece8;font-size:13px;white-space:pre;overflow-wrap:normal;padding:16px 0}.code-line{display:block;min-width:max-content;padding-right:20px}.line-number{display:inline-block;width:48px;text-align:right;padding-right:16px;color:#82968e;user-select:none}.added{background:#244638;color:#bde7cd}.removed{background:#4a302c;color:#f2c7b9}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #dce2df;vertical-align:top}th{background:#edf1ed;color:#52635a;font-size:11px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}.table-wrap{overflow:auto;margin:14px 0}details{margin:12px 0}summary{cursor:pointer;font-weight:600;padding:10px 0}summary .muted{font-weight:400;font-size:12px;margin-left:10px}li{margin:5px 0}:focus-visible{outline:2px solid #28644d;outline-offset:4px}@media(min-width:1700px){main{margin-right:auto;margin-left:230px}}@media(max-width:1000px){aside{width:175px;padding:24px 18px}main{margin-left:175px;padding:28px}.decision-grid{grid-template-columns:1fr}}@media(max-width:650px){aside{position:static;width:auto;border-right:0;border-bottom:1px solid #dce2df;padding:16px}aside p{display:none}nav{display:flex;flex-wrap:wrap;gap:10px}nav a{padding:3px;margin:0;font-size:12px}main{margin:0;padding:22px 16px}h1{font-size:28px}.status-strip{gap:12px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
'''
