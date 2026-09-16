#!/usr/bin/env python3
"""Actual sanitizer and host-syntax checks; neither proves GPU execution."""
from pathlib import Path
import json
from praline.execution.compile import compile_pair, source_hash
from praline.execution.validate import validate_pair
from praline.execution.process import run
from praline.report.html import render_report

ROOT=Path(__file__).resolve().parents[1]
root=ROOT/'submission/evidence/map-cpu'
doctor=json.loads((root/'doctor.json').read_text())
pair=compile_pair(ROOT/'examples/helper_map.c',root/'generated.c',ROOT/'runs/sanitizer/generated',doctor,
                  extra_flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'])
result=validate_pair(pair,sizes=[0,1,1024,65536],seeds=[1,7],threads=2)
(root/'sanitizer.json').write_text(json.dumps(result,indent=2)+'\n')
print('Core-generated ASan/UBSan:',result['status'])
gpu=ROOT/'submission/evidence/map-gpu'
source=gpu/'generated.c'
selected=doctor['selected']
checked=run([selected['path'],'-std=c11','-O2','-fsyntax-only',str(source.resolve()),*selected['openmp_flags']])
checked['source_sha256']=source_hash(source)
checked['runtime_header_sha256']=source_hash(gpu/'runtime.h')
(gpu/'host-syntax-check.json').write_text(json.dumps(checked,indent=2)+'\n')
report=json.loads((gpu/'analysis.json').read_text())
report['gpu']['host_syntax_check']=checked
if checked['status']=='ok':
    report['gpu']['status']='syntax_checked'
    report['gpu']['reason']='Host OpenMP syntax check passed; no GPU backend compilation or device execution verified'
    report['gpu']['compile_command']=checked['command']
(gpu/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
render_report(report,gpu,doctor=doctor)
print('GPU host syntax:',checked['status'])
