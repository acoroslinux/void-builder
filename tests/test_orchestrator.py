import tempfile
import unittest
from pathlib import Path
from void_builder.core.orchestrator import BuildOrchestrator, BuildOrchestratorError


class TestOrchestrator(unittest.TestCase):
    def test_orchestrator_validation(self):
        orchestrator = BuildOrchestrator(
            arch="x86_64",
            config_path="configs/global_build.json",
            mode="mock",
        )
        report = orchestrator.validate()
        self.assertTrue(report["valid"])
        self.assertEqual(report["summary"]["target_arch"], "x86_64")

    def test_orchestrator_mock_build(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "void-test.iso"
            orchestrator = BuildOrchestrator(
                arch="x86_64",
                config_path="configs/global_build.json",
                mode="mock",
            )
            result = orchestrator.run_build(str(output))
            self.assertTrue(Path(result).exists())
            self.assertTrue(Path(str(result) + ".sha256").exists())

    def test_orchestrator_fast_mode_and_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "void-fast-test.iso"
            orchestrator = BuildOrchestrator(
                arch="x86_64",
                config_path="configs/global_build.json",
                mode="mock",
                fast_mode=True,
                use_tmpfs=True,
                benchmark=True,
            )
            self.assertEqual(orchestrator.compression, "zstd")
            self.assertTrue(orchestrator.fast_mode)
            self.assertTrue(orchestrator.use_tmpfs)
            self.assertTrue(orchestrator.benchmark)

            result = orchestrator.run_build(str(output))
            self.assertTrue(Path(result).exists())
            self.assertIsNotNone(orchestrator.builder)
            self.assertIn("total", orchestrator.builder.timings)
            self.assertGreaterEqual(orchestrator.builder.timings["total"], 0.0)

    def test_toolchain_dir_in_workdir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            orchestrator = BuildOrchestrator(
                arch="x86_64",
                config_path="configs/global_build.json",
                mode="mock",
                clean=False,
            )
            orchestrator._setup()
            self.assertIsNotNone(orchestrator.toolchain)
            # Verifica se toolchain_dir fica dentro do workdir
            self.assertEqual(orchestrator.toolchain.toolchain_dir, orchestrator.workdir / "build_host")
            self.assertEqual(orchestrator.toolchain.host_dir, orchestrator.workdir / "build_host" / "void-host")
            self.assertEqual(orchestrator.toolchain.target_dir, orchestrator.workdir / "build_host" / "void-target")

    def test_orchestrator_clean_removes_workdir_and_build_host(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "void-clean-test.iso"
            orchestrator = BuildOrchestrator(
                arch="x86_64",
                config_path="configs/global_build.json",
                mode="mock",
                clean=True,
            )
            result = orchestrator.run_build(str(output))
            self.assertTrue(Path(result).exists())
            # Com clean=True (padrão sem --no-clean), o workdir (e consequentemente build_host) deve ser removido
            self.assertFalse(orchestrator.workdir.exists())


if __name__ == "__main__":
    unittest.main()


