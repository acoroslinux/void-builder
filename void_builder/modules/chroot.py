import os
from void_builder.core.base_module import BaseModule
from void_builder.utils.command import CommandRunner

class ChrootModule(BaseModule):
    def __init__(self, config):
        super().__init__(config)
        self.output_dir = self.config.get('output_dir', './output')
        self.tools_dir = os.path.join(os.path.dirname(__file__), '..', 'tools')
        self.proot_bin = os.path.join(self.tools_dir, 'proot')

    def run_in_chroot(self, command, env=None):
        """Runs a command inside the rootfs using proot."""
        if not os.path.exists(self.proot_bin):
            raise FileNotFoundError(f"proot not found at {self.proot_bin}")

        proot_cmd = [
            self.proot_bin,
            '-r', self.output_dir,
            '-0', # Run as root
            '-w', '/', # Set working directory to /
            '-b', '/dev',
            '-b', '/sys',
            '-b', '/proc',
            '/bin/sh', '-c', command
        ]
        
        print(f"Running in chroot: {command}")
        return CommandRunner.run(proot_cmd, env=env)

    def run(self):
        # This module is meant to be inherited or used as a utility
        pass
