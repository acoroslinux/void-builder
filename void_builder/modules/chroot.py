"""
chroot.py - Chroot execution environment for void_builder.

Provides a unified interface to run commands inside the rootfs,
supporting both real chroot (root) and proot fallback.
"""

import os
import re
import shutil

from void_builder.core.base_module import BaseModule
from void_builder.utils.command import CommandRunner
from void_builder.utils.lib import (
    info_msg, warn_msg, error_msg,
    is_target_native, setup_qemu_binfmt,
    mount_pseudofs, umount_pseudofs,
    run_cmd_chroot, run_cmd_target,
    cleanup_chroot, get_tools_dir, ensure_dir,
)


class ChrootModule(BaseModule):
    """Manages command execution inside the rootfs."""

    def __init__(self, config):
        super().__init__(config)
        self.output_dir = self.config.get("output_dir", "./output")
        self.arch = self.config.get("architecture", "x86_64")
        self.tools_dir = get_tools_dir()
        self.proot_bin = os.path.join(self.tools_dir, "proot")
        self._chroot_mode = None

    def _detect_chroot_mode(self):
        if self._chroot_mode is not None:
            return self._chroot_mode
        if os.geteuid() == 0:
            self._chroot_mode = "chroot"
            info_msg("Running as root, using native chroot")
        elif shutil.which("proot") or os.path.exists(self.proot_bin):
            self._chroot_mode = "proot"
            info_msg("Not root, using proot as fallback")
        else:
            error_msg("Neither root nor proot available!")
            self._chroot_mode = "none"
        return self._chroot_mode

    def _setup_qemu_if_needed(self):
        if not is_target_native(self.arch):
            info_msg(f"Cross-arch build: host != target ({self.arch})")
            if not setup_qemu_binfmt(self.arch):
                raise RuntimeError(f"Cannot set up QEMU for {self.arch}")

    def run_in_chroot(self, command, env=None, check=True):
        """Run a command inside the rootfs."""
        mode = self._detect_chroot_mode()
        self._setup_qemu_if_needed()
        if mode == "chroot":
            return run_cmd_chroot(self.output_dir, command, env=env, check=check)
        elif mode == "proot":
            proot = self.proot_bin if os.path.exists(self.proot_bin) else "proot"
            proot_cmd = [proot, "-r", self.output_dir, "-0", "-w", "/",
                         "-b", "/dev", "-b", "/sys", "-b", "/proc",
                         "/bin/sh", "-c", command]
            merged_env = os.environ.copy()
            if env:
                merged_env.update(env)
            return CommandRunner.run(proot_cmd, env=merged_env, check=check)
        else:
            raise RuntimeError("No chroot method available")

    def run_xbps_install(self, packages, repository=None, rootfs=None):
        """Run xbps-install to install packages into the rootfs."""
        rootfs = rootfs or self.output_dir
        repository = repository or self.config.get(
            "repository", "https://repo-default.voidlinux.org/current"
        )
        xbps_install = os.path.join(
            self.tools_dir, "usr", "bin", "xbps-install.static"
        )
        if not os.path.exists(xbps_install):
            warn_msg(f"Static xbps-install not found at {xbps_install}")
            xbps_install = "xbps-install"
            if not shutil.which(xbps_install):
                raise FileNotFoundError("xbps-install not found")
        cmd = [xbps_install, "-S", "-r", rootfs, "-R", repository, "-y"
              ] + list(packages)
        env = os.environ.copy()
        env["XBPS_ARCH"] = self.arch
        return CommandRunner.run(cmd, env=env, stream=True)

    def reconfigure_packages(self):
        """3-pass reconfiguration from mkrootfs.sh."""
        info_msg("Pass 1/3: Reconfiguring base-files (from host)...")
        if is_target_native(self.arch):
            if shutil.which("xbps-reconfigure"):
                env = os.environ.copy()
                env["XBPS_ARCH"] = self.arch
                CommandRunner.run(
                    ["xbps-reconfigure", "--rootdir", self.output_dir, "base-files"],
                    env=env, check=False)
        else:
            CommandRunner.run(
                ["xbps-reconfigure", "--rootdir", self.output_dir, "base-files"],
                check=False)
        info_msg("Pass 2/3: Reconfiguring base-files (in chroot)...")
        self.run_in_chroot("env -i xbps-reconfigure -f base-files", check=False)
        info_msg("Pass 3/3: Reconfiguring all packages (in chroot)...")
        self.run_in_chroot("xbps-reconfigure -a", check=False)

    def set_root_password(self, password="voidlinux"):
        """Set the root password inside the rootfs."""
        info_msg("Setting root password...")
        shadow = os.path.join(self.output_dir, "etc", "shadow")
        if not os.path.exists(shadow):
            self.run_in_chroot("pwconv", check=False)
        self.run_in_chroot(
            f"echo 'root:{password}' | chpasswd -c SHA512", check=True)
        lock = os.path.join(self.output_dir, "etc", ".pwd.lock")
        if os.path.exists(lock):
            os.remove(lock)

    def enable_locale(self, locale="en_US.UTF-8"):
        """Enable a locale in libc-locales (glibc only)."""
        lf = os.path.join(self.output_dir, "etc", "default", "libc-locales")
        if os.path.exists(lf):
            info_msg(f"Enabling locale {locale}...")
            with open(lf, "r") as f:
                content = f.read()
            content = re.sub(rf"#({re.escape(locale)}.*)", r"\1", content)
            with open(lf, "w") as f:
                f.write(content)

    def cleanup(self):
        """Clean up chroot environment."""
        cleanup_chroot(self.output_dir)

    def run(self):
        """This module is meant to be inherited, not run directly."""
        pass

