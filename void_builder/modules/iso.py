"""
iso.py - ISO image generation module for void_builder.

Creates a bootable ISO image using:
  - mksquashfs to compress the rootfs
  - xorriso to create the ISO with hybrid boot support

Mirrors the ISO generation from mklive.sh.
"""

import os
import shutil
import subprocess

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner
from void_builder.utils.lib import (
    info_msg, warn_msg, error_msg, ensure_dir, get_tools_dir,
)


class IsoModule(ChrootModule):
    """Generates bootable ISO images."""

    def __init__(self, config):
        super().__init__(config)
        self.iso_name = self.config.get("name", "void-custom")
        self.iso_version = self.config.get("version", "1.0")
        self.iso_output = self.config.get(
            "iso_output",
            f"{self.iso_name}-{self.iso_version}-{self.arch}.iso"
        )
        self.iso_dir = f"{self.output_dir}_iso"
        self.squashfs_compression = self.config.get("squashfs_compression", "xz")

    def _create_squashfs(self):
        """Create squashfs image of the rootfs."""
        info_msg("Creating squashfs image...")
        liveos_dir = ensure_dir(os.path.join(self.iso_dir, "LiveOS"))
        squashfs_file = os.path.join(liveos_dir, "squashfs.img")

        if os.path.exists(squashfs_file):
            os.remove(squashfs_file)

        cmd = [
            "mksquashfs", self.output_dir, squashfs_file,
            "-comp", self.squashfs_compression,
            "-b", "1M", "-noappend",
        ]

        rc, _, stderr = CommandRunner.run(cmd, check=False, stream=True)
        if rc != 0:
            raise RuntimeError(f"Failed to create squashfs: {stderr}")

        info_msg(f"Squashfs created: {squashfs_file}")
        return squashfs_file


    def _create_iso(self):
        """Create the ISO image using xorriso."""
        info_msg(f"Creating ISO image: {self.iso_output}")

        # Build xorriso command
        cmd = [
            "xorriso",
            "-as", "mkisofs",
            "-iso-level", "3",
            "-rock", "-joliet", "-joliet-long",
            "-max-iso9660-filenames",
            "-omit-period", "-omit-version-number",
            "-relaxed-filenames", "-allow-lowercase",
            "-volid", "VOID_LIVE",
        ]

        # Add BIOS boot options if ISOLINUX is present
        isolinux_dir = os.path.join(self.iso_dir, "boot", "isolinux")
        if os.path.exists(os.path.join(isolinux_dir, "isolinux.bin")):
            cmd.extend([
                "-eltorito-boot", "boot/isolinux/isolinux.bin",
                "-eltorito-catalog", "boot/isolinux/boot.cat",
                "-no-emul-boot",
                "-boot-load-size", "4",
                "-boot-info-table",
            ])

        # Add EFI boot options if GRUB EFI is present
        efiboot_img = os.path.join(self.iso_dir, "boot", "grub", "efiboot.img")
        if os.path.exists(efiboot_img):
            cmd.extend([
                "-eltorito-alt-boot",
                "-e", "boot/grub/efiboot.img",
                "-no-emul-boot",
                "-isohybrid-gpt-basdat",
                "-isohybrid-apm-hfsplus",
            ])

        cmd.extend(["-output", self.iso_output, self.iso_dir])

        rc, _, stderr = CommandRunner.run(cmd, check=False, stream=True)
        if rc != 0:
            raise RuntimeError(f"Failed to create ISO: {stderr}")

        info_msg(f"ISO created: {self.iso_output}")

    def run(self):
        """Generate the complete ISO image."""
        info_msg(f"Building ISO: {self.iso_output}")

        try:
            # Create squashfs
            self._create_squashfs()

            # Create ISO
            self._create_iso()

            info_msg("ISO generation complete")

        except Exception as e:
            error_msg(f"ISO generation failed: {e}")
            raise

