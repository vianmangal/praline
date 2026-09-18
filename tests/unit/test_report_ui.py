"""Presentation tests; compiler data and decisions remain untouched."""
from copy import deepcopy

from praline.report.html import render_report


def test_report_navigation_code_and_decisions(tmp_path):
    report = {
        'source': {'path': 'example.c', 'text': 'int x = 1;\n<script>bad</script>'},
        'loops': [dict(id='loop-1', function='kernel', span={'line': 2},
                       source='for (;;) {}', decision=state, reasons=[
                           dict(code='REASON', message='<unsafe>', helper_chain=['helper'])],
                       assumptions=['Valid buffers']) for state in ('safe', 'unsafe', 'unknown')],
        'functions': [], 'gpu': {'status': 'generated', 'reason': 'Device execution not verified'},
    }
    original = deepcopy(report)
    (tmp_path / 'generated.c').write_text('#pragma omp parallel for\nfor (;;) {}')
    (tmp_path / 'patch.diff').write_text('-old\n+new')
    page = render_report(report, tmp_path).read_text()
    assert report == original
    assert 'Helvetica,Arial,sans-serif' in page
    assert page.index('href="#loops"') < page.index('href="#source"') < page.index('href="#validation"') < page.index('href="#timing"')
    for anchor in ('loops', 'helpers', 'source', 'validation', 'timing', 'gpu', 'environment'):
        assert f'href="#{anchor}"' in page and f'id="{anchor}"' in page
    for state in ('safe', 'unsafe', 'unknown'):
        assert f'class="badge {state}"' in page
    assert '<script>' not in page
    assert '&lt;unsafe&gt;' in page
    assert 'line-number' in page and '#pragma omp parallel for' in page
    assert 'class="code-line added"' in page
    assert 'Device execution not verified' in page


def test_execution_only_and_missing_artifacts(tmp_path):
    page = render_report(None, tmp_path).read_text()
    assert 'No analyzed loop evidence' in page
    assert 'No generated source in this run' in page
    assert 'Unavailable: validation has not run' in page
    assert 'Host fallback does not count as GPU execution' in page
