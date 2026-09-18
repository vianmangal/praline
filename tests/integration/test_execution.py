from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
from praline.doctor import detect
from praline.execution.compile import compile_program, compile_pair
from praline.execution.validate import execute, validate_pair, compare
from praline.execution.benchmark import benchmark_pair
from praline.execution.process import run
from praline.report.html import render_report

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def toolchain():
    found = detect()
    if not found['selected']:
        pytest.skip('No working C compiler detected')
    return found


def test_deterministic_examples_and_independent_reference(toolchain,tmp_path):
    for source in sorted((ROOT/'examples').glob('*.c')):
        compiled = compile_program(source,tmp_path/source.stem,toolchain)
        assert compiled['status'] == 'ok', compiled
        for size in (0,1,2,1024):
            for seed in (0,7):
                actual = execute(compiled['output'],size,seed)
                reference = execute(compiled['output'],size,seed,mode='reference')
                assert actual['status'] == reference['status'] == 'ok'
                assert compare(actual['data']['outputs'],reference['data']['outputs'])['status'] == 'passed', source
                assert actual['data']['observables'] == reference['data']['observables']


def test_full_output_mismatch_and_raw_benchmark(toolchain,tmp_path):
    if toolchain['cpu_openmp']['status'] != 'verified':
        pytest.skip('OpenMP not verified by runtime probe')
    source = ROOT/'examples/helper_map.c'
    generated = tmp_path/'generated.c'
    # Harness fixture only. This is deliberately NOT evidence of core generation.
    generated.write_text(source.read_text().replace('    for (','    #pragma omp parallel for\n    for ('))
    pair = compile_pair(source,generated,tmp_path/'bin',toolchain)
    validated = validate_pair(pair,sizes=[0,1,1024],seeds=[1,7],threads=2)
    assert validated['status'] == 'passed'
    benchmark = benchmark_pair(pair,validated,sizes=[1024],seeds=[7],thread_counts=[2],environment=toolchain['environment'])
    assert benchmark['status'] == 'measured'
    for variant in benchmark['measurements'][0]['variants'].values():
        assert len(variant['samples']) == 5
        assert len(variant['warmups']) == 1
        assert variant['kernel']['median_seconds'] >= 0
        assert all(s['process']['command'] and s['end_to_end_seconds'] > 0 for s in variant['samples'])
    generated.write_text(generated.read_text().replace('value * 3 + 1','value * 3 + 2'))
    wrong_pair = compile_pair(source,generated,tmp_path/'wrong-bin',toolchain)
    wrong = validate_pair(wrong_pair,sizes=[1024],seeds=[1],threads=2)
    assert wrong['status'] == 'failed'
    assert wrong['cases'][0]['comparison']['mismatches'] == 1024
    assert benchmark_pair(wrong_pair,wrong,sizes=[1024],seeds=[1],thread_counts=[2])['status'] == 'unavailable'


def test_timeout_compile_failure_and_invalid_protocol(toolchain,tmp_path,monkeypatch):
    timed = run([sys.executable,'-c','import time; time.sleep(5)'],timeout=.05)
    assert timed['status'] == 'timeout'
    import praline.execution.process as process_module
    monkeypatch.setattr(process_module,'MAX_OUTPUT',1024)
    excessive = run([sys.executable,'-c','import time; print("x"*5000,flush=True); time.sleep(5)'],timeout=2)
    assert excessive['status'] == 'output_limit'
    assert len(excessive['stdout']) <= 1024
    monkeypatch.undo()
    broken = tmp_path/'broken.c'
    broken.write_text('int main(void) { invalid token; }')
    assert compile_program(broken,tmp_path/'broken',toolchain)['status'] == 'failed'
    invalid = tmp_path/'invalid.c'
    invalid.write_text('#include <stdio.h>\nint main(void){puts("42");}')
    compiled = compile_program(invalid,tmp_path/'invalid',toolchain)
    assert execute(compiled['output'],1,1)['status'] == 'protocol_error'
    assert run(['/this/compiler/does/not/exist'])['status'] == 'unavailable'


def test_numeric_policy():
    assert compare([1,2],[2,1])['status'] == 'mismatch'  # same sum, wrong array
    assert compare([1],[1.0])['status'] == 'mismatch'
    assert compare([1.0],[1.001],numeric='float',atol=.002)['status'] == 'passed'
    assert compare([float('nan')],[float('nan')],numeric='float')['status'] == 'mismatch'
    assert compare([float('inf')],[float('inf')],numeric='float')['status'] == 'passed'
    with pytest.raises(ValueError):
        compare([1],[1],atol=-1)


def test_local_report_escapes_untrusted_source(tmp_path):
    result = {'source':{'text':'<script>alert(1)</script>','path':'<&>','sha256':'hash'},
              'loops':[], 'functions':[], 'limitations':['<img src=x onerror=alert(1)>']}
    page = render_report(result,tmp_path).read_text()
    assert '<script>' not in page and '<img src=x' not in page
    assert '&lt;script&gt;' in page
    assert 'Unavailable: no timing measurements' in page


def test_installed_cli_help_and_bad_invocation():
    result = subprocess.run([sys.executable,'-m','praline.cli','--help'],capture_output=True,text=True)
    assert result.returncode == 0
    assert 'doctor' in result.stdout and 'benchmark' in result.stdout
    result = subprocess.run([sys.executable,'-m','praline.cli','validate','missing.c','--generated','missing.c','--threads','0'],capture_output=True,text=True)
    assert result.returncode == 2


def test_output_directory_cannot_delete_input_source(tmp_path):
    from praline.cli import main
    original=tmp_path/'generated.c'
    text='int main(void) { return 0; }\n'
    original.write_text(text)
    assert main(['analyze',str(original),'--out',str(tmp_path)]) == 2
    assert original.read_text() == text
    assert not (tmp_path/'analysis.json').exists()
