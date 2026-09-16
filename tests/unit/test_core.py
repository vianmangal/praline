"""Semantic regression tests use real Clang, never canned analysis results."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from praline.analysis import analyze_source
from praline.frontend import parse_source
from praline.model import AnalysisConfig, PralineError
from praline.transform import transform_source
from praline.transform.edits import Edit, apply_edits

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CLANG = os.environ.get("PRALINE_TEST_CLANG", "clang")


@unittest.skipUnless(shutil.which(CLANG), "Real Clang is required")
class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="praline-unit-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def analyze(self, code=None, fixture=None, **options):
        self.source = FIXTURES / fixture if fixture else self.directory / "input.c"
        if code is not None:
            self.source.write_text(code)
        self.report = analyze_source(self.source, AnalysisConfig(clang=CLANG, **options))
        self.assertEqual(self.report["errors"], [])
        return self.report["loops"][0]

    def check_decision(self, code, decision, reason_code=None, **options):
        loop = self.analyze(code, **options)
        self.assertEqual(loop["decision"], decision, loop["reasons"])
        if reason_code:
            self.assertIn(reason_code, {r["code"] for r in loop["reasons"]})
        if decision != "safe":
            with self.assertRaises(PralineError):
                transform_source(self.source, self.report)
        return loop

    def test_positive_transitive_scalar_helper(self):
        loop = self.analyze(fixture="helper_map.c", extents={"input": "n", "output": "n"})
        self.assertEqual(loop["decision"], "safe", loop["reasons"])
        self.assertEqual(loop["calls"], ["apply", "square"])
        self.assertEqual(loop["eligible_targets"], ["cpu", "gpu"])
        self.assertTrue(next(f for f in self.report["functions"] if f["name"] == "square")["pure"])
        self.assertEqual(loop["recommendation"]["target"], "insufficient_evidence")

    def test_negative_fixtures_and_no_generation(self):
        for fixture, decision, code in [
            ("global_write.c", "unsafe", "GLOBAL_WRITE"),
            ("prefix_dependency.c", "unsafe", "CROSS_ITERATION_DEPENDENCE"),
            ("alias_unknown.c", "unknown", "ALIAS_UNRESOLVED"),
            ("scatter_write.c", "unsafe", "WRITE_COLLISION"),
            ("unknown_call.c", "unknown", "UNKNOWN_CALL"),
        ]:
            with self.subTest(fixture=fixture):
                loop = self.analyze(fixture=fixture)
                self.assertEqual(loop["decision"], decision, loop["reasons"])
                self.assertIn(code, {r["code"] for r in loop["reasons"]})
                for target in ["cpu", "gpu"]:
                    with self.assertRaises(PralineError):
                        transform_source(self.source, self.report, target)

    def test_effect_witness_chain(self):
        self.analyze(fixture="global_write.c")
        witnesses = [r for r in self.report["loops"][0]["reasons"] if r["code"] == "GLOBAL_WRITE"]
        self.assertIn("bump", witnesses[0]["helper_chain"])
        self.assertIsNotNone(witnesses[0]["span"])

    def test_pointer_arguments_and_transitive_substitution(self):
        loop = self.analyze(fixture="pointer_helper.c", extents={"input": "n", "output": "n"})
        self.assertEqual(loop["decision"], "safe", loop["reasons"])
        effect = next(e for e in loop["effects"] if e["kind"] == "write")
        self.assertEqual((effect["name"], effect["index"]), ("output", "i"))
        self.assertEqual(effect["helper_chain"][1:], ["apply", "store"])

    def test_swapped_arguments_keep_identity(self):
        code = '''static void store(int *x, int *y, int j) { x[j]=y[j-1]; }
        void f(int *a) { for(int i=1;i<64;++i) store(a,a,i); }'''
        self.check_decision(code, "unsafe", "CROSS_ITERATION_DEPENDENCE", extents={"a": "64"})

    def test_pointer_offset_substitution(self):
        code = '''static void store(int *p,int k) {p[k]=k;}
        void f(int *restrict a){for(int i=0;i<63;++i) store(a+1,i);}'''
        loop = self.check_decision(code, "safe", extents={"a": "64"})
        self.assertEqual(next(e for e in loop["effects"] if e["kind"] == "write")["index"], "(1 + i)")

    def test_address_of_element_substitution(self):
        self.check_decision('''static void put(int *p){*p=1;}
        void f(int *a){for(int i=0;i<16;++i)put(&a[i]);}''', "safe")

    def test_offset_requires_bounds(self):
        code = "void f(int *restrict a,const int *restrict b){for(int i=1;i<64;++i)a[i]=b[i-1];}"
        self.check_decision(code, "unknown", "EXTENT_UNKNOWN")
        self.check_decision(code, "safe", extents={"a": "64", "b": "64"})

    def test_explicit_disjoint_assumption(self):
        loop = self.analyze(fixture="alias_unknown.c", assume_disjoint=(("input", "output"),))
        self.assertEqual(loop["decision"], "safe")
        self.assertTrue(any("User assumes" in a for a in loop["assumptions"]))

    def test_distinct_declared_arrays(self):
        loop = self.check_decision("void f(void){int a[32]={0},b[32];for(int i=0;i<32;++i)b[i]=a[i]+1;}", "safe")
        self.assertIn("gpu", loop["eligible_targets"])
        self.assertEqual({m["extent"] for m in loop["mappings"]}, {"32"})

    def test_local_scalar_shadow_does_not_write_global(self):
        loop = self.check_decision('''int value; static int h(int x){int value=x+1;return value;}
        void f(int *a){for(int i=0;i<32;++i){int value=i;a[i]=h(value);}}''', "safe")
        self.assertNotIn("value", loop["shared_variables"])

    def test_shared_scalar_write_rejected(self):
        self.check_decision("void f(int *a){int sum=0;for(int i=0;i<32;++i){sum+=i;a[i]=sum;}}", "unsafe", "SHARED_WRITE")

    def test_impure_unknown_calls_do_not_get_whitelisted(self):
        self.check_decision("extern int abs(int);void f(int *a){for(int i=0;i<32;++i)a[i]=abs(i);}", "unknown", "UNKNOWN_CALL")

    def test_pure_helper_does_not_prove_scatter(self):
        self.check_decision("static int h(int x){return x%2;}void f(int *a){for(int i=0;i<32;++i)a[h(i)]=i;}", "unknown", "UNSUPPORTED_ACCESS")

    def test_recursive_helper_unknown(self):
        self.check_decision("static int h(int x){return x?h(x-1):0;}void f(int *a){for(int i=0;i<32;++i)a[i]=h(i);}", "unknown", "RECURSION")

    def test_helper_modified_formal_unknown(self):
        self.check_decision("static void h(int *a,int k){++k;a[k]=1;}void f(int *a){for(int i=0;i<32;++i)h(a,i);}", "unknown", "UNSUPPORTED_SYNTAX")

    def test_indirect_call_unknown(self):
        self.check_decision("void f(int *a,int (*h)(int)){for(int i=0;i<32;++i)a[i]=h(i);}", "unknown", "UNKNOWN_CALL")

    def test_macro_loop_unknown(self):
        self.check_decision("#define INDEX i\nvoid f(int *a){for(int i=0;i<32;++i)a[INDEX]=i;}", "unknown", "MACRO_EXPANSION")

    def test_volatile_and_atomic_unknown(self):
        for typ in ["volatile int", "_Atomic(int)"]:
            with self.subTest(typ=typ):
                self.check_decision(f"void f({typ} *a){{for(int i=0;i<32;++i)a[i]=i;}}", "unknown", "VOLATILE_OR_ATOMIC")

    def test_restrict_does_not_separate_derived_local_alias(self):
        self.check_decision("void f(int *restrict a){int *p=a;for(int i=1;i<32;++i)a[i]=p[i-1];}",
                            "unknown", "ALIAS_UNRESOLVED", extents={"a": "32", "p": "32"})

    def test_rebound_parameter_does_not_get_restrict_separation(self):
        self.check_decision("void f(int *restrict a,int *b){b=a;for(int i=1;i<32;++i)a[i]=b[i-1];}",
                            "unknown", "ALIAS_UNRESOLVED", extents={"a": "32", "b": "32"})

    def test_address_taken_parameter_does_not_get_restrict_separation(self):
        self.check_decision("extern void mutate(int **);void f(int *restrict a,int *b){mutate(&b);for(int i=1;i<32;++i)a[i]=b[i-1];}",
                            "unknown", "ALIAS_UNRESOLVED", extents={"a": "32", "b": "32"})

    def test_pointer_address_cast_is_not_device_safe_arithmetic(self):
        self.check_decision("void f(int *a){for(int i=0;i<32;++i)a[i]=(long)a%7;}", "unknown", "UNSUPPORTED_ACCESS")

    def test_helper_pointer_escape_is_exposed(self):
        self.check_decision("int *saved;static int h(int *p){saved=p;return 1;}void f(int *a){for(int i=0;i<32;++i)a[i]=h(a);}", "unsafe", "GLOBAL_WRITE")
        summary = next(f for f in self.report["functions"] if f["name"] == "h")
        self.assertTrue(any(e["kind"] == "escape" for e in summary["effects"]))

    def test_helper_macro_access_unknown(self):
        self.check_decision("#define IDX j\nstatic void h(int *p,int j){p[IDX]=1;}void f(int *a){for(int i=0;i<32;++i)h(a,i);}", "unknown", "MACRO_EXPANSION")

    def test_private_pointer_is_unknown_not_a_shared_collision(self):
        loop = self.check_decision("void f(int *a){for(int i=0;i<32;++i){int *p=&a[i];*p=i;}}", "unknown", "UNSUPPORTED_ACCESS")
        self.assertNotIn("WRITE_COLLISION", {r["code"] for r in loop["reasons"]})

    def test_pointer_cast_unknown(self):
        self.check_decision("void f(char *a){for(int i=0;i<32;++i)((int*)a)[i]=i;}", "unknown", "UNSUPPORTED_ACCESS")

    def test_index_narrowing_not_treated_as_injective(self):
        self.check_decision("void f(int *a){for(int i=0;i<512;++i)a[(unsigned char)i]=i;}", "unknown", "UNSUPPORTED_ACCESS")

    def test_indirect_scatter_unknown(self):
        self.check_decision("void f(int *restrict a,int *restrict b){for(int i=0;i<32;++i)a[b[i]]=i;}", "unknown", "UNSUPPORTED_ACCESS")

    def test_induction_variable_cannot_be_its_own_upper_bound(self):
        self.check_decision("void f(int *a){for(int i=0;i<i;++i)a[i]=1;}", "unknown", "UNSUPPORTED_LOOP")

    def test_gpu_read_only_overlap_requires_layout_evidence(self):
        code = "void f(int *restrict out,const int *a,const int *b){for(int i=0;i<16;++i)out[i]=a[i]+b[i];}"
        loop = self.check_decision(code, "safe", extents={"out": "16", "a": "16", "b": "16"})
        self.assertEqual(loop["eligible_targets"], ["cpu"])
        loop = self.check_decision(code, "safe", extents={"out": "16", "a": "16", "b": "16"},
                                   assume_disjoint=(("a", "b"),))
        self.assertIn("gpu", loop["eligible_targets"])

    def test_loop_variable_modified_unknown(self):
        self.check_decision("void f(int *a){for(int i=0;i<32;++i){a[i]=1;i++;}}", "unknown", "UNSUPPORTED_LOOP")

    def test_early_return_unknown(self):
        self.check_decision("void f(int *a){for(int i=0;i<32;++i){if(i==3)return;a[i]=1;}}", "unknown", "UNSUPPORTED_SYNTAX")

    def test_addressed_shared_scalar_alias_unknown(self):
        self.check_decision("void f(void){int x=1;int *p=&x;for(int i=0;i<1;++i)p[i]=x;}", "unknown", "ALIAS_UNRESOLVED")

    def test_existing_openmp_is_not_duplicated(self):
        self.analyze(fixture="helper_map.c")
        generated = transform_source(self.source, self.report)["source"]
        loop = self.analyze(generated)
        self.assertEqual(loop["decision"], "unknown")
        self.assertIn("EXISTING_OPENMP", {r["code"] for r in loop["reasons"]})

    def test_nested_candidates_are_not_accepted(self):
        self.analyze("void f(int *a){for(int i=0;i<32;++i){for(int j=0;j<32;++j)a[j]=i;}}")
        self.assertTrue(all(l["decision"] != "safe" for l in self.report["loops"]))

    def test_stale_source_and_selection_guards(self):
        self.analyze("void f(int *a){for(int i=0;i<32;++i)a[i]=i;}")
        with self.assertRaises(PralineError) as cm:
            transform_source(self.source, self.report, loop_ids=["invalid"])
        self.assertEqual(cm.exception.code, "INVALID_SELECTION")
        self.source.write_text(self.source.read_text() + "\n")
        with self.assertRaises(PralineError) as cm:
            transform_source(self.source, self.report)
        self.assertEqual(cm.exception.code, "STALE_SOURCE")

    def test_bytes_not_unicode_character_offsets(self):
        self.analyze("/* café λ */\nvoid f(int *a){for(int i=0;i<32;++i)a[i]=i;}")
        generated = transform_source(self.source, self.report)["source"]
        self.assertIn("/* café λ */", generated)
        self.assertIn("\n#pragma omp parallel for", generated)
        self.syntax_check(generated)

    def test_prototype_resolution_uses_declaration_chain(self):
        self.check_decision("static int h(int);void f(int *a){for(int i=0;i<32;++i)a[i]=h(i);}static int h(int x){return x+1;}", "safe")

    def test_header_definition_is_not_rewritten(self):
        (self.directory / "helper.h").write_text("static int h(int x){return x+1;}\n")
        self.check_decision('#include "helper.h"\nvoid f(int *a){for(int i=0;i<32;++i)a[i]=h(i);}', "unknown", "UNKNOWN_CALL")

    def test_missing_gpu_extent_does_not_block_cpu(self):
        loop = self.analyze(fixture="helper_map.c")
        self.assertEqual(loop["eligible_targets"], ["cpu"])
        with self.assertRaises(PralineError) as cm:
            transform_source(self.source, self.report, "gpu")
        self.assertEqual(cm.exception.code, "TARGET_UNSUPPORTED")

    def test_config_extent_is_not_code_injection(self):
        loop = self.analyze(fixture="helper_map.c", extents={"input": "n); evil(); (", "output": "n"})
        self.assertNotIn("gpu", loop["eligible_targets"])

    def test_noninteger_and_oversized_extents_refuse_gpu(self):
        code = "void f(int *a,float length){for(int i=0;i<16;++i)a[i]=i;}"
        for extent in ["length", str(2**100)]:
            with self.subTest(extent=extent):
                loop = self.check_decision(code, "safe", extents={"a": extent})
                self.assertEqual(loop["eligible_targets"], ["cpu"])

    def test_gpu_preserves_partial_output(self):
        self.analyze("void f(int *a){for(int i=1;i<16;++i){if(i%2)a[i]=i;}}", extents={"a": "32"})
        generated = transform_source(self.source, self.report, "gpu")["source"]
        self.assertIn("map(tofrom: a[0:32])", generated)
        self.syntax_check(generated)

    def test_gpu_unbraced_if_else_and_simple_statement(self):
        self.analyze("void f(int *a,int flag){if(flag) for(int i=0;i<16;++i)a[i]=i; else a[0]=0;}", extents={"a": "16"})
        generated = transform_source(self.source, self.report, "gpu")["source"]
        self.syntax_check(generated)

    def test_adjacent_loops_and_helpers_have_unambiguous_edits(self):
        code = "static int h(int x){return x+1;}static int g(int x){return h(x);}" + \
               "void f(int *a){for(int i=0;i<16;++i)a[i]=g(i);for(int j=0;j<16;++j)a[j]=h(j);}"
        self.analyze(code, extents={"a": "16"})
        for target in ["cpu", "gpu"]:
            generated = transform_source(self.source, self.report, target)["source"]
            self.syntax_check(generated)
        self.assertEqual(generated.count("#pragma omp declare target"), 2)

    def test_artifacts_and_gpu_status(self):
        self.analyze(fixture="helper_map.c", extents={"input": "n", "output": "n"})
        original_report = json.dumps(self.report, sort_keys=True)
        result = transform_source(self.source, self.report, "gpu", self.directory / "run")
        self.assertEqual(result["report"]["gpu"]["status"], "generated")
        self.assertIsNone(result["report"]["gpu"]["is_initial_device"])
        self.assertEqual(json.dumps(self.report, sort_keys=True), original_report)
        for filename in ["analysis.json", "generated.c", "patch.diff"]:
            self.assertTrue((self.directory / "run" / filename).exists())
        self.assertEqual(result["source"].count("#pragma omp declare target"), 2)
        self.syntax_check(result["source"])

    def test_source_overwrite_refused(self):
        self.source = self.directory / "generated.c"
        self.source.write_text("void f(int *a){for(int i=0;i<4;++i)a[i]=i;}")
        report = analyze_source(self.source)
        with self.assertRaises(PralineError) as cm:
            transform_source(self.source, report, output_dir=self.directory)
        self.assertEqual(cm.exception.code, "SOURCE_OVERWRITE")

    def test_parse_error_and_missing_compiler_are_reports(self):
        path = self.directory / "invalid.c"
        path.write_text("not C!")
        report = analyze_source(path)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["errors"][0]["code"], "PARSE_ERROR")
        report = analyze_source(path, AnalysisConfig(clang="/nonexistent/praline-clang"))
        self.assertEqual(report["errors"][0]["code"], "COMPILER_NOT_FOUND")
        self.assertEqual(analyze_source(self.directory / "absent.c")["errors"][0]["code"], "SOURCE_ERROR")

    def test_ast_spans_and_declaration_identity(self):
        self.analyze(fixture="helper_map.c")
        tu = parse_source(self.source)
        self.assertTrue(tu.functions)
        loop = self.report["loops"][0]
        self.assertEqual(tu.data[loop["span"]["start"]:loop["span"]["end"]].decode(), loop["source"])
        self.assertEqual(loop["span"]["line"], 4)

    def syntax_check(self, source):
        path = self.directory / "syntax.c"
        path.write_text(source)
        proc = subprocess.run([CLANG, "-std=c11", "-Xclang", "-fopenmp", "-Werror", "-fsyntax-only", str(path)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class EditTests(unittest.TestCase):
    def test_overlap_and_hash_guards(self):
        data = b"abcdef"
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(apply_edits(data, [Edit(1, 2, b"X"), Edit(4, 5, b"Y")], digest), b"aXcdYf")
        for edits in [[Edit(1, 3, b""), Edit(2, 2, b"")], [Edit(1, 1, b""), Edit(1, 1, b"")]]:
            with self.assertRaises(PralineError):
                apply_edits(data, edits, digest)
        with self.assertRaises(PralineError):
            apply_edits(data, [], "stale")


if __name__ == "__main__":
    unittest.main()
