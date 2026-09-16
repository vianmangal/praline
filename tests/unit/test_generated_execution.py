"""Real compile/run checks. These are correctness tests, not a benchmark harness."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from praline.analysis import analyze_source
from praline.model import AnalysisConfig
from praline.transform import transform_source

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CLANG = os.environ.get("PRALINE_TEST_CLANG", "clang")


def omp_flags():
    """Environment override supports Linux CI without assuming Apple flags."""
    override = os.environ.get("PRALINE_TEST_OPENMP_FLAGS")
    if override is not None:
        return shlex.split(override)
    for lib in [Path("/opt/homebrew/opt/libomp/lib"), Path("/usr/local/opt/libomp/lib")]:
        if (lib / "libomp.dylib").exists():
            return ["-Xclang", "-fopenmp", f"-L{lib}", f"-Wl,-rpath,{lib}", "-lomp"]
    return ["-fopenmp"]


@unittest.skipUnless(shutil.which(CLANG), "Clang is unavailable")
class GeneratedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="praline-execution-")
        cls.directory = Path(cls.temp.name)
        cls.flags = omp_flags()
        probe = cls.directory / "probe.c"
        probe.write_text('''#include <stdio.h>
extern int omp_get_thread_num(void);
extern int omp_get_num_devices(void);
int main(void){int workers=0;
#pragma omp parallel reduction(+:workers)
{workers += omp_get_thread_num() >= 0;}
printf("workers=%d devices=%d\\n",workers,omp_get_num_devices());
return workers < 2;}
''')
        command = [CLANG, "-std=c11", str(probe), *cls.flags, "-o", str(cls.directory / "probe")]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            cls.temp.cleanup()
            raise unittest.SkipTest("CPU OpenMP toolchain unavailable: " + compiled.stderr)
        run = subprocess.run([str(cls.directory / "probe")], env={**os.environ, "OMP_NUM_THREADS": "2", "OMP_DYNAMIC": "FALSE"},
                             capture_output=True, text=True, timeout=30)
        if run.returncode:
            cls.temp.cleanup()
            raise AssertionError("OpenMP did not execute on multiple threads: " + run.stdout + run.stderr)
        cls.probe_output = run.stdout.strip()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compile(self, source, name, openmp, extra=()):
        executable = self.directory / name
        command = [CLANG, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(source),
                   str(FIXTURES / "map_driver.c"), *extra,
                   *(self.flags if openmp else []), "-o", str(executable)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        return executable

    def test_cpu_scalar_and_pointer_helpers_match_every_element(self):
        for name, extra in [("helper_map", []), ("pointer_helper", ["-DKERNEL=pointer_helper", "-DSCALE=1"])]:
            with self.subTest(kernel=name):
                source = FIXTURES / (name + ".c")
                report = analyze_source(source)
                result = transform_source(source, report, "cpu", self.directory / name)
                serial = self.compile(source, name + "-serial", False, extra)
                parallel = self.compile(self.directory / name / "generated.c", name + "-parallel", True, extra)
                for size in [0, 1, 2, 31, 1024, 65536]:
                    for seed in [1, 17, 12345]:
                        for threads in [1, 4]:
                            for exe in [serial, parallel]:
                                with self.subTest(kernel=name, size=size, seed=seed, threads=threads, variant=exe.name):
                                    proc = subprocess.run([str(exe), str(size), str(seed)],
                                        env={**os.environ, "OMP_NUM_THREADS": str(threads), "OMP_DYNAMIC": "FALSE"},
                                        capture_output=True, text=True, timeout=30)
                                    self.assertEqual(proc.returncode, 0, proc.stderr)
                                    self.assertEqual(proc.stdout, "all elements match\n")
                self.assertEqual(result["report"]["validation"]["status"], "not_run")

    def test_comparison_driver_detects_wrong_output(self):
        wrong = self.directory / "wrong.c"
        wrong.write_text("void helper_map(int n,const int *input,int *output){for(int i=0;i<n;++i)output[i]=input[i];}\n")
        exe = self.compile(wrong, "wrong", False)
        proc = subprocess.run([str(exe), "32", "17"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("mismatch", proc.stderr)

    def test_gpu_source_syntax_is_not_claimed_as_device_execution(self):
        source = FIXTURES / "pointer_helper.c"
        report = analyze_source(source, AnalysisConfig(extents={"input": "n", "output": "n"}))
        result = transform_source(source, report, "gpu", self.directory / "gpu")
        proc = subprocess.run([CLANG, "-std=c11", "-Xclang", "-fopenmp", "-Werror", "-fsyntax-only",
                               str(self.directory / "gpu" / "generated.c")], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(result["report"]["gpu"]["status"], "generated")
        self.assertIsNone(result["report"]["gpu"]["is_initial_device"])

    @unittest.skipUnless(os.environ.get("PRALINE_TEST_OFFLOAD_FLAGS"),
                         "Real GPU offload unverified: set PRALINE_TEST_OFFLOAD_FLAGS on a compatible device host")
    def test_real_gpu_requires_mandatory_offload_and_noninitial_device(self):
        flags = shlex.split(os.environ["PRALINE_TEST_OFFLOAD_FLAGS"])
        probe = self.directory / "gpu-probe.c"
        probe.write_text('''#include <stdio.h>
extern int omp_is_initial_device(void);
extern int omp_get_num_devices(void);
int main(void){int initial=1;int devices=omp_get_num_devices();
#pragma omp target map(from:initial)
{initial=omp_is_initial_device();}
printf("devices=%d is_initial_device=%d\\n",devices,initial);
return devices < 1 || initial;}
''')
        command = [CLANG, "-std=c11", *flags, str(probe), "-o", str(self.directory / "gpu-probe")]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        env = {**os.environ, "OMP_TARGET_OFFLOAD": "MANDATORY"}
        result = subprocess.run([str(self.directory / "gpu-probe")], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("is_initial_device=0", result.stdout)
        for kernel, extra in [("helper_map", []), ("pointer_helper", ["-DKERNEL=pointer_helper", "-DSCALE=1"])]:
            original = FIXTURES / (kernel + ".c")
            report = analyze_source(original, AnalysisConfig(clang=CLANG, extents={"input": "n", "output": "n"}))
            out = self.directory / ("real-gpu-" + kernel)
            transform_source(original, report, "gpu", out)
            exe = out / "program"
            compiled = subprocess.run([CLANG, "-std=c11", "-O2", *flags, str(out / "generated.c"),
                                       str(FIXTURES / "map_driver.c"), *extra, "-o", str(exe)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            for size in [0, 1, 31, 1024, 65536]:
                result = subprocess.run([str(exe), str(size), "17"], env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
