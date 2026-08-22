import unittest
import tempfile
import json
import tarfile
import struct
from pathlib import Path

from void_builder.core.verifier import ImageVerifier, VerificationReport


class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_verify_checksums_and_manifest(self):
        test_file = self.dir_path / "test.iso"
        test_file.write_bytes(b"HELLO_WORLD_TEST_ISO_DATA")

        # Create checksum and manifest
        import hashlib
        h = hashlib.sha256(test_file.read_bytes()).hexdigest()
        (self.dir_path / "test.iso.sha256").write_text(f"{h}  test.iso\n")
        (self.dir_path / "test.iso.manifest.json").write_text(json.dumps({"format": "iso", "size": len(test_file.read_bytes())}))

        report = VerificationReport(test_file)
        ImageVerifier.verify_file_checksums(test_file, report)
        self.assertTrue(report.all_passed)
        self.assertEqual(report.metadata.get("sha256"), h)

    def test_verify_tarball(self):
        tar_path = self.dir_path / "rootfs.tar.xz"
        with tarfile.open(tar_path, "w:xz") as tar:
            # Add core directories
            for d in ["etc", "bin", "usr", "var", "root", "home", "proc", "sys", "dev"]:
                ti = tarfile.TarInfo(d)
                ti.type = tarfile.DIRTYPE
                tar.addfile(ti)

            # Add pkgdb
            pkgdb_info = tarfile.TarInfo("var/db/xbps/pkgdb-0.38.plist")
            pkgdb_data = b"<plist version=\"1.0\"></plist>"
            pkgdb_info.size = len(pkgdb_data)
            from io import BytesIO
            tar.addfile(pkgdb_info, BytesIO(pkgdb_data))

            # Add shadow
            shadow_info = tarfile.TarInfo("etc/shadow")
            shadow_data = b"root:*:19000:0:99999:7:::\n"
            shadow_info.size = len(shadow_data)
            shadow_info.mode = 0o600
            tar.addfile(shadow_info, BytesIO(shadow_data))

        report = ImageVerifier.verify_tarball(tar_path)
        self.assertTrue(report.all_passed)

    def test_verify_platform(self):
        test_file = self.dir_path / "test.iso"
        test_file.write_bytes(b"VOID_PLATFORM_TEST")
        report = ImageVerifier.verify_platform("pinebookpro", test_file)
        self.assertTrue(any("Pinebook Pro" in c.name for c in report.checks))


if __name__ == "__main__":
    unittest.main()
