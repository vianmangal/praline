"""The normative schema is extracted from the shared contract, not duplicated."""
import json
from pathlib import Path
import re
import tempfile
import unittest

from praline.analysis import analyze_source
from praline.model import AnalysisConfig
from praline.transform import transform_source

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(Draft202012Validator, "Optional jsonschema dependency is unavailable")
class ContractTests(unittest.TestCase):
    def test_all_reports_and_generation_match_frozen_schema(self):
        contract = (ROOT / "docs" / "CONTRACT.md").read_text()
        schema = json.loads(re.search(r"```json\n(.*?)\n```", contract, re.S).group(1))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for path in (ROOT / "tests" / "fixtures").glob("*.c"):
            with self.subTest(fixture=path.name):
                report = analyze_source(path, AnalysisConfig(extents={"input": "n", "output": "n"}))
                validator.validate(report)
                if path.name in {"helper_map.c", "pointer_helper.c"}:
                    for target in ["cpu", "gpu"]:
                        with tempfile.TemporaryDirectory(prefix="praline-schema-") as directory:
                            result = transform_source(path, report, target, directory)
                            validator.validate(result["report"])
                            validator.validate(json.loads((Path(directory) / "analysis.json").read_text()))
        validator.validate(analyze_source(ROOT / "tests" / "fixtures" / "missing.c"))
