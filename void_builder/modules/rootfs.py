"""
rootfs.py - Root filesystem builder for void_builder.

Implements the bootstrap sequence from mkrootfs.sh:
  1. Create rootfs directory
  2. Install base packages with xbps-install
  3. Enable locale
  4. 3-pass reconfiguration (host -> chroot base-files -> chroot all)
  5. Set root password
  6. Clean up and optionally compress
"""

import os
import shutil
import tempfile

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner
from void_builder.utils.lib import (
    info_msg, step_msg, warn_msg, error_msg,
    is_target_native, setup_qemu_binfmt,
    mount_pseudofs, umount_pseudofs,
    cleanup_chroot, get_tools_dir, ensure_dir,
)


class RootfsBuilder(ChrootModule):
    """
    Builds a Void Linux root filesystem from scratch.

    Mirrors the bootstrap process from mkrootfs.sh:
    - Installs base packages using xbps-install
    - Performs 3-pass reconfiguration
    - Sets up credentials
    - Optionally compresses to tarball
    """

    STEP_COUNT = 8

    def __init__(self, config):
        super().__init__(config)
        self.base_system = self.config.get("base_system", "base-container-full")
        self.repository = self.config.get(
            "repository", "https://repo-default.voidlinux.org/current"
        )
        self.packages = self.config.get("packages", [])
        self.root_password = self.config.get("root_password", "voidlinux")
        self.compress = self.config.get("compress_rootfs", False)
        self._current_step = 0

    def _step(self, msg):
        self._current_step += 1
        step_msg(self._current_step, self.STEP_COUNT, msg)


    def run(self):
        """Execute the full bootstrap sequence."""
        info_msg(f"Building rootfs for {self.arch}...")
        info_msg(f"Base system: {self.base_system}")
        info_msg(f"Repository: {self.repository}")

        try:
            self._step("Creating rootfs directory")
            ensure_dir(self.output_dir)

            self._step("Setting up QEMU for cross-arch (if needed)")
            if not is_target_native(self.arch):
                if not setup_qemu_binfmt(self.arch):
                    raise RuntimeError(f"QEMU setup failed for {self.arch}")

            self._step("Installing base system packages")
            all_packages = [self.base_system] + self.packages
            pkg_list = ", ".join(all_packages)
            info_msg(f"Packages: {pkg_list}")
            self.run_xbps_install(all_packages, self.repository)

            self._step("Enabling locale (en_US.UTF-8)")
            self.enable_locale()

            self._step("Mounting pseudo-filesystems")
            mount_pseudofs(self.output_dir)

            self._step("3-pass package reconfiguration")
            self.reconfigure_packages()

            self._step("Setting root password")
            self.set_root_password(self.root_password)

            self._step("Cleaning up chroot")
            self.cleanup()
            # Remove cache (will be outdated by the time rootfs is used)
            cache_dir = os.path.join(self.output_dir, "var", "cache")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                ensure_dir(cache_dir)

            if self.compress:
                self._compress_rootfs()

            info_msg(f"Rootfs created successfully at {self.output_dir}")

        except Exception as e:
            error_msg(f"Rootfs build failed: {e}")
            self.cleanup()
            raise


    def _compress_rootfs(self):
        """Compress the rootfs to a tarball (like mkrootfs.sh)."""
        import datetime
        date_str = datetime.datetime.utcnow().strftime("%Y%m%d")
        filename = f"void-{self.arch}-ROOTFS-{date_str}.tar.xz"
        output_file = self.config.get("rootfs_output", filename)

        info_msg(f"Compressing rootfs to {output_file}...")

        # Use tar with xz compression, preserving xattrs
        cmd = [
            "tar", "cp", "--posix",
            "--xattrs", "--xattrs-include=*",
            "-C", self.output_dir, ".",
        ]

        # Pipe to xz
        import subprocess
        with open(output_file, "wb") as outf:
            tar_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE
            )
            xz_proc = subprocess.Popen(
                ["xz", "-T0", "-9"],
                stdin=tar_proc.stdout,
                stdout=outf
            )
            tar_proc.stdout.close()
            xz_proc.communicate()

        if xz_proc.returncode != 0:
            raise RuntimeError("Failed to compress rootfs")

        info_msg(f"Successfully created {output_file}")
        return output_file

