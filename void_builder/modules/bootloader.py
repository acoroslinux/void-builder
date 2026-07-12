"""
bootloader.py - Bootloader setup module for void_builder.

Sets up GRUB (EFI) and ISOLINUX (BIOS) boot support,
mirroring the approach from mklive.sh.
"""

import os
import shutil
import re

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner
from void_builder.utils.lib import (
    info_msg, warn_msg, error_msg, ensure_dir, get_mklive_dir,
)


class BootloaderModule(ChrootModule):
    """Sets up GRUB and ISOLINUX boot support."""

    def __init__(self, config):
        super().__init__(config)
        self.iso_dir = f"{self.output_dir}_iso"
        self.boot_title = self.config.get("boot_title", "Void Linux")
        self.keymap = self.config.get("keymap", "us")
        self.locale = self.config.get("locale", "en_US.UTF-8")
        self.boot_cmdline = self.config.get("boot_cmdline", "")
        self.splash_image = self.config.get("splash_image", "")

    def _find_kernel_version(self):
        """Find kernel version from /boot."""
        boot_dir = os.path.join(self.output_dir, "boot")
        if not os.path.isdir(boot_dir):
            return None
        for f in os.listdir(boot_dir):
            if f.startswith("vmlinuz-"):
                return f.replace("vmlinuz-", "")
        return None


    def _setup_isolinux(self, kernel_ver):
        """Set up ISOLINUX for BIOS/Legacy boot (x86 only)."""
        if not (self.arch.startswith("x86_64") or self.arch.startswith("i686")):
            info_msg("Skipping ISOLINUX (not x86)")
            return

        info_msg("Setting up ISOLINUX for BIOS boot...")
        isolinux_dir = ensure_dir(os.path.join(self.iso_dir, "boot", "isolinux"))
        syslinux_dir = os.path.join(self.output_dir, "usr", "lib", "syslinux")

        if not os.path.isdir(syslinux_dir):
            warn_msg(f"syslinux not found at {syslinux_dir}")
            return

        # Copy syslinux binaries
        for f in ["isolinux.bin", "ldlinux.c32", "libcom32.c32",
                  "vesamenu.c32", "libutil.c32", "chain.c32",
                  "reboot.c32", "poweroff.c32"]:
            src = os.path.join(syslinux_dir, f)
            if os.path.exists(src):
                shutil.copy(src, isolinux_dir)

        # Generate isolinux.cfg from template
        mklive_dir = get_mklive_dir()
        template = os.path.join(mklive_dir, "isolinux", "isolinux.cfg.in")
        if os.path.exists(template):
            with open(template, "r") as f:
                cfg = f.read()
            cfg = cfg.replace("@@SPLASHIMAGE@@", "splash.png")
            cfg = cfg.replace("@@BOOT_TITLE@@", self.boot_title)
            cfg = cfg.replace("@@KERNVER@@", kernel_ver)
            cfg = cfg.replace("@@ARCH@@", self.arch)
            cfg = cfg.replace("@@KEYMAP@@", self.keymap)
            cfg = cfg.replace("@@LOCALE@@", self.locale)
            cfg = cfg.replace("@@BOOT_CMDLINE@@", self.boot_cmdline)
            with open(os.path.join(isolinux_dir, "isolinux.cfg"), "w") as f:
                f.write(cfg)
            info_msg("ISOLINUX configured")

        # Copy splash image
        splash_src = self.splash_image or os.path.join(mklive_dir, "data", "splash.png")
        if os.path.exists(splash_src):
            shutil.copy(splash_src, os.path.join(isolinux_dir, "splash.png"))

    def _setup_grub_efi(self, kernel_ver):
        """Set up GRUB for EFI boot."""
        info_msg("Setting up GRUB for EFI boot...")
        grub_dir = ensure_dir(os.path.join(self.iso_dir, "boot", "grub"))
        mklive_dir = get_mklive_dir()

        # Generate grub_void.cfg from pre + entries + post
        pre_file = os.path.join(mklive_dir, "grub", "grub_void.cfg.pre")
        post_file = os.path.join(mklive_dir, "grub", "grub_void.cfg.post")

        cfg_content = ""
        if os.path.exists(pre_file):
            with open(pre_file, "r") as f:
                cfg_content = f.read()
            cfg_content = cfg_content.replace("@@SPLASHIMAGE@@", "splash.png")

        # Add boot entries
        cfg_content += self._generate_grub_entries(kernel_ver)

        if os.path.exists(post_file):
            with open(post_file, "r") as f:
                cfg_content += f.read()

        with open(os.path.join(grub_dir, "grub_void.cfg"), "w") as f:
            f.write(cfg_content)

        # Copy main grub.cfg
        main_cfg = os.path.join(mklive_dir, "grub", "grub.cfg")
        if os.path.exists(main_cfg):
            shutil.copy(main_cfg, os.path.join(grub_dir, "grub.cfg"))

        info_msg("GRUB EFI configured")


    def _generate_grub_entries(self, kernel_ver):
        """Generate GRUB menu entries."""
        base_append = (
            f"root=live:CDLABEL=VOID_LIVE init=/sbin/init ro "
            f"rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 "
            f"vconsole.unicode=1 vconsole.keymap={self.keymap} "
            f"locale.LANG={self.locale} {self.boot_cmdline}"
        )

        entries = ""
        entries += "\n"
        entries += "menuentry \"Void Linux\" --id linux {\n"
        entries += f"    linux /boot/vmlinuz {base_append}\n"
        entries += "    initrd /boot/initrd\n"
        entries += "}\n"

        entries += "\n"
        entries += "menuentry \"Void Linux (RAM)\" --id linuxram {\n"
        entries += f"    linux /boot/vmlinuz {base_append} rd.live.ram\n"
        entries += "    initrd /boot/initrd\n"
        entries += "}\n"

        entries += "\n"
        entries += "menuentry \"Void Linux (no graphics)\" --id linuxnogfx {\n"
        entries += f"    linux /boot/vmlinuz {base_append} nomodeset\n"
        entries += "    initrd /boot/initrd\n"
        entries += "}\n"

        entries += "\n"
        entries += "menuentry \"Void Linux with speech\" --id linuxa11y {\n"
        entries += f"    linux /boot/vmlinuz {base_append} live.accessibility live.autologin\n"
        entries += "    initrd /boot/initrd\n"
        entries += "}\n"

        return entries

    def _copy_boot_files(self):
        """Copy kernel and initramfs to the ISO directory."""
        boot_dir = os.path.join(self.output_dir, "boot")
        iso_boot = ensure_dir(os.path.join(self.iso_dir, "boot"))

        if not os.path.isdir(boot_dir):
            warn_msg(f"Boot directory not found: {boot_dir}")
            return

        for f in os.listdir(boot_dir):
            if f.startswith("vmlinuz"):
                shutil.copy(os.path.join(boot_dir, f),
                           os.path.join(iso_boot, "vmlinuz"))
            elif f.startswith("initrd") or f == "initrd":
                shutil.copy(os.path.join(boot_dir, f),
                           os.path.join(iso_boot, "initrd"))

        info_msg("Boot files copied to ISO directory")

    def run(self):
        """Set up all bootloader components."""
        info_msg("Setting up bootloader...")

        kernel_ver = self._find_kernel_version()
        if not kernel_ver:
            error_msg("No kernel found in /boot")
            return

        info_msg(f"Kernel version: {kernel_ver}")

        # Copy boot files to ISO directory
        self._copy_boot_files()

        # Set up ISOLINUX (BIOS)
        self._setup_isolinux(kernel_ver)

        # Set up GRUB (EFI)
        self._setup_grub_efi(kernel_ver)

        info_msg("Bootloader setup complete")

