import pytest
from pathlib import Path
from void_builder.core.orchestrator import BuildOrchestrator, BuildOrchestratorError


def test_orchestrator_validation():
    orchestrator = BuildOrchestrator(
        arch="x86_64",
        config_path="configs/global_build.json",
        mode="mock",
    )
    report = orchestrator.validate()
    assert report["valid"] is True
    assert report["summary"]["target_arch"] == "x86_64"


def test_orchestrator_mock_build(tmp_path):
    output = tmp_path / "void-test.iso"
    orchestrator = BuildOrchestrator(
        arch="x86_64",
        config_path="configs/global_build.json",
        mode="mock",
    )
    result = orchestrator.run_build(str(output))
    assert Path(result).exists()
    assert Path(str(result) + ".sha256").exists()
