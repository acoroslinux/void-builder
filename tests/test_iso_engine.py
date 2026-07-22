import pytest
from pathlib import Path
from void_builder.core.config_loader import Config, ConfigAssembler
from void_builder.core.iso_engine import ISOBuilder, _ENGINE_REGISTRY
from void_builder.core.chroot_manager import ChrootManager


class DummyToolchain:
    def __init__(self):
        self.mode = "mock"
        self.host_dir = Path("/tmp")
        self.xbps_install_static = Path("/tmp/xbps-install.static")
        self.chroot_manager = ChrootManager(
            chroot_path=Path("/tmp/mock_chroot"),
            toolchain=self,
            mode="mock",
            arch="x86_64",
        )

    def setup(self):
        pass


def test_engine_registry():
    assert "x86_64" in _ENGINE_REGISTRY
    assert "rpi-aarch64" in _ENGINE_REGISTRY
    assert "pinebookpro" in _ENGINE_REGISTRY
    assert "asahi" in _ENGINE_REGISTRY


def test_iso_builder_mock_iso(tmp_path):
    assembler = ConfigAssembler("configs")
    cfg = assembler.assemble("x86_64")
    toolchain = DummyToolchain()
    builder = ISOBuilder("x86_64", cfg, toolchain)

    output_iso = tmp_path / "test.iso"
    result = builder.build(str(output_iso), workdir=str(tmp_path / "workdir"), output_format="iso")
    assert Path(result).exists()
    assert Path(str(result) + ".sha256").exists()
    assert Path(str(result) + ".md5").exists()
    assert Path(str(result) + ".manifest.json").exists()


def test_iso_builder_mock_tarball(tmp_path):
    assembler = ConfigAssembler("configs")
    cfg = assembler.assemble("x86_64")
    toolchain = DummyToolchain()
    builder = ISOBuilder("x86_64", cfg, toolchain)

    output_tarball = tmp_path / "test.tar.xz"
    result = builder.build(str(output_tarball), workdir=str(tmp_path / "workdir"), output_format="tarball")
    assert Path(result).exists()
    assert Path(str(result) + ".manifest.json").exists()
