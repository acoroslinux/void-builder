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


if __name__ == "__main__":
    unittest.main()
