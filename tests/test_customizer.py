import tempfile
import unittest
from pathlib import Path
from void_builder.core.chroot_manager import ChrootManager
from void_builder.core.customizer import (
    SystemConfigurator,
    RootPasswordAction,
    SSHKeyAction,
    HookAction,
    ServiceAction,
)
from void_builder.core.config_loader import Config


class DummyToolchain:
    def __init__(self):
        self.mode = "mock"


class TestCustomizer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chroot_path = Path(self.temp_dir.name)
        self.toolchain = DummyToolchain()
        self.chroot = ChrootManager(
            chroot_path=self.chroot_path,
            toolchain=self.toolchain,
            mode="mock",
            arch="x86_64",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_root_password_action_mock(self):
        action_pwd = RootPasswordAction(password="test1234")
        action_pwd.execute(self.chroot, self.chroot_path)

        action_lock = RootPasswordAction(lock=True)
        action_lock.execute(self.chroot, self.chroot_path)

    def test_ssh_key_action_mock(self):
        keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA test@host"]
        action = SSHKeyAction(ssh_keys=keys, target_users=["root", "live"])
        action.execute(self.chroot, self.chroot_path)

    def test_hook_action_mock(self):
        hook_script = self.chroot_path / "post_install_hook.sh"
        hook_script.write_text("#!/bin/sh\necho hello\n")
        action = HookAction(stage="post-install", script_path=str(hook_script), in_chroot=True)
        action.execute(self.chroot, self.chroot_path)

    def test_configurator_service_conflict_resolution(self):
        cfg_data = {
            "customizations": {
                "services": ["NetworkManager", "dhcpcd", "sshd"],
                "root_password": "secret_root_pass",
                "ssh_keys": ["ssh-rsa AAAA..."],
            }
        }
        config = Config(cfg_data)
        configurator = SystemConfigurator(self.chroot)
        configurator.load_from_config(config)

        # Ensure ServiceAction omitted dhcpcd due to NetworkManager
        service_actions = [a for a in configurator.actions if isinstance(a, ServiceAction)]
        self.assertEqual(len(service_actions), 1)
        self.assertIn("NetworkManager", service_actions[0].services)
        self.assertNotIn("dhcpcd", service_actions[0].services)
        self.assertIn("sshd", service_actions[0].services)

        # Check RootPasswordAction and SSHKeyAction were loaded
        root_actions = [a for a in configurator.actions if isinstance(a, RootPasswordAction)]
        self.assertEqual(len(root_actions), 1)
        self.assertEqual(root_actions[0].password, "secret_root_pass")

        ssh_actions = [a for a in configurator.actions if isinstance(a, SSHKeyAction)]
        self.assertEqual(len(ssh_actions), 1)

        # Apply in mock mode
        configurator.apply()


if __name__ == "__main__":
    unittest.main()
