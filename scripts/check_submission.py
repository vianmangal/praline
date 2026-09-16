#!/usr/bin/env python3
"""Audit local submission artifacts without implying publication."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
required = ['abstract.md','deck.pdf','deck.pptx','video-script.md','MANIFEST.md','evidence/doctor.json','evidence/map-cpu/analysis.json','evidence/map-cpu/validation.json','evidence/map-cpu/benchmark.json']
missing = [name for name in required if not (ROOT/'submission'/name).is_file()]
for name in required:
    print(('MISSING ' if name in missing else 'PRESENT ')+name)
for name in ('analysis','validation','benchmark'):
    path = ROOT/'submission/evidence/map-cpu'/(name+'.json')
    if path.is_file():
        evidence = json.loads(path.read_text())
        print(name+' state: '+evidence['status'])
errors=[]
root=ROOT/'submission/evidence/map-cpu'
if all((root/(name+'.json')).is_file() for name in ('analysis','validation','benchmark')):
    analysis=json.loads((root/'analysis.json').read_text())
    validation=json.loads((root/'validation.json').read_text())
    benchmark=json.loads((root/'benchmark.json').read_text())
    if validation['status']!='passed' or benchmark['status']!='measured':
        errors.append('CPU validation/measurement incomplete')
    if benchmark['compilation']!=validation['compilation']:
        errors.append('Validation and benchmark compilation differ')
    if analysis['source']['sha256']!=hashlib.sha256((ROOT/'examples/helper_map.c').read_bytes()).hexdigest():
        errors.append('Static analysis source is stale')
    if validation['compilation']['generated']['source_hash']!=hashlib.sha256((root/'generated.c').read_bytes()).hexdigest():
        errors.append('Generated source differs from validation')
    if not all(case['passed'] for case in validation['cases']):
        errors.append('Some CPU validation cases did not pass')
    sanitizer=json.loads((root/'sanitizer.json').read_text()) if (root/'sanitizer.json').exists() else None
    if sanitizer and sanitizer['compilation']['generated']['source_hash']!=validation['compilation']['generated']['source_hash']:
        errors.append('Sanitizer evidence is stale')
for error in errors:
    print('ERROR '+error)
print('Local file presence does not establish publication, accessible links, or form submission.')
sys.exit(bool(missing or errors))
