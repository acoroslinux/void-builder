import pytest
from void_builder.core.config_loader import Config, ConfigAssembler, ConfigLoader
from void_builder.core.path_utils import resolve_from_project


def test_config_dot_notation():
    data = {
        "system": {
            "iso_label": "VOID_TEST",
            "workdir_base": "workdir",
        },
        "iso": {
            "compression_type": "xz",
        },
    }
    cfg = Config(data)
    assert cfg.get("system.iso_label") == "VOID_TEST"
    assert cfg.get("system.workdir_base") == "workdir"
    assert cfg.get("iso.compression_type") == "xz"
    assert cfg.get("nonexistent.key", "default") == "default"


def test_config_assembler_assemble():
    assembler = ConfigAssembler("configs")
    cfg = assembler.assemble("x86_64")
    assert cfg is not None
    assert cfg.get("system.iso_label") == "VOID_MODERN"
    official_pkgs = cfg.get("package_sources.official", [])
    assert "base-system" in official_pkgs


def test_config_assembler_validate():
    assembler = ConfigAssembler("configs")
    report = assembler.validate("x86_64", target_desktop="xfce")
    assert report["valid"] is True
    assert "errors" in report
    assert len(report["errors"]) == 0
    assert report["summary"]["target_arch"] == "x86_64"
    assert report["summary"]["desktop"] == "xfce"


def test_config_assembler_validate_invalid_desktop():
    assembler = ConfigAssembler("configs")
    report = assembler.validate("x86_64", target_desktop="nonexistent_desktop_12345")
    assert report["valid"] is False
    assert any("nonexistent_desktop_12345" in err for err in report["errors"])
