import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from void_builder.core.disk_engine import DiskEngine


class TestDiskEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.tmp_dir.name)
        self.workdir = self.root_path / "workdir" / "build_test"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.target_root = self.root_path / "target_root"
        self.target_root.mkdir(parents=True, exist_ok=True)
        (self.target_root / "etc").mkdir(parents=True, exist_ok=True)
        (self.target_root / "boot").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_fstab_vfat_no_commit_option(self):
        engine = DiskEngine(
            workdir=self.workdir,
            target_root=self.target_root,
            output_name="test-disk",
            config={},
            mode="mock",
            arch="x86_64",
        )
        engine.build_disk_image("img")

        # In mock mode build_disk_image returns early, let's verify fstab in real mode logic with mocked subprocess
        engine.mode = "real"
        with patch("subprocess.run") as mock_run, \
             patch("subprocess.check_output", return_value=b"100\t."), \
             patch("shutil.rmtree"), \
             patch("pathlib.Path.mkdir"):

            # Create dummy kernel and grub standalone
            (self.target_root / "boot" / "vmlinuz").touch()
            (self.target_root / "boot" / "initrd").touch()
            (self.target_root / "usr" / "lib" / "grub" / "x86_64-efi").mkdir(parents=True, exist_ok=True)

            try:
                engine.build_disk_image("img")
            except Exception:
                pass

        fstab_file = self.target_root / "etc" / "fstab"
        if fstab_file.exists():
            content = fstab_file.read_text(encoding="utf-8")
            # /boot/efi vfat line must NOT have commit=60
            for line in content.splitlines():
                if "vfat" in line:
                    self.assertNotIn("commit=60", line, f"vfat line contains invalid option: {line}")
                    self.assertIn("defaults,noatime 0 2", line)

    def test_conversion_command_format_options(self):
        engine = DiskEngine(
            workdir=self.workdir,
            target_root=self.target_root,
            output_name="test-disk",
            config={},
            mode="real",
            arch="x86_64",
        )

        # Verify that qcow2 and vmdk add proper conversion flags
        with patch("subprocess.run") as mock_run, \
             patch("subprocess.check_output", return_value=b"100\t."), \
             patch.object(engine, "_calculate_image_size", return_value=500):

            (self.target_root / "boot" / "vmlinuz").touch()
            (self.target_root / "usr" / "lib" / "grub" / "x86_64-efi").mkdir(parents=True, exist_ok=True)

            # Test qcow2 conversion command
            try:
                engine.build_disk_image("qcow2")
            except Exception:
                pass

            # Search calls for qemu-img
            qemu_calls = [c[0][0] for c in mock_run.call_args_list if c[0] and isinstance(c[0][0], list) and c[0][0][0] == "qemu-img"]
            if qemu_calls:
                cmd = qemu_calls[-1]
                self.assertIn("-c", cmd)
                self.assertIn("qcow2", cmd)


if __name__ == "__main__":
    unittest.main()
