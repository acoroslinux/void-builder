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


    def test_config_assembler_comma_separated_profiles(self):
        assembler = ConfigAssembler("configs")
        cfg = assembler.assemble("x86_64", package_profiles=["desktop-essentials,internet"])
        self.assertIsNotNone(cfg)
        official_pkgs = cfg.get("package_sources.official", [])
        self.assertIn("octoxbps", official_pkgs)  # from desktop-essentials
        self.assertIn("firefox", official_pkgs)    # from internet

    def test_config_assembler_presets(self):
        assembler = ConfigAssembler("configs")
        cfg = assembler.assemble("x86_64", preset="minimal")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.get("boot_title"), "Void Linux Minimal")
        self.assertEqual(cfg.get("customizations.hostname"), "void-minimal")

        # Test developer preset
        cfg_dev = assembler.assemble("x86_64", preset="developer")
        official_pkgs = cfg_dev.get("package_sources.official", [])
        self.assertIn("rust", official_pkgs)
        self.assertIn("git", official_pkgs)

        # Test gaming preset (auto enables multilib and nonfree)
        cfg_game = assembler.assemble("x86_64", preset="gaming")
        repos = cfg_game.get("repositories", [])
        self.assertTrue(any("multilib" in r for r in repos))

    def test_config_assembler_direct_overrides(self):
        assembler = ConfigAssembler("configs")
        cfg = assembler.assemble(
            "x86_64",
            hostname="my-custom-host",
            locale="pt_PT.UTF-8",
            timezone="Europe/Lisbon",
            keymap="pt-latin1",
            root_password="secretpassword",
            boot_title="My Custom Distro",
            iso_label="MY_VOID",
            extra_kernel_args="quiet loglevel=3",
            ssh_keys=["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA test@host"],
        )
        self.assertEqual(cfg.get("customizations.hostname"), "my-custom-host")
        self.assertEqual(cfg.get("customizations.locale"), "pt_PT.UTF-8")
        self.assertEqual(cfg.get("customizations.timezone"), "Europe/Lisbon")
        self.assertEqual(cfg.get("customizations.keymap"), "pt-latin1")
        self.assertEqual(cfg.get("customizations.root_password"), "secretpassword")
        self.assertEqual(cfg.get("boot_title"), "My Custom Distro")
        self.assertEqual(cfg.get("system.iso_label"), "MY_VOID")
        self.assertIn("loglevel=3", cfg.get("boot_cmdline"))
        self.assertEqual(len(cfg.get("customizations.ssh_keys")), 1)

    def test_config_assembler_validate_preset(self):
        assembler = ConfigAssembler("configs")
        report = assembler.validate("x86_64", preset="rescue-sysadmin")
        self.assertTrue(report["valid"])

        report_invalid = assembler.validate("x86_64", preset="nonexistent_preset_999")
        self.assertFalse(report_invalid["valid"])
        self.assertTrue(any("nonexistent_preset_999" in err for err in report_invalid["errors"]))


if __name__ == "__main__":
    unittest.main()

