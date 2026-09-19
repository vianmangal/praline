from pathlib import Path

import pytest

from praline.web import ASSET_ROOT, analyze_submission


SAFE = """static int apply(int value) { return value * 3 + 1; }
void map(const int *restrict input, int *restrict output, int n) {
  for (int i = 0; i < n; ++i) output[i] = apply(input[i]);
}
"""


def test_web_assets_exist_and_use_helvetica():
    for name in ("index.html", "analyze.html", "styles.css", "app.js"):
        assert (ASSET_ROOT / name).is_file()
    assert '"Helvetica Neue", Helvetica' in (ASSET_ROOT / "styles.css").read_text()


def test_web_submission_analyzes_and_generates_cpu():
    result = analyze_submission({"code": SAFE, "filename": "map.c", "target": "cpu"})
    assert result["ok"] is True
    assert result["analysis"]["loops"][0]["decision"] == "safe"
    assert "#pragma omp parallel for" in result["generated"]
    assert result["diff"]


def test_web_submission_generates_gpu_with_extents():
    result = analyze_submission({
        "code": SAFE,
        "filename": "map.c",
        "target": "gpu",
        "extents": "input=n, output=n",
    })
    assert result["analysis"]["loops"][0]["decision"] == "safe"
    assert "target teams distribute parallel for" in result["generated"]


def test_web_submission_refuses_unsafe_loop():
    code = "int counter; void f(int *a){for(int i=0;i<8;++i){counter++;a[i]=i;}}"
    result = analyze_submission({"code": code, "target": "cpu"})
    assert result["analysis"]["loops"][0]["decision"] == "unsafe"
    assert result["generated"] is None


def test_web_submission_requires_source():
    with pytest.raises(ValueError, match="Paste C source"):
        analyze_submission({"code": ""})


def test_web_submission_rejects_non_c_filename():
    with pytest.raises(ValueError, match="ending in .c"):
        analyze_submission({"code": SAFE, "filename": "map.txt"})
