import tempfile
import unittest
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


class TestISOEngine(unittest.TestCase):
    def test_engine_registry(self):
        self.assertIn("x86_64", _ENGINE_REGISTRY)
        self.assertIn("i686", _ENGINE_REGISTRY)
        self.assertIn("aarch64", _ENGINE_REGISTRY)
        self.assertIn("rpi-aarch64", _ENGINE_REGISTRY)
        self.assertIn("pinebookpro", _ENGINE_REGISTRY)
        self.assertIn("asahi", _ENGINE_REGISTRY)
        self.assertIn("x13s", _ENGINE_REGISTRY)
        self.assertIn("riscv64", _ENGINE_REGISTRY)

    def test_iso_builder_mock_iso(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("x86_64")
            toolchain = DummyToolchain()
            builder = ISOBuilder("x86_64", cfg, toolchain)

            output_iso = tmp_path / "test.iso"
            result = builder.build(str(output_iso), workdir=str(tmp_path / "workdir"), output_format="iso")
            self.assertTrue(Path(result).exists())
            self.assertTrue(Path(str(result) + ".sha256").exists())
            self.assertTrue(Path(str(result) + ".md5").exists())
            self.assertTrue(Path(str(result) + ".manifest.json").exists())

    def test_iso_builder_mock_tarball(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("x86_64")
            toolchain = DummyToolchain()
            builder = ISOBuilder("x86_64", cfg, toolchain)

            output_tarball = tmp_path / "test.tar.xz"
            result = builder.build(str(output_tarball), workdir=str(tmp_path / "workdir"), output_format="tarball")
            self.assertTrue(Path(result).exists())
            self.assertTrue(Path(str(result) + ".manifest.json").exists())

    def test_iso_builder_mock_qcow2(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("x86_64")
            toolchain = DummyToolchain()
            builder = ISOBuilder("x86_64", cfg, toolchain)

            output_qcow2 = tmp_path / "test.qcow2"
            result = builder.build(str(output_qcow2), workdir=str(tmp_path / "workdir"), output_format="qcow2")
            self.assertTrue(Path(result).exists())
            self.assertTrue(str(result).endswith(".qcow2"))
            self.assertTrue(Path(str(result) + ".sha256").exists())
            self.assertTrue(Path(str(result) + ".manifest.json").exists())

    def test_iso_builder_mock_vdi_vmdk(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("x86_64")
            toolchain = DummyToolchain()
            builder = ISOBuilder("x86_64", cfg, toolchain)

            output_vdi = tmp_path / "test.vdi"
            res_vdi = builder.build(str(output_vdi), workdir=str(tmp_path / "workdir"), output_format="vdi")
            self.assertTrue(Path(res_vdi).exists())
            self.assertTrue(str(res_vdi).endswith(".vdi"))

            output_vmdk = tmp_path / "test.vmdk"
            res_vmdk = builder.build(str(output_vmdk), workdir=str(tmp_path / "workdir"), output_format="vmdk")
            self.assertTrue(Path(res_vmdk).exists())
            self.assertTrue(str(res_vmdk).endswith(".vmdk"))

    def test_iso_builder_mock_platform_img(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("rpi-aarch64")
            toolchain = DummyToolchain()
            builder = ISOBuilder("rpi-aarch64", cfg, toolchain)

            output_img = tmp_path / "rpi.img"
            res_img = builder.build(str(output_img), workdir=str(tmp_path / "workdir"), output_format="img")
            self.assertTrue(Path(res_img).exists())
            self.assertTrue(Path(str(res_img) + ".sha256").exists())
            self.assertTrue(Path(str(res_img) + ".manifest.json").exists())

    def test_iso_builder_mock_platform_img_compressed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            assembler = ConfigAssembler("configs")
            cfg = assembler.assemble("rpi-aarch64")
            cfg._data["compress_image"] = True
            cfg._data["compression"] = "xz"
            toolchain = DummyToolchain()
            builder = ISOBuilder("rpi-aarch64", cfg, toolchain)

            output_img = tmp_path / "rpi.img.xz"
            res_img = builder.build(str(output_img), workdir=str(tmp_path / "workdir"), output_format="img")
            self.assertTrue(Path(res_img).exists())
            self.assertTrue(str(res_img).endswith(".xz"))
            self.assertTrue(Path(str(res_img) + ".sha256").exists())
            self.assertTrue(Path(str(res_img) + ".manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
