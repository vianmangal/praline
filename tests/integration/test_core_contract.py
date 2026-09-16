"""Run against actual core implementation, or visibly skip before integration."""
from pathlib import Path
import json
import pytest
from praline.execution import core
from praline.cli import main

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def actual_core():
    try:
        return core.api()
    except RuntimeError as exc:
        pytest.skip(str(exc))


def test_real_core_cpu_pipeline_and_report(actual_core,tmp_path):
    from praline.doctor import detect
    if detect()['cpu_openmp']['status'] != 'verified':
        pytest.skip('CPU OpenMP runtime probe did not pass')
    source = ROOT/'examples/helper_map.c'
    assert main(['transform',str(source),'--target','cpu','--out',str(tmp_path)]) == 0
    report = json.loads((tmp_path/'analysis.json').read_text())
    assert report['schema_version'] == 1
    assert any(l['decision']=='safe' for l in report['loops'])
    assert '#pragma omp' in (tmp_path/'generated.c').read_text()
    assert main(['benchmark',str(source),'--generated',str(tmp_path/'generated.c'),'--out',str(tmp_path),
                 '--sizes','0,1,1024','--seeds','1,7','--threads','1,2','--trials','5']) == 0
    result = json.loads((tmp_path/'analysis.json').read_text())
    assert result['validation']['status'] == 'passed'
    assert result['benchmark']['status'] == 'measured'
    assert result['source']['sha256'] == report['source']['sha256']
    assert 'Measured runtime' in (tmp_path/'report.html').read_text()


def test_negative_examples_do_not_transform(actual_core,tmp_path):
    for name,decision in [('global_write','unsafe'),('prefix_dependency','unsafe'),
                          ('scatter_write','unsafe'),('alias_unknown','unknown'),('unknown_call','unknown')]:
        source = ROOT/'examples'/(name+'.c')
        report = core.analyze(source)
        loops = [l for l in report['loops'] if l['function']=='kernel']
        assert loops and all(l['decision']==decision for l in loops), (name,loops)
        assert main(['transform',str(source),'--target','cpu','--out',str(tmp_path/name)]) == 2
        assert not (tmp_path/name/'generated.c').exists()


def test_real_gpu_generation_and_stale_analysis(actual_core,tmp_path):
    source = ROOT/'examples/helper_map.c'
    report = core.analyze(source,extents={'input':'n','output':'n'})
    generated = core.transform(source,report,target='gpu',out=tmp_path/'gpu')
    assert 'target teams distribute parallel for' in generated['source']
    assert 'map(' in generated['source'] and 'declare target' in generated['source']
    changed = tmp_path/'changed.c'
    changed.write_text(source.read_text()+'\n/* changed */\n')
    with pytest.raises(Exception) as exc:
        core.transform(changed,report,target='cpu',out=tmp_path/'stale')
    assert getattr(exc.value,'code',None) in ('STALE_SOURCE','SOURCE_CHANGED','SOURCE_HASH_MISMATCH')


def test_gpu_device_execution_when_available(actual_core,tmp_path):
    from praline.doctor import detect
    found = detect()
    if found['gpu']['status'] != 'device-verified':
        pytest.skip('GPU unavailable: mandatory offload did not establish a non-host device')
    source = ROOT/'examples/helper_map.c'
    assert main(['transform',str(source),'--target','gpu','--extent','input=n','--extent','output=n',
                 '--out',str(tmp_path)]) == 0
    # Passing requires generated-kernel device instrumentation, never doctor alone.
    assert main(['validate',str(source),'--generated',str(tmp_path/'generated.c'),'--target','gpu',
                 '--sizes','1024','--out',str(tmp_path)]) == 0
    result=json.loads((tmp_path/'validation.json').read_text())
    assert all(c['device_verified']['initial_device'] is False for c in result['cases'])
