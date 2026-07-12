"""
initramfs.py - Initramfs generation module for void_builder.

Generates the initramfs using dracut with Void-specific modules:
  - vmklive: Live CD support (user creation, locale, autologin)
  - autoinstaller: Automatic installation support
  - dmsquash-live: SquashFS-based live root

Mirrors the dracut invocation from mklive.sh.
"""

import os
import shutil

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner
from void_builder.utils.lib import (
    info_msg, warn_msg, error_msg,
    get_mklive_dir, get_tools_dir, ensure_dir,
)


class InitramfsModule(ChrootModule):
    """Generates initramfs with Void-specific dracut modules."""

    def __init__(self, config):
        super().__init__(config)
        self.compression = self.config.get("initramfs_compression", "xz")
        self.extra_dracut_modules = self.config.get("dracut_modules", [])

    def _find_kernel_version(self):
        """Find the installed kernel version."""
        modules_dir = os.path.join(self.output_dir, "usr", "lib", "modules")
        if not os.path.isdir(modules_dir):
            return None
        versions = [d for d in os.listdir(modules_dir)
                    if os.path.isdir(os.path.join(modules_dir, d))]
        return versions[0] if versions else None

    def _install_dracut_modules(self):
        """Copy Void dracut modules from void-mklive into the rootfs."""
        mklive_dir = get_mklive_dir()
        dracut_modules_dir = os.path.join(
            self.output_dir, "usr", "lib", "dracut", "modules.d"
        )
        ensure_dir(dracut_modules_dir)

        # Copy vmklive module
        src = os.path.join(mklive_dir, "dracut", "vmklive")
        dest = os.path.join(dracut_modules_dir, "01vmklive")
        if os.path.isdir(src):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            info_msg("Installed dracut module: vmklive")
        else:
            warn_msg(f"vmklive module not found at {src}")

        # Copy autoinstaller module
        src = os.path.join(mklive_dir, "dracut", "autoinstaller")
        dest = os.path.join(dracut_modules_dir, "01autoinstaller")
        if os.path.isdir(src):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            info_msg("Installed dracut module: autoinstaller")
        else:
            warn_msg(f"autoinstaller module not found at {src}")


    def _ensure_dracut_packages(self):
        """Install dracut and dependencies into the rootfs."""
        info_msg("Ensuring dracut and dependencies are installed...")
        dracut_pkgs = [
            "dracut", "dracut-network", "eudev",
            "libcap-ng", "linux", "findutils",
            "cryptsetup", "device-mapper",
            "coreutils", "util-linux",
        ]
        try:
            self.run_xbps_install(dracut_pkgs)
        except Exception as e:
            warn_msg(f"Some dracut packages may already be installed: {e}")

    def _build_dracut_command(self, kernel_version):
        """Build the dracut command line."""
        # Compression flag
        comp_flags = {
            "xz": "--xz",
            "gzip": "--gzip",
            "lz4": "--lz4",
            "bzip2": "--bzip2",
            "zstd": "--zstd",
        }
        comp = comp_flags.get(self.compression, "--xz")

        # Force-add Void-specific modules
        force_add = ["vmklive", "autoinstaller"]
        force_add.extend(self.extra_dracut_modules)

        # Omit problematic modules in chroot/proot environments
        omit = [
            "systemd", "iscsi", "lunmask", "lvm",
            "cifs", "hwdb",
        ]

        # Build command
        cmd_parts = ["dracut", "-N"]  # -N = no kernel
        cmd_parts.append(comp)

        for mod in force_add:
            cmd_parts.extend(["--force-add", mod])

        for mod in omit:
            cmd_parts.extend(["--omit", mod])

        cmd_parts.extend(["--force"])
        cmd_parts.extend(["/boot/initrd", kernel_version])

        return " ".join(cmd_parts)

    def run(self):
        """Generate the initramfs."""
        info_msg("Generating initramfs...")

        # Find kernel version
        kernel_ver = self._find_kernel_version()
        if not kernel_ver:
            error_msg("No kernel found in /usr/lib/modules/")
            error_msg("Cannot generate initramfs without a kernel")
            return

        info_msg(f"Kernel version: {kernel_ver}")

        # Ensure dracut is installed
        self._ensure_dracut_packages()

        # Copy Void dracut modules
        self._install_dracut_modules()

        # Build dracut command
        dracut_cmd = self._build_dracut_command(kernel_ver)
        info_msg(f"Dracut command: {dracut_cmd}")

        # Run dracut inside the chroot
        try:
            self.run_in_chroot(dracut_cmd)
            info_msg("Initramfs generated successfully")
        except Exception as e:
            error_msg(f"Failed to generate initramfs: {e}")
            # Try with more omissions as fallback
            warn_msg("Retrying with additional omissions...")
            fallback_cmd = dracut_cmd.replace(
                "--omit hwdb",
                "--omit \"hwdb udev-rules dmsquash-live dm\""
            )
            try:
                self.run_in_chroot(fallback_cmd)
                info_msg("Initramfs generated (fallback mode)")
            except Exception as e2:
                error_msg(f"Fallback also failed: {e2}")
                raise

