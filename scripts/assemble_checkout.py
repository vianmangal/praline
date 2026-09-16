#!/usr/bin/env python3
"""Build a combined source snapshot without editing either task's owned files."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core-root',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ROOT/'runs/integrated')
    p.add_argument('--archive',type=Path)
    args=p.parse_args()
    core=args.core_root.resolve()
    out=args.out.resolve()
    if out.exists():
        raise SystemExit('Choose a new nonexisting --out directory')
    if not (core/'docs/CONTRACT.md').is_file():
        raise SystemExit('Core contract is missing')
    out.mkdir(parents=True)
    provenance={'created_at':datetime.now(timezone.utc).isoformat(),'files':{},
                'note':'Core files are copied byte-for-byte. No safety or transformation implementation is changed.'}
    def copy(source_root,relative,owner):
        source=source_root/relative
        if source.is_dir():
            for child in sorted(source.rglob('*')):
                if child.is_file() and not any(part in ('__pycache__','.deck-build','node_modules','.pytest_cache') for part in child.parts) and child.suffix not in ('.pyc','.mp4','.mov') and not child.name.endswith('.tar.gz'):
                    copy(source_root,child.relative_to(source_root),owner)
        elif source.is_file():
            target=out/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
            provenance['files'][str(relative)]={'owner':owner,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    for relative in ('pyproject.toml','.gitignore','README.md','PRD.md','IMPLEMENTATION_PLAN.md','SUBMISSION_PLAN.md',
                     'praline/cli.py','praline/doctor.py','praline/execution','praline/report','examples','tests/integration','scripts','submission'):
        copy(ROOT,Path(relative),'experience')
    for relative in ('praline/model.py','praline/frontend','praline/analysis','praline/transform','tests/unit','tests/fixtures','docs/CONTRACT.md'):
        if not (core/relative).exists():
            raise SystemExit('Missing core path: '+relative)
        copy(core,Path(relative),'compiler')
    (out/'INTEGRATION_PROVENANCE.json').write_text(json.dumps(provenance,indent=2)+'\n')
    if args.archive:
        args.archive.parent.mkdir(parents=True,exist_ok=True)
        with tarfile.open(args.archive,'w:gz') as archive:
            for child in sorted(out.rglob('*')):
                if child.is_file():
                    archive.add(child,arcname=Path('praline')/child.relative_to(out))
    print(out)


if __name__=='__main__':
    main()
