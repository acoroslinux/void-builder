import tempfile
import unittest
from pathlib import Path

from void_builder.core.stage_manager import StageManager, StageManagerError


class TestStageManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workdir = Path(self.temp_dir.name)
        self.stage_manager = StageManager(workdir=self.workdir, mode="mock", arch="x86_64")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_local_tarball(self):
        tar_file = self.workdir / "custom-base.tar.xz"
        tar_file.touch()

        resolved = self.stage_manager.resolve_tarball(str(tar_file))
        self.assertEqual(resolved, tar_file.resolve())

    def test_resolve_auto_tarball_mock(self):
        resolved = self.stage_manager.resolve_tarball("y")
        self.assertTrue(resolved.exists())
        self.assertIn("void-base-x86_64", resolved.name)

    def test_extract_tarball_mock(self):
        tar_file = self.workdir / "base.tar.xz"
        tar_file.touch()
        target_root = self.workdir / "airootfs"

        self.stage_manager.extract_tarball(tar_file, target_root)
        self.assertTrue((target_root / "etc").exists())
        self.assertTrue((target_root / "bin").exists())

    def test_create_stage_tarball_mock(self):
        source_root = self.workdir / "airootfs"
        source_root.mkdir(parents=True, exist_ok=True)
        output_tarball = self.workdir / "output" / "stage-test.tar.xz"

        res = self.stage_manager.create_stage_tarball(source_root, output_tarball)
        self.assertTrue(res.exists())
        self.assertEqual(res, output_tarball)


if __name__ == "__main__":
    unittest.main()
