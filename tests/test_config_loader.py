import unittest
from void_builder.core.config_loader import Config, ConfigAssembler, ConfigLoader
from void_builder.core.path_utils import resolve_from_project


class TestConfigLoader(unittest.TestCase):
    def test_config_dot_notation(self):
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
        self.assertEqual(cfg.get("system.iso_label"), "VOID_TEST")
        self.assertEqual(cfg.get("system.workdir_base"), "workdir")
        self.assertEqual(cfg.get("iso.compression_type"), "xz")
        self.assertEqual(cfg.get("nonexistent.key", "default"), "default")

    def test_config_assembler_assemble(self):
        assembler = ConfigAssembler("configs")
        cfg = assembler.assemble("x86_64")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.get("system.iso_label"), "VOID_MODERN")
        official_pkgs = cfg.get("package_sources.official", [])
        self.assertIn("base-system", official_pkgs)

    def test_config_assembler_validate(self):
        assembler = ConfigAssembler("configs")
        report = assembler.validate("x86_64", target_desktop="xfce")
        self.assertTrue(report["valid"])
        self.assertIn("errors", report)
        self.assertEqual(len(report["errors"]), 0)
        self.assertEqual(report["summary"]["target_arch"], "x86_64")
        self.assertEqual(report["summary"]["desktop"], "xfce")

    def test_config_assembler_validate_invalid_desktop(self):
        assembler = ConfigAssembler("configs")
        report = assembler.validate("x86_64", target_desktop="nonexistent_desktop_12345")
        self.assertFalse(report["valid"])
        self.assertTrue(any("nonexistent_desktop_12345" in err for err in report["errors"]))


if __name__ == "__main__":
    unittest.main()
