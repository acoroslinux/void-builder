"""
users.py - User management module for void_builder.

Creates users and sets passwords inside the rootfs,
mirroring the approach from mkrootfs.sh and installer.sh.
"""

import os

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.lib import info_msg, warn_msg, error_msg


class UsersModule(ChrootModule):
    """Manages user creation and password setting inside the rootfs."""

    def __init__(self, config):
        super().__init__(config)
        self.users = self.config.get("users", [])
        self.root_password = self.config.get("root_password", None)

    def run(self):
        # Set root password if specified
        if self.root_password:
            self.set_root_password(self.root_password)

        if not self.users:
            info_msg("No additional users to create.")
            return

        info_msg(f"Creating {len(self.users)} user(s)...")

        for user in self.users:
            username = user.get("name")
            if not username:
                continue

            info_msg(f"Creating user: {username}")

            # Check if user already exists
            rc, _, _ = self.run_in_chroot(f"id {username}", check=False)
            if rc == 0:
                warn_msg(f"User {username} already exists")
            else:
                # Create user
                groups = user.get("groups", [])
                groups_str = f"-G {\" ,\".join(groups)}" if groups else ""
                shell = user.get("shell", "/bin/bash")

                cmd = f"useradd -m -s {shell} {groups_str} {username}"
                rc, _, stderr = self.run_in_chroot(cmd, check=False)
                if rc != 0:
                    error_msg(f"Failed to create {username}: {stderr}")
                    continue
                info_msg(f"Created user {username}")

            # Set password if provided
            password = user.get("password")
            if password:
                rc, _, _ = self.run_in_chroot(
                    f"echo '{username}:{password}' | chpasswd -c SHA512",
                    check=False)
                if rc == 0:
                    info_msg(f"Set password for {username}")
                else:
                    warn_msg(f"Failed to set password for {username}")

        # Clean up lock files
        lock = os.path.join(self.output_dir, "etc", ".pwd.lock")
        if os.path.exists(lock):
            os.remove(lock)

