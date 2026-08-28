import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("disk_engine")

class DiskEngine:
    def __init__(self, workdir: Path, target_root: Path, output_name: str, config: Dict[str, Any], mode: str, toolchain: Optional[Any] = None, arch: str = "x86_64"):
        self.workdir = Path(workdir).resolve()
        self.target_root = Path(target_root).resolve()
        self.output_name = output_name
        self.config = config
        self.mode = mode
        self.toolchain = toolchain
        self.arch = arch

    def _calculate_image_size(self, rootfs: Path) -> int:
        if self.mode == "mock":
            return 1024
        out = subprocess.check_output(["du", "-sm", str(rootfs)])
        return int(out.split()[0]) + 600

    def build_disk_image(self, target_format: str = "img") -> Path:
        out_path = self.workdir.parent.parent / "output" / f"{self.output_name}.img"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if self.mode == "mock":
            out_path.touch()
            return out_path
            
        # 1. Prepare Bootloader (GRUB EFI) in a staging dir
        efi_staging = self.target_root / "tmp" / "efi_staging"
        if efi_staging.exists():
            shutil.rmtree(efi_staging)
        efi_staging.mkdir(parents=True, exist_ok=True)
        
        if self.arch not in ("rpi-aarch64", "rpi-armv7l", "rpi-armv6l", "pinebookpro"):
            logger.info("Installing GRUB into staging directory...")
            from void_builder.utils.lib import mount_pseudofs, umount_pseudofs, run_cmd_chroot
            try:
                mount_pseudofs(str(self.target_root))
                
                grub_target = "x86_64-efi"
                if self.arch == "i686":
                    grub_target = "i386-efi"
                elif self.arch.startswith("aarch64") or self.arch in ("asahi", "x13s"):
                    grub_target = "arm64-efi"
                elif self.arch.startswith("arm"):
                    grub_target = "arm-efi"
                
                run_cmd_chroot(
                    str(self.target_root),
                    f"grub-install --target={grub_target} --efi-directory=/tmp/efi_staging --bootloader-id=BOOT --removable --no-nvram",
                    check=True
                )
                run_cmd_chroot(str(self.target_root), "grub-mkconfig -o /boot/grub/grub.cfg", check=True)
                
                if self.arch in ("asahi", "x13s"):
                    kernel_pkg = "linux-asahi" if self.arch == "asahi" else "linux"
                    run_cmd_chroot(str(self.target_root), f"xbps-reconfigure -f {kernel_pkg}", check=False)
            finally:
                umount_pseudofs(str(self.target_root))
        elif self.arch.startswith("rpi"):
            chroot_boot = self.target_root / "boot"
            if chroot_boot.exists():
                subprocess.run(["cp", "-rL", f"{chroot_boot}/.", f"{efi_staging}/"], check=False)
            
            cmdline_content = f"console=serial0,115200 console=tty1 root=LABEL=void_root rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait\n"
            (efi_staging / "cmdline.txt").write_text(cmdline_content)
            (self.target_root / "boot" / "cmdline.txt").write_text(cmdline_content)
            
            config_txt = efi_staging / "config.txt"
            if not config_txt.exists():
                config_content = (
                    "# Void Linux Raspberry Pi Boot Config\n"
                    "arm_64bit=1\n"
                    "enable_uart=1\n"
                    "dtoverlay=vc4-kms-v3d\n"
                    "disable_overscan=1\n"
                    "gpu_mem=64\n"
                )
                config_txt.write_text(config_content)
        
        # 2. Update /etc/fstab with generic UUIDs
        root_uuid = "4f68bce3-e8ce-4773-8ce8-7bb7f902ac29"
        boot_uuid = "4F68-BCE3"
        
        fstab_path = self.target_root / "etc" / "fstab"
        if self.arch.startswith("rpi") or self.arch == "pinebookpro":
            fstab_content = f"UUID={root_uuid} / ext4 defaults,noatime 0 1\nUUID={boot_uuid} /boot vfat defaults 0 2\n"
        else:
            fstab_content = f"UUID={root_uuid} / ext4 defaults,noatime 0 1\nUUID={boot_uuid} /boot/efi vfat defaults 0 2\n"
        fstab_path.write_text(fstab_content)
        
        # 3. Calculate sizes
        rootfs_size = self._calculate_image_size(self.target_root)
        
        if self.arch.startswith("rpi") or self.arch == "pinebookpro" or self.arch in ("asahi", "x13s"):
            efi_size = 256
            if self.arch == "pinebookpro":
                efi_size = 512
        else:
            efi_size = 256

        total_size = rootfs_size + efi_size + 4
        
        efi_img = self.workdir / "efi.img"
        root_img = self.workdir / "root.img"
        
        logger.info(f"Generating root filesystem ({rootfs_size} MB)...")
        if self.toolchain:
            self.toolchain.run_in_build_host(["truncate", "-s", f"{rootfs_size}M", str(root_img)], check=True)
            self.toolchain.run_in_build_host(["mke2fs", "-t", "ext4", "-L", "void_root", "-U", root_uuid, "-d", str(self.target_root), str(root_img)], check=True)
        else:
            subprocess.run(["truncate", "-s", f"{rootfs_size}M", str(root_img)], check=True)
            subprocess.run(["mke2fs", "-t", "ext4", "-L", "void_root", "-U", root_uuid, "-d", str(self.target_root), str(root_img)], check=True)
            
        logger.info(f"Generating FAT32 EFI filesystem ({efi_size} MB)...")
        if self.toolchain:
            self.toolchain.run_in_build_host(["truncate", "-s", f"{efi_size}M", str(efi_img)], check=True)
            self.toolchain.run_in_build_host(["mkfs.fat", "-F", "32", "-n", "VOID_BOOT", "-i", boot_uuid.replace("-", ""), str(efi_img)], check=True)
            self.toolchain.run_in_build_host(["mcopy", "-s", "-i", str(efi_img), f"{efi_staging}/*", "::/"], check=False)
        else:
            subprocess.run(["truncate", "-s", f"{efi_size}M", str(efi_img)], check=True)
            subprocess.run(["mkfs.fat", "-F", "32", "-n", "VOID_BOOT", "-i", boot_uuid.replace("-", ""), str(efi_img)], check=True)
            subprocess.run(f"mcopy -s -i {efi_img} {efi_staging}/* ::/", shell=True, check=False)

        logger.info(f"Building partitioned disk image ({total_size} MB)...")
        if self.arch.startswith("rpi") or self.arch in ("asahi", "x13s"):
            subprocess.run(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mktable", "msdos"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "primary", "fat32", "1MiB", f"{efi_size+1}MiB"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "set", "1", "boot", "on"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "primary", "ext4", f"{efi_size+1}MiB", "100%"], check=True)
            subprocess.run(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=1", "conv=notrunc", "status=none"], check=True)
            subprocess.run(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+1}", "conv=notrunc", "status=none"], check=True)
        elif self.arch == "pinebookpro":
            subprocess.run(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mktable", "gpt"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "BootFS", "fat32", "16MiB", f"{efi_size+16}MiB"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "set", "1", "legacy_boot", "on"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "RootFS", "ext4", f"{efi_size+16}MiB", "100%"], check=True)
            subprocess.run(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=16", "conv=notrunc", "status=none"], check=True)
            subprocess.run(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+16}", "conv=notrunc", "status=none"], check=True)
            
            logger.info("Flashing Pinebook Pro U-Boot...")
            uboot_dir = self.target_root / "usr" / "lib" / "pinebookpro-uboot"
            if uboot_dir.exists():
                subprocess.run(["dd", f"if={uboot_dir}/idbloader.img", f"of={out_path}", "bs=512", "seek=64", "conv=notrunc,fsync"], check=True)
                subprocess.run(["dd", f"if={uboot_dir}/u-boot.itb", f"of={out_path}", "bs=512", "seek=16384", "conv=notrunc,fsync"], check=True)
            else:
                logger.warning("U-Boot binaries not found in /usr/lib/pinebookpro-uboot!")
        else:
            subprocess.run(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mktable", "gpt"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "ESP", "fat32", "1MiB", f"{efi_size+1}MiB"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "set", "1", "esp", "on"], check=True)
            subprocess.run(["parted", "-s", str(out_path), "mkpart", "primary", "ext4", f"{efi_size+1}MiB", "100%"], check=True)
            subprocess.run(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=1", "conv=notrunc", "status=none"], check=True)
            subprocess.run(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+1}", "conv=notrunc", "status=none"], check=True)

        final_out = out_path
        if target_format != "img":
            vm_out = out_path.with_name(f"{self.output_name}.{target_format}")
            logger.info(f"Converting raw disk image to VM format: {target_format}...")
            if self.toolchain:
                self.toolchain.run_in_build_host(["qemu-img", "convert", "-f", "raw", "-O", target_format, str(out_path), str(vm_out)], check=True)
            else:
                subprocess.run(["qemu-img", "convert", "-f", "raw", "-O", target_format, str(out_path), str(vm_out)], check=True)
            out_path.unlink()
            final_out = vm_out
            out_path = final_out

        compression = self.config.get("compression", "zstd")
        if self.config.get("compress_image", False):
            logger.info(f"Compressing disk image with {compression}...")
            final_path = out_path
            if compression == "xz":
                cmd = ["xz", "-z9", "-T0", str(out_path)]
                final_path = Path(f"{out_path}.xz")
            elif compression in ("gz", "gzip"):
                cmd = ["gzip", "-9", str(out_path)]
                final_path = Path(f"{out_path}.gz")
            else:
                zstd_level = "-3" if self.config.get("fast_mode", False) else "-19"
                cmd = ["zstd", zstd_level, "-f", "-T0", "-q", "--rm", str(out_path)]
                final_path = Path(f"{out_path}.zst")
                
            if self.toolchain:
                self.toolchain.run_in_build_host(cmd, check=True)
            else:
                subprocess.run(cmd, check=True)
                
            out_path = final_path
            
        logger.info(f"Disk image generated successfully at {out_path}")
        return out_path
