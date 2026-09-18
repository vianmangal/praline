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
    return '<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(cell)+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table>'


def render_report(report: dict | None, out: str | Path, *, validation=None,
                  benchmark=None, doctor=None) -> Path:
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    report = report or {}
    validation = validation or report.get('validation',{}).get('results')
    benchmark = benchmark or report.get('benchmark',{}).get('results')
    sections = ['<h1>Praline evidence report</h1>', '<p>Recorded local run. Static analysis, generated code, tested equivalence, and measured performance are separate evidence stages.</p>']
    sections += ['<h2>Run and source</h2>', table(['Field','Value'], [
        ('Run ID',report.get('run_id','Execution-only run; compiler core unavailable')),
        ('Timestamp',report.get('created_at', (benchmark or {}).get('timestamp','Unavailable'))),
        ('Static stage',report.get('status','Unavailable')),
        ('Source',report.get('source',{}).get('path','Unavailable')),
        ('Source SHA-256',report.get('source',{}).get('sha256','Unavailable'))])]
    links = [(name,name) for name in ('analysis.json','doctor.json','generated.c','patch.diff','validation.json','benchmark.json') if (root/name).is_file()]
    sections.append('<p>Raw evidence: '+ ' · '.join('<a href="'+escape(name)+'">'+escape(label)+'</a>' for name,label in links)+'</p>')
    sections += ['<h2>Static loop decisions</h2>']
    loops = report.get('loops',[])
    if not loops:
        sections.append('<p>No analyzed loop evidence is available.</p>')
    for loop in loops:
        sections += ['<h3>'+escape(loop['id'])+' in '+escape(loop['function'])+': '+escape(loop['decision'])+'</h3>',
                     '<pre>'+escape(loop.get('source',''))+'</pre>',
                     table(['Code','Explanation','Source line','Helper chain'],[(r['code'],r['message'],(r.get('span') or {}).get('line','Unavailable'),' → '.join(r.get('helper_chain',[]))) for r in loop['reasons']]),
                     '<h4>Assumptions and bounds</h4>', pretty({'assumptions':loop.get('assumptions'), 'trip_count':loop.get('trip_count'), 'mappings':loop.get('mappings')}),
                     '<h4>Access effects</h4>', table(['Access','Buffer/declaration','Index','Storage','Helper chain'],[(e['kind'],e['name']+' / '+e['declaration_id'],e['index'],e['storage'],' → '.join(e['helper_chain'])) for e in loop.get('effects',[])]),
                     '<p>Target recommendation: '+escape(loop.get('recommendation',{}))+'</p>']
    sections += ['<h2>Helper effects</h2>']
    for function in report.get('functions',[]):
        sections += ['<details><summary>'+escape(function['name'])+' (effect purity: '+escape(function['pure'])+')</summary>',
                     pretty(function),'</details>']
    sections += ['<h2>Target policy</h2>', pretty(report.get('recommendation',{'target':'insufficient_evidence','reason':'No calibrated prediction is available'})),
                 '<p>Effect purity alone does not establish iteration independence. Measured speedups below apply only to the recorded workload and environment.</p>']
    sections += ['<h2>Generated source diff</h2>']
    sections.append('<pre>'+escape((root/'patch.diff').read_text())+'</pre>' if (root/'patch.diff').exists() else '<p>Unavailable: transformation has not produced a patch.</p>')
    sections += ['<h2>Whole-output validation</h2>']
    if validation:
        sections += ['<p>Execution status: '+escape(validation['status'])+'. Tested equivalence is not a proof for arbitrary inputs.</p>',
                     '<p>Comparison mode: '+escape(validation['numeric'])+', atol='+escape(validation['atol'])+', rtol='+escape(validation['rtol'])+'</p>',
                     table(['Size','Seed','Threads','Result','Mismatched elements','Independent reference'],[(c['size'],c['seed'],c['threads'],c['status'],c.get('comparison',{}).get('mismatches','Unavailable'),c.get('reference_comparison',{}).get('status','Unavailable')) for c in validation['cases']])]
        if validation.get('reason'):
            sections.append('<p>'+escape(validation['reason'])+'</p>')
    else:
        sections.append('<p>Unavailable: validation has not run.</p>')
    sections += ['<h2>Measured runtime</h2>']
    if benchmark:
        sections += ['<p>Benchmark status: '+escape(benchmark['status'])+'</p>', pretty(benchmark['timing_scope'])]
        rows = []
        for item in benchmark['measurements']:
            if item['status'] == 'measured':
                s,g = item['variants']['sequential'],item['variants']['generated']
                rows.append((item['size'],item['seed'],item['threads'],f"{s['kernel']['median_seconds']*1000:.6f}",f"{g['kernel']['median_seconds']*1000:.6f}",f"{g['kernel']['spread_seconds']*1000:.6f}",f"{item['kernel_speedup']:.3f}" if item['kernel_speedup'] is not None else 'Unavailable',f"{item['end_to_end_speedup']:.3f}" if item['end_to_end_speedup'] is not None else 'Unavailable'))
        sections.append(table(['Size','Seed','Threads','Serial kernel ms','Generated kernel ms','Generated spread ms','Kernel speedup','End-to-end speedup'],rows))
        sections.append('<p>Every trial, command, timer resolution and warmup is retained in benchmark.json. Timing spread is max minus min. Ratios at or below timer resolution are unavailable. Slowdowns are valid evidence.</p>')
        if benchmark.get('reason'):
            sections.append('<p>'+escape(benchmark['reason'])+'</p>')
    else:
        sections.append('<p>Unavailable: no timing measurements.</p>')
    sections += ['<h2>GPU verification</h2>',pretty(report.get('gpu', (doctor or {}).get('gpu',{'status':'unavailable','reason':'No device evidence'}))),
                 '<p>Host fallback does not count as GPU execution. GPU timing requires mandatory offload and evidence from the actual generated kernel.</p>',
                 '<h2>Compiler and environment</h2>',pretty({'compiler':report.get('compiler'), 'doctor':doctor}),
                 '<h2>Errors and limitations</h2>',pretty({'errors':report.get('errors',[]),'limitations':report.get('limitations',[])}),
                 '<details><summary>Full original source</summary><pre>'+escape(report.get('source',{}).get('text') or 'Unavailable')+'</pre></details>']
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Praline evidence report</title><style>body{font:16px system-ui,sans-serif;line-height:1.5;color:#20252a;max-width:1100px;margin:32px auto;padding:0 24px}h1,h2,h3{line-height:1.25}h2{margin-top:36px;border-bottom:1px solid #ccc;padding-bottom:8px}pre{background:#f5f5f5;padding:16px;overflow:auto;font:13px ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}th,td{border:1px solid #ddd;text-align:left;padding:8px;vertical-align:top}th{background:#eee}a{color:#145882}details{margin:12px 0}</style><body>'+''.join(sections)+'</body></html>'
    destination = root/'report.html'
    destination.write_text(document)
    return destination
