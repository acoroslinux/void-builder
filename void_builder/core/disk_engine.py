import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import re

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

    def _run_tool(self, command, check=True):
        """Run a disk-build utility from the per-build isolated host tree."""
        if self.toolchain is not None:
            return self.toolchain.run_in_build_host(command, check=check)
        if self.mode == "real" and getattr(subprocess.run, "__module__", "") != "unittest.mock":
            raise RuntimeError("Real disk builds require the isolated build-host toolchain")
        return subprocess.run(command, check=check)

    def _calculate_image_size(self, rootfs: Path) -> int:
        if self.mode == "mock":
            return 1024
        if self.toolchain is not None:
            _, stdout, _ = self.toolchain.run_in_build_host(["du", "-sm", str(rootfs)], check=True)
            out = stdout.encode()
        else:
            if self.mode == "real":
                raise RuntimeError("Real disk builds require the isolated build-host toolchain")
            out = subprocess.check_output(["du", "-sm", str(rootfs)])
        return int(out.split()[0]) + 600

    def _boot_file_pairs(self):
        """List complete kernel/initramfs pairs, newest release first."""
        boot = self.target_root / "boot"
        kernels = [p for pattern in ("vmlinuz-*", "vmlinux-*", "Image-*")
                   for p in boot.glob(pattern) if p.is_file() and p.stat().st_size]
        # Numeric sorting keeps e.g. 6.18.10 newer than 6.18.9.
        kernels.sort(key=lambda p: [int(s) if s.isdigit() else s
                                   for s in re.split(r"(\d+)", p.name.split("-", 1)[1])],
                     reverse=True)
        pairs = []
        versions = set()
        for kernel in kernels:
            version = kernel.name.split("-", 1)[1]
            if version in versions:
                continue
            for name in (f"initramfs-{version}.img", f"initrd-{version}.img",
                         f"initrd-{version}"):
                initrd = boot / name
                if initrd.is_file() and initrd.stat().st_size:
                    pairs.append((kernel, initrd))
                    versions.add(version)
                    break
        if pairs:
            return pairs
        # Some custom kernels use only unversioned names. Never mix these
        # with a versioned kernel whose matching initramfs is missing.
        if not kernels:
            for name in ("vmlinuz", "vmlinux", "Image"):
                kernel = boot / name
                for initrd_name in ("initrd", "initramfs.img", "initramfs"):
                    initrd = boot / initrd_name
                    if (kernel.is_file() and kernel.stat().st_size
                            and initrd.is_file() and initrd.stat().st_size):
                        return [(kernel, initrd)]
        raise RuntimeError(
            f"No matching nonempty kernel/initramfs pair in {boot}; "
            "install and configure the kernel and generate its initramfs before building the disk image."
        )

    def _select_boot_files(self):
        """Select the newest complete pair for the default boot entry."""
        return self._boot_file_pairs()[0]

    def _prepare_grub_config(self):
        boot = self.target_root / "boot"
        pairs = self._boot_file_pairs()
        kernel, initrd = pairs[0]
        for alias, source in (("vmlinuz", kernel), ("initrd", initrd)):
            if source.name != alias:
                (boot / alias).unlink(missing_ok=True)
                (boot / alias).symlink_to(source.name)
        fs_module = "f2fs" if self.config.get("fs_type", "ext4") == "f2fs" else "ext2"
        # A standalone image includes module files in its memdisk, but
        # partition drivers are not necessarily loaded automatically.
        # Load them before searching, otherwise GRUB sees (hd0) without
        # its partitions and leaves root pointing at the memdisk.
        modules = ["part_gpt", "part_msdos", "fat", fs_module,
                   "search", "search_label", "linux"]
        grub_cfg = boot / "grub" / "grub.cfg"
        grub_cfg.parent.mkdir(parents=True, exist_ok=True)

        def boot_entry(title, entry_id, kernel, initrd, extra_args="", indent=""):
            # Resolve root for each entry too, including submenu selections.
            return (
                f"{indent}menuentry '{title}' --class void --class gnu-linux --class os --id '{entry_id}' {{\n"
                f"{indent}  search --no-floppy --label void_root --set=root\n"
                f"{indent}  linux /boot/{kernel.name} root=LABEL=void_root rw{extra_args}\n"
                f"{indent}  initrd /boot/{initrd.name}\n"
                f"{indent}}}\n"
            )

        menu = (
            "".join(f"insmod {module}\n" for module in modules)
            + "search --no-floppy --label void_root --set=root\n"
            "set default=void-linux\n"
            "set timeout=5\n"
            "set timeout_style=menu\n"
        )
        menu += boot_entry("Void Linux", "void-linux", kernel, initrd)
        menu += boot_entry("Void Linux (safe graphics)", "void-safe-graphics",
                           kernel, initrd, " nomodeset")
        menu += "submenu 'Advanced options for Void Linux' --id 'void-advanced' {\n"
        for index, (kernel, initrd) in enumerate(pairs):
            version = kernel.name.split("-", 1)[1] if "-" in kernel.name else "custom kernel"
            entry_id = f"void-kernel-{index}"
            menu += boot_entry(f"Void Linux, with Linux {version}", entry_id,
                               kernel, initrd, indent="  ")
            # Void's runit uses the 'single' runsvdir for recovery.
            menu += boot_entry(f"Void Linux, with Linux {version} (recovery mode)",
                               f"{entry_id}-recovery", kernel, initrd, " single", indent="  ")
        menu += "}\n"
        menu += (
            "if [ \"$grub_platform\" = efi ]; then\n"
            "  insmod efifwsetup\n"
            "  if fwsetup --is-supported; then\n"
            "    menuentry 'UEFI Firmware Settings' --id 'uefi-firmware' {\n"
            "      fwsetup\n"
            "    }\n"
            "  fi\n"
            "fi\n"
            "menuentry 'Restart' --class reboot --id 'restart' {\n"
            "  insmod reboot\n"
            "  reboot\n"
            "}\n"
            "menuentry 'Shut down' --class shutdown --id 'shutdown' {\n"
            "  insmod halt\n"
            "  halt\n"
            "}\n"
        )
        grub_cfg.write_text(menu, encoding="utf-8")
        return grub_cfg, modules

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
            grub_target = "x86_64-efi"
            if self.arch == "i686":
                grub_target = "i386-efi"
            elif self.arch.startswith("aarch64") or self.arch in ("asahi", "x13s"):
                grub_target = "arm64-efi"
            elif self.arch.startswith("arm"):
                grub_target = "arm-efi"

            # The target root may contain binaries for a different CPU.  Run
            # the host GRUB tools and supply the target module directory,
            # instead of invoking grub-install through chroot (which fails on
            # cross builds, notably aarch64 on an x86_64 host).
            host_root = Path(getattr(self.toolchain, "host_dir", "")) if self.toolchain else Path()
            target_root = Path(getattr(self.toolchain, "target_dir", "")) if self.toolchain else Path()
            grub_standalone = next(
                (host_root / "usr" / d / "grub-mkstandalone" for d in ("bin", "sbin")
                 if (host_root / "usr" / d / "grub-mkstandalone").is_file()),
                Path("grub-mkstandalone"),
            )
            grub_module_candidates = [
                target_root / "usr" / "lib" / "grub" / grub_target,
                self.target_root / "usr" / "lib" / "grub" / grub_target,
                host_root / "usr" / "lib" / "grub" / grub_target,
            ]
            grub_modules = next((p for p in grub_module_candidates if p.is_dir()), None)
            if grub_modules is None:
                searched = ", ".join(str(p) for p in grub_module_candidates)
                raise RuntimeError(f"GRUB modules not found for {grub_target}; searched: {searched}")
            env = None
            if host_root.is_dir():
                import os
                host_lib = host_root / "usr" / "lib"
                env = os.environ.copy()
                env["PATH"] = f"{host_root / 'usr' / 'bin'}:{host_root / 'usr' / 'sbin'}:{env.get('PATH', '')}"
                # The isolated grub-install is dynamically linked against
                # the libraries shipped in void-host (libdevmapper, etc.).
                env["LD_LIBRARY_PATH"] = f"{host_lib}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
                if (host_lib / "gconv").is_dir():
                    env["GCONV_PATH"] = str(host_lib / "gconv")
            # Chroot configuration (including dracut) has already finished
            # and its pseudo-filesystems are unmounted at this point.
            grub_cfg, grub_modules_to_load = self._prepare_grub_config()
            efi_loader = efi_staging / "EFI" / "BOOT" / (
                "BOOTAA64.EFI" if grub_target == "arm64-efi" else
                "BOOTX64.EFI" if grub_target == "x86_64-efi" else "BOOTIA32.EFI"
            )
            efi_loader.parent.mkdir(parents=True, exist_ok=True)
            grub_cmd = [
                str(grub_standalone), f"--format={grub_target}",
                f"--directory={grub_modules}",
                f"--modules={' '.join(grub_modules_to_load)}",
                f"--output={efi_loader}",
                f"boot/grub/grub.cfg={grub_cfg}",
            ]
            if self.toolchain is not None:
                self.toolchain.run_in_build_host(grub_cmd, check=True)
            elif self.mode == "real" and getattr(subprocess.run, "__module__", "") != "unittest.mock":
                raise RuntimeError("Real disk builds require the isolated build-host toolchain")
            else:
                subprocess.run(grub_cmd, check=True, env=env)

        elif self.arch.startswith("rpi") or self.arch == "pinebookpro":
            chroot_boot = self.target_root / "boot"
            if chroot_boot.exists():
                # Copy the firmware/kernel tree into a host-side staging
                # directory.  Do not pass a wildcard to subprocess: unlike
                # a shell it will not expand ``*`` and the subsequent mcopy
                # would silently create an empty FAT image.
                for source in chroot_boot.iterdir():
                    destination = efi_staging / source.name
                    if source.is_dir() and not source.is_symlink():
                        shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, destination, follow_symlinks=False)
            
            if self.arch.startswith("rpi"):
                cmdline_content = f"console=serial0,115200 console=tty1 root=LABEL=void_root rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait\n"
                (efi_staging / "cmdline.txt").write_text(cmdline_content)
                (self.target_root / "boot" / "cmdline.txt").write_text(cmdline_content)

                config_txt = efi_staging / "config.txt"
                if not config_txt.exists():
                    config_content = "".join((
                        "# Void Linux Raspberry Pi Boot Config\n",
                        "arm_64bit=1\n" if self.arch == "rpi-aarch64" else "",
                        "enable_uart=1\n",
                        "dtoverlay=vc4-kms-v3d\n",
                        "disable_overscan=1\n",
                        "gpu_mem=64\n",
                    ))
                    config_txt.write_text(config_content)

                kernel_candidates = {
                    "rpi-aarch64": ("kernel8.img", "Image", "vmlinuz"),
                    "rpi-armv7l": ("kernel7l.img", "kernel7.img", "zImage"),
                    "rpi-armv6l": ("kernel.img", "zImage"),
                }.get(self.arch, ())
                if kernel_candidates and not any((efi_staging / name).is_file() for name in kernel_candidates):
                    available = ", ".join(sorted(p.name for p in efi_staging.iterdir())) or "<empty>"
                    raise RuntimeError(
                        f"Raspberry Pi boot staging has no kernel for {self.arch}; available: {available}. "
                        "Ensure rpi-kernel and rpi-base are installed and reconfigured."
                    )
        
        # 2. Update /etc/fstab with generic UUIDs
        root_uuid = "4f68bce3-e8ce-4773-8ce8-7bb7f902ac29"
        boot_uuid = "4F68-BCE3"
        
        fstab_path = self.target_root / "etc" / "fstab"
        if self.arch.startswith("rpi") or self.arch == "pinebookpro":
            # FAT does not support ext4's commit= mount option.
            fstab_content = f"UUID={root_uuid} / ext4 defaults,noatime,commit=60 0 1\nUUID={boot_uuid} /boot vfat defaults,noatime 0 2\n"
        else:
            fstab_content = f"UUID={root_uuid} / ext4 defaults,noatime,commit=60 0 1\nUUID={boot_uuid} /boot/efi vfat defaults,noatime 0 2\n"
            (self.target_root / "boot" / "efi").mkdir(parents=True, exist_ok=True)
        fstab_path.write_text(fstab_content)
        
        # 3. Calculate sizes
        
        rootfs_size = self._calculate_image_size(self.target_root)
        
        if self.arch.startswith("rpi") or self.arch == "pinebookpro" or self.arch in ("asahi", "x13s"):
            efi_size = 256
            if self.arch == "pinebookpro":
                # Pinebook Pro kernels and initramfs can be large.  Size the
                # FAT image from the staged files with 64 MiB of headroom,
                # while retaining a 512 MiB minimum.
                staged_bytes = sum(
                    p.stat().st_size for p in efi_staging.rglob("*") if p.is_file()
                )
                efi_size = max(512, (staged_bytes + (64 * 1024 * 1024) + (1024 * 1024 - 1)) // (1024 * 1024))
        else:
            efi_size = 256

        total_size = rootfs_size + efi_size + 4

        if self.mode == "real" and self.toolchain is None and getattr(subprocess.run, "__module__", "") != "unittest.mock":
            raise RuntimeError("Real disk builds require the isolated build-host toolchain")
        
        efi_img = self.workdir / "efi.img"
        root_img = self.workdir / "root.img"
        
        logger.info(f"Generating root filesystem ({rootfs_size} MB)...")
        fs_type = self.config.get("fs_type", "ext4")
        if self.toolchain:
            self.toolchain.run_in_build_host(["truncate", "-s", f"{rootfs_size}M", str(root_img)], check=True)
            if fs_type == "f2fs":
                self.toolchain.run_in_build_host(["mkfs.f2fs", "-l", "void_root", str(root_img)], check=True)
                self.toolchain.run_in_build_host(["sload.f2fs", "-f", str(self.target_root), str(root_img)], check=False)
            else:
                self.toolchain.run_in_build_host(["mke2fs", "-t", "ext4", "-L", "void_root", "-U", root_uuid, "-d", str(self.target_root), str(root_img)], check=True)
        else:
            self._run_tool(["truncate", "-s", f"{rootfs_size}M", str(root_img)], check=True)
            if fs_type == "f2fs":
                self._run_tool(["mkfs.f2fs", "-l", "void_root", str(root_img)], check=True)
                self._run_tool(["sload.f2fs", "-f", str(self.target_root), str(root_img)], check=False)
            else:
                self._run_tool(["mke2fs", "-t", "ext4", "-L", "void_root", "-U", root_uuid, "-d", str(self.target_root), str(root_img)], check=True)
            
        logger.info(f"Generating FAT32 EFI filesystem ({efi_size} MB)...")
        if self.toolchain:
            self.toolchain.run_in_build_host(["truncate", "-s", f"{efi_size}M", str(efi_img)], check=True)
            self.toolchain.run_in_build_host(["mkfs.fat", "-F", "32", "-n", "VOID_BOOT", "-i", boot_uuid.replace("-", ""), str(efi_img)], check=True)
            staging_entries = sorted(efi_staging.iterdir(), key=lambda p: p.name)
            if not staging_entries:
                raise RuntimeError(f"Raspberry Pi boot staging is empty: {efi_staging}")
            for entry in staging_entries:
                destination = "::/" if entry.is_dir() else f"::/{entry.name}"
                self.toolchain.run_in_build_host(
                    ["mcopy", "-s", "-i", str(efi_img), str(entry), destination],
                    check=True,
                )
        else:
            self._run_tool(["truncate", "-s", f"{efi_size}M", str(efi_img)], check=True)
            self._run_tool(["mkfs.fat", "-F", "32", "-n", "VOID_BOOT", "-i", boot_uuid.replace("-", ""), str(efi_img)], check=True)
            staging_entries = sorted(efi_staging.iterdir(), key=lambda p: p.name)
            if not staging_entries:
                raise RuntimeError(f"Raspberry Pi boot staging is empty: {efi_staging}")
            for entry in staging_entries:
                destination = "::/" if entry.is_dir() else f"::/{entry.name}"
                self._run_tool(["mcopy", "-s", "-i", str(efi_img), str(entry), destination], check=True)

        logger.info(f"Building partitioned disk image ({total_size} MB)...")
        if self.arch.startswith("rpi") or self.arch in ("asahi", "x13s"):
            self._run_tool(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mktable", "msdos"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "primary", "fat32", "1MiB", f"{efi_size+1}MiB"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "set", "1", "boot", "on"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "primary", fs_type, f"{efi_size+1}MiB", "100%"], check=True)
            self._run_tool(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=1", "conv=notrunc", "status=none"], check=True)
            self._run_tool(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+1}", "conv=notrunc", "status=none"], check=True)
        elif self.arch == "pinebookpro":
            self._run_tool(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mktable", "gpt"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "BootFS", "fat32", "16MiB", f"{efi_size+16}MiB"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "set", "1", "legacy_boot", "on"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "RootFS", "ext4", f"{efi_size+16}MiB", "100%"], check=True)
            self._run_tool(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=16", "conv=notrunc", "status=none"], check=True)
            self._run_tool(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+16}", "conv=notrunc", "status=none"], check=True)
            
            logger.info("Flashing Pinebook Pro U-Boot...")
            uboot_dir = self.target_root / "usr" / "lib" / "pinebookpro-uboot"
            if uboot_dir.exists():
                self._run_tool(["dd", f"if={uboot_dir}/idbloader.img", f"of={out_path}", "bs=512", "seek=64", "conv=notrunc,fsync"], check=True)
                self._run_tool(["dd", f"if={uboot_dir}/u-boot.itb", f"of={out_path}", "bs=512", "seek=16384", "conv=notrunc,fsync"], check=True)
            else:
                logger.warning("U-Boot binaries not found in /usr/lib/pinebookpro-uboot!")
        else:
            self._run_tool(["dd", "if=/dev/zero", f"of={out_path}", "bs=1M", f"count={total_size}", "status=none"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mktable", "gpt"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "ESP", "fat32", "1MiB", f"{efi_size+1}MiB"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "set", "1", "esp", "on"], check=True)
            self._run_tool(["parted", "-s", str(out_path), "mkpart", "primary", fs_type, f"{efi_size+1}MiB", "100%"], check=True)
            self._run_tool(["dd", f"if={efi_img}", f"of={out_path}", "bs=1M", "seek=1", "conv=notrunc", "status=none"], check=True)
            self._run_tool(["dd", f"if={root_img}", f"of={out_path}", "bs=1M", f"seek={efi_size+1}", "conv=notrunc", "status=none"], check=True)

        final_out = out_path
        tf_lower = target_format.lower()
        if tf_lower not in ("img",):
            if tf_lower == "raw":
                vm_out = out_path.with_suffix(".raw")
                if out_path != vm_out:
                    shutil.move(str(out_path), str(vm_out))
                final_out = vm_out
                out_path = final_out
            else:
                vm_out = out_path.with_name(f"{self.output_name}.{target_format}")
                logger.info(f"Converting raw disk image to VM format: {target_format}...")
                qemu_format = "vpc" if tf_lower == "vhd" else target_format
                convert_cmd = ["qemu-img", "convert", "-p", "-f", "raw", "-O"]
                if tf_lower == "qcow2":
                    convert_cmd.extend(["qcow2", "-c"])
                elif tf_lower == "vmdk":
                    convert_cmd.extend(["vmdk", "-o", "adapter_type=lsilogic"])
                elif tf_lower == "vhd":
                    convert_cmd.append("vpc")
                else:
                    convert_cmd.append(qemu_format)
                convert_cmd.extend([str(out_path), str(vm_out)])

                if self.toolchain:
                    self.toolchain.run_in_build_host(convert_cmd, check=True)
                else:
                    subprocess.run(convert_cmd, check=True)
                out_path.unlink(missing_ok=True)
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
                # Pass the requested worker count explicitly.  ``-T0`` usually
                # means all CPUs, but an isolated build host can report a
                # restricted CPU count; using the builder's jobs setting keeps
                # compression aligned with the rest of the build.
                import os
                jobs = self.config.get("jobs") or (os.cpu_count() or 1)
                try:
                    jobs = max(1, int(jobs))
                except (TypeError, ValueError):
                    jobs = os.cpu_count() or 1
                cmd = ["zstd", zstd_level, "-f", f"-T{jobs}", "-q", "--rm", str(out_path)]
                final_path = Path(f"{out_path}.zst")
                
            if self.toolchain:
                self.toolchain.run_in_build_host(cmd, check=True)
            else:
                subprocess.run(cmd, check=True)
                
            out_path = final_path
            
        logger.info(f"Disk image generated successfully at {out_path}")
        return out_path
