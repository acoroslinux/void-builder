from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Type, Union

from void_builder.core.config_loader import Config
from void_builder.core.bootloaders.grub2 import Grub2Bootloader
from void_builder.core.bootloaders.syslinux import SyslinuxBootloader
from void_builder.core.customizer import SystemConfigurator
from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("ISOBuilder")
_ENGINE_REGISTRY: Dict[str, Type[ISOEngine]] = {}

class ISOBuilderError(Exception):
    """Raised when the build orchestration flow cannot proceed."""
    pass


class ISOEngine(ABC):
    """Abstract base for architecture-specific build engines."""

    @classmethod
    def register(cls, arch_name: str):
        def decorator(engine_class: Type[ISOEngine]):
            if arch_name in _ENGINE_REGISTRY:
                raise TypeError(f"Architecture '{arch_name}' is already registered.")
            _ENGINE_REGISTRY[arch_name] = engine_class
            return engine_class

        return decorator


class BaseEngine(ISOEngine):
    """Common engine behavior shared across all architecture-specific engines."""

    def __init__(self, arch: str, config: Config, toolchain: Any):
        self.arch = arch
        self.config = config
        self.toolchain = toolchain
        self.logger = getattr(toolchain, "logger", logger)

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        try:
            # 1. Try key directly
            val = self.config.get(key)
            if val is not None:
                return val

            # 2. Try iso.<key>
            if not key.startswith("iso."):
                val = self.config.get(f"iso.{key}")
                if val is not None:
                    return val

            # 3. Try customizations.<key>
            if not key.startswith("customizations."):
                val = self.config.get(f"customizations.{key}")
                if val is not None:
                    return val

            # 4. Try system.<key>
            if not key.startswith("system."):
                val = self.config.get(f"system.{key}")
                if val is not None:
                    return val

            return default
        except Exception:
            return default

    def _workdir_base(self) -> str:
        configured = (
            self.config.get("system.workdir_base")
            or "workdir"
        )
        return str(resolve_from_project(str(configured)))

    def _normalize_packages(self, packages: Any) -> List[str]:
        if not packages:
            return []
        normalized: List[str] = []
        for item in packages:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    normalized.append(str(name))
            else:
                normalized.append(str(item))
        return normalized

    def _package_plan(self) -> Dict[str, List[str]]:
        legacy_packages = self._normalize_packages(self._cfg_get("packages"))
        platform_packages = self._normalize_packages(self._cfg_get("platform_specific.packages"))
        legacy = list(dict.fromkeys(legacy_packages + platform_packages))
        official = self._normalize_packages(self._cfg_get("package_sources.official", []))
        
        # Keep order while deduplicating.
        official_all = list(dict.fromkeys([*legacy, *official]))

        if self.config.get("desktop_environment") or self.config.get("desktop") or any(
            any(pkg == d or pkg.startswith(f"{d}-") or pkg.startswith(f"{d}4-") or pkg.startswith(f"{d}4") for d in ("xfce", "kde", "gnome", "mate", "cinnamon", "lxde", "lxqt", "i3", "sway"))
            for pkg in official_all
        ):
            common_desktop = self._normalize_packages(self._cfg_get("common_desktop_packages", []))
            official_all.extend(pkg for pkg in common_desktop if pkg not in official_all)

        # Architecture exclusions safety check
        target_arch = str(self.arch or "").lower()
        is_arm = target_arch.startswith(("aarch64", "arm", "rpi", "pinebook", "asahi"))
        is_x86 = target_arch.startswith(("x86_64", "i686"))
        
        X86_EXCLUSIONS = {
            "intel-ucode", "amd-ucode", "sof-firmware", "alsa-firmware",
            "intel-media-driver", "libva-intel-driver", "mesa-vulkan-intel",
            "xf86-video-intel", "xf86-video-vmware", "xf86-video-vesa", "xf86-video-ati",
            "open-vm-tools", "thermald", "crda", "syslinux", "grub-i386-efi", "grub-x86_64-efi",
            "memtest86+", "virtualbox-ose-guest-dkms", "wsdd"
        }
        ARM_EXCLUSIONS = {
            "rpi-base", "rpi-kernel", "rpi-firmware", "rpi-userland",
            "pinebookpro-base", "x13s-base", "asahi-base", "grub-arm64-efi"
        }
        if is_arm:
            official_all = [p for p in official_all if p not in X86_EXCLUSIONS]
            if "rpi-kernel" in official_all and "linux" in official_all:
                official_all.remove("linux")
        elif is_x86:
            official_all = [p for p in official_all if p not in ARM_EXCLUSIONS]

        return {
            "official": official_all,
            "aur": [],
            "local_paths": [],
        }

    def setup_workdir(self, workdir: Optional[Union[str, Path]] = None) -> Path:
        target = Path(workdir) if workdir else Path(self._workdir_base())
        if not target.is_absolute():
            target = resolve_from_project(target)
        target.mkdir(parents=True, exist_ok=True)
        return target

    @abstractmethod
    def setup_chroot(self, workdir: str) -> None:
        """Prepare the chroot environment."""

    @abstractmethod
    def install_packages(self) -> None:
        """Install target packages inside the chroot."""

    @abstractmethod
    def build_bootloaders(self, mountpoint: str) -> None:
        """Generate bootloader artifacts for the target architecture."""

    @abstractmethod
    def post_install_configure(self) -> None:
        """Run post-install configuration steps."""

    @abstractmethod
    def finalize_isofile(self, output_path: str, output_format: str = "iso") -> Optional[str]:
        """Produce the final output artifact (ISO, IMG, QCOW2, VDI, VMDK, VHDX, etc.)."""

    def _convert_disk_image(self, raw_img_path: Path, target_format: str, output_path: Path) -> Path:
        """Convert a raw disk image (.img/.raw) to target VM disk format (qcow2, vdi, vmdk, vhdx)."""
        target_format = target_format.lower()
        if target_format in ("img", "raw"):
            if raw_img_path != output_path:
                shutil.move(str(raw_img_path), str(output_path))
            return output_path

        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        if is_mock:
            self.logger.info(f"[convert] [MOCK] Would convert {raw_img_path} to {target_format.upper()} at {output_path}")
            output_path.touch()
            if raw_img_path != output_path and raw_img_path.exists():
                try:
                    raw_img_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return output_path

        import subprocess
        qemu_img_bin = "qemu-img"
        cmd = [qemu_img_bin, "convert", "-p", "-f", "raw", "-O"]
        
        if target_format == "qcow2":
            cmd.extend(["qcow2", "-c"])  # Enable compression
        elif target_format == "vdi":
            cmd.extend(["vdi"])
        elif target_format == "vmdk":
            cmd.extend(["vmdk"])
        elif target_format in ("vhdx", "vhd"):
            cmd.extend(["vhdx"])
        else:
            cmd.extend([target_format])

        cmd.extend([str(raw_img_path), str(output_path)])
        self.logger.info(f"[convert] Converting raw disk image to {target_format.upper()}: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            self.logger.error(f"[convert] qemu-img conversion failed: {res.stderr}")
            raise ISOBuilderError(f"qemu-img conversion to {target_format} failed: {res.stderr}")

        self.logger.info(f"[convert] Successfully generated {target_format.upper()} virtual disk: {output_path}")
        if raw_img_path != output_path and raw_img_path.exists():
            try:
                raw_img_path.unlink(missing_ok=True)
            except Exception:
                pass
        return output_path

    def _generate_manifest_and_checksums(self, output_file_path: str) -> None:
        import hashlib
        import json
        from datetime import datetime, timezone

        output_file = Path(output_file_path)
        if not output_file.exists():
            return

        generate_manifest = self.config.get("generate_manifest", True)
        if not generate_manifest:
            return

        self.logger.info(f"[manifest] Generating checksums and manifest for {output_file.name}...")

        sha256_hash = hashlib.sha256()
        sha512_hash = hashlib.sha512()
        md5_hash = hashlib.md5()

        with open(output_file, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
                sha512_hash.update(byte_block)
                md5_hash.update(byte_block)

        sha256_val = sha256_hash.hexdigest()
        sha512_val = sha512_hash.hexdigest()
        md5_val = md5_hash.hexdigest()

        sha256_file = output_file.with_suffix(output_file.suffix + ".sha256")
        sha512_file = output_file.with_suffix(output_file.suffix + ".sha512")
        md5_file = output_file.with_suffix(output_file.suffix + ".md5")

        sha256_file.write_text(f"{sha256_val}  {output_file.name}\n")
        sha512_file.write_text(f"{sha512_val}  {output_file.name}\n")
        md5_file.write_text(f"{md5_val}  {output_file.name}\n")

        packages = self._package_plan().get("official", [])
        manifest_data = {
            "name": output_file.name,
            "architecture": self.arch,
            "desktop": self.config.get("desktop_environment", "base"),
            "kernel": self.config.get("kernel", "default"),
            "bootloader": self.config.get("bootloader", "default"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_size_bytes": output_file.stat().st_size if output_file.exists() else 0,
            "checksums": {
                "sha256": sha256_val,
                "sha512": sha512_val,
                "md5": md5_val,
            },
            "packages_count": len(packages),
            "packages": sorted(packages),
        }

        manifest_file = output_file.with_suffix(output_file.suffix + ".manifest.json")
        with open(manifest_file, "w") as mf:
            json.dump(manifest_data, mf, indent=2)

        self.logger.info(f"[manifest] Generated SHA256: {sha256_file.name}")
        self.logger.info(f"[manifest] Generated SHA512: {sha512_file.name}")
        self.logger.info(f"[manifest] Generated MD5: {md5_file.name}")
        self.logger.info(f"[manifest] Generated Manifest: {manifest_file.name}")

    def export_tarball(self, output_path: str) -> str:
        import subprocess
        output_abs = str(resolve_from_project(output_path))
        if output_abs.endswith(".iso") or output_abs.endswith(".img"):
            output_abs = output_abs.rsplit(".", 1)[0] + ".tar.xz"

        Path(output_abs).parent.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"[tarball] Exporting rootfs tarball to {output_abs}...")

        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        if is_mock:
            self.logger.info(f"[tarball] [MOCK] Would create rootfs tarball: {output_abs}")
            Path(output_abs).touch()
            self._generate_manifest_and_checksums(output_abs)
            return output_abs

        cmd = ["tar", "-cJf", output_abs, "-C", str(self.chroot_path), "."]
        subprocess.run(cmd, check=True)
        self.logger.info(f"[tarball] Rootfs tarball created: {output_abs}")
        self._generate_manifest_and_checksums(output_abs)
        return output_abs


@ISOEngine.register("x86_64")
@ISOEngine.register("x86_64-musl")
@ISOEngine.register("i686")
@ISOEngine.register("aarch64")
@ISOEngine.register("aarch64-musl")
@ISOEngine.register("armv7l")
@ISOEngine.register("armv7l-musl")
@ISOEngine.register("armv6l")
@ISOEngine.register("armv6l-musl")
@ISOEngine.register("riscv64")
@ISOEngine.register("riscv64-musl")
class VoidEngine(BaseEngine):
    """Engine in charge of Void Linux builds."""

    def setup_chroot(self, workdir: str) -> None:
        self.logger.info(f"[setup_chroot] Preparing chroot at {workdir}")
        self.chroot_path = Path(workdir) / "airootfs"
        self.chroot_path.mkdir(parents=True, exist_ok=True)

        self.iso_staging = Path(workdir) / "iso-staging"
        self.iso_staging.mkdir(parents=True, exist_ok=True)

    def install_packages(self) -> None:
        plan = self._package_plan()
        chroot_manager = getattr(self.toolchain, "chroot_manager", None)
        if not chroot_manager or not hasattr(chroot_manager, "install_packages"):
            self.logger.error("No chroot manager available to install packages.")
            raise ISOBuilderError("ChrootManager missing.")

        # Check for pre-built stage tarball option (--use-tarball / --tarball)
        use_tarball_arg = self._cfg_get("use_tarball")
        if use_tarball_arg:
            from void_builder.core.stage_manager import StageManager
            stage_manager = StageManager(
                workdir=self.chroot_path.parent,
                mode=getattr(self.toolchain, "mode", "mock"),
                arch=self.arch,
            )
            tarball_path = stage_manager.resolve_tarball(use_tarball_arg)
            stage_manager.extract_tarball(tarball_path, self.chroot_path)

        # Mount virtual filesystems BEFORE installing packages so that python compilation hooks have /dev/shm
        chroot_manager.mount()

        if use_tarball_arg and getattr(self.toolchain, "mode", "mock") == "real":
            self.logger.info("[Tarball] Updating base packages inside extracted chroot via xbps-install -Syu...")
            try:
                chroot_manager.run_command("xbps-install -Syu -y", check=False)
            except Exception as e:
                self.logger.warning(f"[Tarball] System update in chroot warned: {e}")

        repos = self._cfg_get("repositories", []) + self._cfg_get("custom_repositories", [])
        
        # Support for Custom Local Packages (e.g. Calamares)
        from void_builder.core.path_utils import resolve_from_project
        local_pkgs_dir = resolve_from_project("custom_packages")
        
        if local_pkgs_dir.exists() and local_pkgs_dir.is_dir():
            xbps_files = [str(p) for p in local_pkgs_dir.glob("*.xbps")]
            if len(xbps_files) > 0:
                self.logger.info(f"[Packages] Found {len(xbps_files)} custom local packages in {local_pkgs_dir}. Indexing...")
                import subprocess
                try:
                    xbps_rindex_bin = str(self.toolchain.xbps_install_static).replace("xbps-install.static", "xbps-rindex.static")
                    if Path(xbps_rindex_bin).exists():
                        subprocess.run([xbps_rindex_bin, "-a"] + xbps_files, check=True)
                    else:
                        subprocess.run(["xbps-rindex", "-a"] + xbps_files, check=True)
                    repos.insert(0, str(local_pkgs_dir))  # Insert at priority 0
                    self.logger.info(f"[Packages] Added local repository to the front: {local_pkgs_dir}")
                except Exception as e:
                    self.logger.warning(f"[Packages] Failed to index local packages: {e}")
            else:
                self.logger.warning(f"[Packages] Directory {local_pkgs_dir} exists but no .xbps files found.")

        chroot_manager.install_packages(plan, repos=repos)

    def post_install_configure(self) -> None:
        chroot_manager = getattr(self.toolchain, "chroot_manager", None)
        if not chroot_manager:
            raise ISOBuilderError("ChrootManager missing.")

        # 1. Mount virtual systems
        chroot_manager.mount()

        # 2. 3-pass package reconfigure (must happen first when using xbps-install -U)
        self.logger.info("[post_install] Running Void 3-pass package reconfiguration...")
        chroot_manager.run_reconfigure()

        # 3. Run system configuration / customizations & dracut initramfs generation
        self.logger.info("[post_install] Running customizations and generating initramfs...")
        configurator = SystemConfigurator(chroot_manager)
        configurator.load_from_config(self.config)
        configurator.apply()

        # 4. Cleanup rootfs before unmounting (cache, tmp)
        self.logger.info("[post_install] Cleaning up rootfs caches and temporary files to optimize ISO size...")
        # Match void-mklive: rm -rf /var/cache/* /run/* /var/run/*
        # Also clean /tmp and /var/tmp which void-mklive ignores but are safe to clear.
        chroot_manager.run_command("rm -rf /var/cache/* /var/tmp/* /tmp/* /run/* /var/run/*", check=False)
        # No custom dracut modules to clean up (using standard dmsquash-live only)
        from void_builder.utils.lib import clean_qemu_user_binary
        clean_qemu_user_binary(self.arch, self.chroot_path)

        # 5. Unmount virtual systems
        chroot_manager.umount()

    def build_bootloaders(self, mountpoint: str) -> None:
        self.logger.info("[bootloaders] Preparing bootloader files and copying kernel...")
        
        # Ensure target kernel and initramfs files exist in airootfs /boot
        chroot_boot = self.chroot_path / "boot"
        staging_boot = self.iso_staging / "boot"
        staging_boot.mkdir(parents=True, exist_ok=True)

        # Find kernel and initramfs inside target chroot and copy to staging_boot as vmlinuz/initrd
        is_aarch64 = self.arch.startswith("aarch64")
        kernel_name = "vmlinux" if is_aarch64 else "vmlinuz"

        kernel_found = False
        initrd_found = False
        kernel_version = "linux"

        # Determine correct kernel version (newest by modified time, matching customizer)
        modules_dir = self.chroot_path / "usr" / "lib" / "modules"
        if not modules_dir.exists():
            modules_dir = chroot_boot.parent / "lib" / "modules"

        if modules_dir.is_dir():
            versions_dirs = [d for d in modules_dir.iterdir() if d.is_dir()]
            if versions_dirs:
                versions_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                kernel_version = versions_dirs[0].name
                self.logger.info(f"[bootloaders] Staging kernel version: {kernel_version}")

        # 1. Search for kernel candidate in /boot
        kernel_candidates = [
            chroot_boot / f"vmlinuz-{kernel_version}",
            chroot_boot / f"vmlinux-{kernel_version}",
            chroot_boot / f"Image-{kernel_version}",
            chroot_boot / "vmlinuz",
            chroot_boot / "vmlinux",
            chroot_boot / "Image",
        ]
        if chroot_boot.is_dir():
            for g in ["vmlinuz*", "vmlinux*", "Image*"]:
                for f in chroot_boot.glob(g):
                    if f.is_file() and f not in kernel_candidates:
                        kernel_candidates.append(f)

        for kcand in kernel_candidates:
            if kcand.exists() and kcand.is_file() and kcand.stat().st_size > 0:
                shutil.copy2(kcand, staging_boot / kernel_name)
                kernel_found = True
                self.logger.info(f"[bootloaders] Staged kernel from: {kcand.name} -> {kernel_name}")
                break

        # 2. Search for initramfs candidate in /boot
        initrd_candidates = [
            chroot_boot / "initrd",
            chroot_boot / f"initramfs-{kernel_version}.img",
            chroot_boot / f"initrd-{kernel_version}.img",
            chroot_boot / "initramfs.img",
            chroot_boot / "initramfs",
        ]
        if chroot_boot.is_dir():
            for g in ["initrd*", "initramfs*"]:
                for f in chroot_boot.glob(g):
                    if f.is_file() and f not in initrd_candidates:
                        initrd_candidates.append(f)

        for icand in initrd_candidates:
            if icand.exists() and icand.is_file() and icand.stat().st_size > 0:
                shutil.copy2(icand, staging_boot / "initrd")
                initrd_found = True
                self.logger.info(f"[bootloaders] Staged initramfs from: {icand.name} -> initrd")
                break

        if not kernel_found or not initrd_found:
            if getattr(self.toolchain, "mode", "mock") == "mock":
                self.logger.warning("[bootloaders] Kernel or initramfs not found in chroot /boot. Using mock placeholders.")
                if not kernel_found:
                    (staging_boot / kernel_name).write_text("mock-kernel")
                if not initrd_found:
                    (staging_boot / "initrd").write_text("mock-initrd")
            else:
                missing = []
                if not kernel_found:
                    missing.append("kernel")
                if not initrd_found:
                    missing.append("initramfs")
                raise ISOBuilderError(f"Real build failed: {' and '.join(missing)} missing in target chroot /boot.")

        # Determine target bootloader chroot environment
        bootloader_chroot = self.chroot_path
        if getattr(self.toolchain, "mode", "mock") == "real" and hasattr(self.toolchain, "target_dir"):
            bootloader_chroot = self.toolchain.target_dir

        # Copy memtest binaries if present in bootloader chroot
        chroot_memtest_dir = bootloader_chroot / "boot" / "memtest86+"
        if chroot_memtest_dir.is_dir():
            for f in chroot_memtest_dir.iterdir():
                if f.name in ("memtest.bin", "memtest.efi"):
                    shutil.copy2(f, staging_boot / f.name)
                    self.logger.info(f"[bootloaders] Copied memtest file: {f.name}")

        # Process platform DTBs if ARM platforms are specified
        platforms_config = self.config.get("platforms_config", {})
        if is_aarch64 and platforms_config:
            for platform, plat_info in platforms_config.items():
                dtb_path = plat_info.get("dtb")
                if dtb_path:
                    chroot_dtb_dir = chroot_boot / "dtbs"
                    src_dtb = None
                    if chroot_dtb_dir.is_dir():
                        for f in chroot_dtb_dir.rglob(dtb_path):
                            if f.is_file():
                                src_dtb = f
                                break
                    if src_dtb and src_dtb.exists():
                        dest_dtb = staging_boot / "dtbs" / dtb_path
                        dest_dtb.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_dtb, dest_dtb)
                        self.logger.info(f"[bootloaders] Copied DTB for {platform}: {dtb_path}")
                    else:
                        self.logger.warning(f"[bootloaders] DTB file '{dtb_path}' not found in chroot /boot/dtbs/")

        # Copy GRUB themes and fonts for theme support
        # 1. First try copying themes from the project's assets
        from void_builder.core.path_utils import resolve_from_project
        project_themes = resolve_from_project("configs/assets/grub/themes")
        if project_themes.exists():
            shutil.copytree(project_themes, staging_boot / "grub" / "themes", dirs_exist_ok=True)
            self.logger.info("[bootloaders] Copied GRUB themes from project assets to ISO boot tree")
        # 2. Then try copying system themes from the chroot
        chroot_grub_themes = self.chroot_path / "usr" / "share" / "grub" / "themes"
        if chroot_grub_themes.exists():
            shutil.copytree(chroot_grub_themes, staging_boot / "grub" / "themes", dirs_exist_ok=True)
            self.logger.info("[bootloaders] Copied system GRUB themes to ISO boot tree")

        # Ensure the unicode font is present on the ISO for graphical terminal menu rendering
        iso_fonts_dir = staging_boot / "grub" / "fonts"
        iso_fonts_dir.mkdir(parents=True, exist_ok=True)
        copied_font = False

        # 1. Try copying from chroot /boot/grub/fonts
        if (chroot_boot / "grub" / "fonts" / "unicode.pf2").exists():
            shutil.copy2(chroot_boot / "grub" / "fonts" / "unicode.pf2", iso_fonts_dir / "unicode.pf2")
            copied_font = True
        # 2. Try copying from chroot /usr/share/grub/unicode.pf2
        elif (self.chroot_path / "usr" / "share" / "grub" / "unicode.pf2").exists():
            shutil.copy2(self.chroot_path / "usr" / "share" / "grub" / "unicode.pf2", iso_fonts_dir / "unicode.pf2")
            copied_font = True
        # 3. Try copying from host /usr/share/grub/unicode.pf2
        elif Path("/usr/share/grub/unicode.pf2").exists():
            shutil.copy2("/usr/share/grub/unicode.pf2", iso_fonts_dir / "unicode.pf2")
            copied_font = True

        if copied_font:
            self.logger.info("[bootloaders] Copied GRUB unicode font to ISO boot tree")
        else:
            self.logger.warning("[bootloaders] GRUB unicode font could not be located on chroot or host")

        # Set up ISOLINUX (BIOS) - only for x86 architectures
        if self.arch.startswith(("x86_64", "i686")):
            syslinux = SyslinuxBootloader(self.config, kernel_version=kernel_version)
            syslinux.prepare_files(self.iso_staging)
            syslinux.generate_boot_image(self.iso_staging, bootloader_chroot)

        # Set up GRUB2 (UEFI) - for all architectures
        grub = Grub2Bootloader(self.config, root_device_id="VOID_MODERN", kernel_version=kernel_version)
        grub.prepare_files(self.iso_staging)
        grub.generate_boot_image(self.iso_staging, bootloader_chroot)

    def _create_squashfs(self) -> None:
        """Create the squashed root filesystem (wrapped in ext3fs.img for dmsquash-live)."""
        self.logger.info("=== Step 4: Compressing Root Filesystem ===")

        # CRITICAL: Unmount pseudofs BEFORE copying rootfs into ext3fs.img.
        # Without this, /dev /proc /sys from the host get baked into the
        # SquashFS image, causing dracut to crash with 'Signal caught!' on boot.
        # This matches void-mklive's generate_squashfs() which starts with:
        #   umount_pseudofs || exit 1
        chroot_manager = getattr(self.toolchain, "chroot_manager", None)
        if chroot_manager:
            chroot_manager.umount()

        # Also ensure the pseudofs mount points inside chroot are empty directories
        # (safety net in case umount was already done but dirs have stale content)
        import subprocess, os
        chroot_cmd = [] if os.geteuid() == 0 else ["sudo"]
        for d in ["dev", "proc", "sys", "run"]:
            target = self.chroot_path / d
            if target.is_mount():
                self.logger.warning(f"[squashfs] {target} still mounted! Force unmounting...")
                subprocess.run(chroot_cmd + ["umount", "-R", "-l", str(target)], check=False)

        liveos_dir = self.iso_staging / "LiveOS"
        liveos_dir.mkdir(parents=True, exist_ok=True)
        squashfs_img = liveos_dir / "squashfs.img"

        if squashfs_img.exists():
            self.logger.info("SquashFS already exists, skipping compression.")
            return

        comp_type = self.config.get("squashfs_compression", "xz")
        if getattr(self.toolchain, "mode", "mock") == "mock":
            self.logger.info(f"[MOCK] mksquashfs {self.chroot_path} {squashfs_img} -comp {comp_type}")
            squashfs_img.write_text("mock squashfs content")
            return

        import os
        import subprocess
        import tempfile
        import time

        # 1. Determine rootfs size
        try:
            res = subprocess.run(["du", "--apparent-size", "-sm", str(self.chroot_path)], capture_output=True, text=True, check=True)
            size_mb = int(res.stdout.split()[0])
        except Exception as e:
            self.logger.warning(f"Failed to determine rootfs size, using 4000MB fallback: {e}")
            size_mb = 4000

        img_size_mb = size_mb * 2 + 100

        with tempfile.TemporaryDirectory(dir=self.iso_staging.parent) as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_liveos = tmp_path / "LiveOS"
            tmp_liveos.mkdir(parents=True, exist_ok=True)

            ext3_img = tmp_liveos / "ext3fs.img"
            
            # 2. Truncate image file
            subprocess.run(["truncate", "-s", f"{img_size_mb}M", str(ext3_img)], check=True)
            
            # 3. Run mkfs.ext3 matching void-mklive
            subprocess.run([
                "mkfs.ext3", "-F", "-m", "1",
                str(ext3_img)
            ], check=True)
            
            # 4. Mount and copy
            mount_point = tmp_path / "mnt"
            mount_point.mkdir(parents=True, exist_ok=True)

            chroot_cmd = []
            if os.geteuid() != 0:
                chroot_cmd = ["sudo"]

            subprocess.run(chroot_cmd + ["mount", "-o", "loop", str(ext3_img), str(mount_point)], check=True)
            try:
                self.logger.info(f"Copying rootfs into ext3fs.img (Size: {img_size_mb}MB)...")
                subprocess.run(chroot_cmd + ["cp", "-a", f"{self.chroot_path}/.", f"{mount_point}/"], check=True)

                # Strictly ensure security permissions inside ext3fs.img
                subprocess.run(chroot_cmd + ["chmod", "600", f"{mount_point}/etc/shadow"], check=False)
                subprocess.run(chroot_cmd + ["chmod", "644", f"{mount_point}/etc/passwd"], check=False)
                subprocess.run(chroot_cmd + ["chmod", "644", f"{mount_point}/etc/group"], check=False)
                if (mount_point / "etc" / "sudoers").exists():
                    subprocess.run(chroot_cmd + ["chmod", "440", f"{mount_point}/etc/sudoers"], check=False)
                sudoers_d = mount_point / "etc" / "sudoers.d"
                if sudoers_d.exists():
                    subprocess.run(chroot_cmd + ["chmod", "750", str(sudoers_d)], check=False)
                    for s_file in sudoers_d.glob("*"):
                        if s_file.is_file():
                            subprocess.run(chroot_cmd + ["chmod", "440", str(s_file)], check=False)
            finally:
                unmounted = False
                for _ in range(5):
                    res = subprocess.run(chroot_cmd + ["umount", "-f", str(mount_point)], capture_output=True)
                    if res.returncode == 0:
                        unmounted = True
                        break
                    time.sleep(1)
                if not unmounted:
                    subprocess.run(chroot_cmd + ["umount", "-l", str(mount_point)], capture_output=True)
                try:
                    mount_point.rmdir()
                except OSError:
                    pass

            # 5. Generate squashfs from tmp_dir
            mksquashfs_bin = "mksquashfs"
            if getattr(self.toolchain, "mode", "mock") == "real" and hasattr(self.toolchain, "host_dir"):
                candidate = self.toolchain.host_dir / "usr" / "bin" / "mksquashfs"
                if candidate.exists():
                    mksquashfs_bin = str(candidate)

            comp_type = self.config.get("squashfs_compression", "xz")
            cpu_count = max(os.cpu_count() or 1, 1)
            
            cmd = [
                str(mksquashfs_bin), str(tmp_dir), str(squashfs_img),
                "-comp", comp_type, "-processors", str(cpu_count)
            ]
            if comp_type == "zstd":
                comp_level = str(self.config.get("zstd_level", "3"))
                block_size = "256K" if self.config.get("fast_mode") else "1048576"
                cmd.extend(["-Xcompression-level", comp_level, "-b", block_size])
            elif comp_type == "xz":
                cmd.extend(["-b", "1048576"])

            self.logger.info(f"[squashfs] Command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=False)
            subprocess.run(["chmod", "444", str(squashfs_img)], check=True)

        self.logger.info(f"[squashfs] SquashFS created: {squashfs_img}")

    def finalize_isofile(self, output_path: str, output_format: str = "iso") -> Optional[str]:
        output_format = (output_format or "iso").lower()
        if output_format == "iso":
            return self._finalize_iso(output_path)
        elif output_format in ("img", "raw", "qcow2", "vdi", "vmdk", "vhdx", "vhd"):
            return self._finalize_disk_image(output_path, output_format)
        else:
            raise ISOBuilderError(f"Unsupported output format: {output_format}")

    def _finalize_iso(self, output_path: str) -> str:
        # 1. Create squashfs
        self._create_squashfs()

        # 2. Xorriso ISO creation
        output_abs = str(resolve_from_project(output_path))
        Path(output_abs).parent.mkdir(parents=True, exist_ok=True)

        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        iso_label = self._cfg_get("system.iso_label", "VOID_MODERN")

        xorriso_bin = "xorriso"
        if not is_mock and hasattr(self.toolchain, "host_dir"):
            candidate = self.toolchain.host_dir / "usr" / "bin" / "xorriso"
            if candidate.exists():
                xorriso_bin = str(candidate)

        command = [
            xorriso_bin,
            "-as", "mkisofs",
            "-iso-level", "3",
            "-rock", "-joliet", "-joliet-long",
            "-max-iso9660-filenames",
            "-omit-period", "-omit-version-number",
            "-relaxed-filenames", "-allow-lowercase",
            "-volid", iso_label,
        ]

        # Add BIOS boot options if ISOLINUX is present
        isolinux_dir = self.iso_staging / "boot" / "isolinux"
        if (isolinux_dir / "isolinux.bin").exists():
            isohdpfx_path = None
            if hasattr(self.toolchain, "target_dir"):
                candidate = self.toolchain.target_dir / "usr" / "lib" / "syslinux" / "isohdpfx.bin"
                if candidate.exists():
                    isohdpfx_path = candidate
            if not isohdpfx_path:
                candidate = self.chroot_path / "usr" / "lib" / "syslinux" / "isohdpfx.bin"
                if candidate.exists():
                    isohdpfx_path = candidate

            if isohdpfx_path and isohdpfx_path.exists():
                command.extend([
                    "-isohybrid-mbr", str(isohdpfx_path)
                ])
            command.extend([
                "-eltorito-boot", "boot/isolinux/isolinux.bin",
                "-eltorito-catalog", "boot/isolinux/boot.cat",
                "-no-emul-boot",
                "-boot-load-size", "4",
                "-boot-info-table",
            ])

        # Add UEFI boot options if efiboot.img is present
        efiboot_img = self.iso_staging / "boot" / "grub" / "efiboot.img"
        if efiboot_img.exists():
            command.extend([
                "-eltorito-alt-boot",
                "-e", "boot/grub/efiboot.img",
                "-no-emul-boot",
                "-isohybrid-gpt-basdat",
                "-isohybrid-apm-hfsplus",
            ])

        command.extend(["-output", output_abs, str(self.iso_staging)])

        if is_mock:
            self.logger.info(f"[finalize] [MOCK] Would create ISO: {output_abs} from {self.iso_staging}")
            self.logger.info(f"[finalize] [MOCK] Command: {' '.join(command)}")
            Path(output_abs).touch()
            self._generate_manifest_and_checksums(output_abs)
            return output_abs

        self.logger.info(f"[finalize] Creating bootable hybrid ISO with xorriso: {output_abs}")
        self.logger.info(f"[finalize] Command: {' '.join(command)}")

        import subprocess
        res = subprocess.run(command, capture_output=True, text=True)
        if res.returncode != 0:
            err_msg = res.stderr or res.stdout
            if "exceeds free space" in err_msg or "Image write cancelled" in err_msg:
                if Path(output_abs).exists():
                    Path(output_abs).unlink(missing_ok=True)
                self.logger.error("xorriso failed: Insufficient disk space on destination storage media.")
                raise ISOBuilderError("xorriso failed: Insufficient disk space on destination storage media.")

            # Only ignore harmless xorriso warnings (like exit code 1 with non-critical notes) if no failure occurred
            if "FAILURE :" in err_msg or "MISHAP :" in err_msg:
                if Path(output_abs).exists():
                    Path(output_abs).unlink(missing_ok=True)
                self.logger.error(f"xorriso build failed: {err_msg}")
                raise ISOBuilderError(f"xorriso build failed: {err_msg}")

            if Path(output_abs).exists() and Path(output_abs).stat().st_size > 1000000:
                self.logger.warning(
                    f"xorriso reported minor non-fatal exit warning ({err_msg}), "
                    f"proceeding with generated ISO at {output_abs}."
                )
            else:
                if Path(output_abs).exists():
                    Path(output_abs).unlink(missing_ok=True)
                self.logger.error(f"xorriso failed: {err_msg}")
                raise ISOBuilderError(f"xorriso failed: {err_msg}")

        self.logger.info(f"[finalize] Bootable ISO created: {output_abs}")
        self._generate_manifest_and_checksums(output_abs)
        return output_abs

    def _finalize_disk_image(self, output_path: str, output_format: str) -> str:
        self.logger.info(f"=== Step 6: Finalizing Bootable Virtual Disk / Disk Image ({output_format.upper()}) ===")
        import subprocess
        import os
        from void_builder.core.path_utils import resolve_from_project

        output_abs_path = resolve_from_project(output_path)
        ext_map = {
            "qcow2": ".qcow2",
            "vdi": ".vdi",
            "vmdk": ".vmdk",
            "vhdx": ".vhdx",
            "vhd": ".vhdx",
            "raw": ".raw",
            "img": ".img",
        }
        target_ext = ext_map.get(output_format, f".{output_format}")
        if output_abs_path.suffix != target_ext:
            output_abs_path = output_abs_path.with_suffix(target_ext)

        output_abs_path.parent.mkdir(parents=True, exist_ok=True)

        img_size_config = self._cfg_get("system.img_size", None)
        if img_size_config:
            img_size = img_size_config
        else:
            try:
                du_res = subprocess.run(["du", "--apparent-size", "-sm", str(self.chroot_path)], capture_output=True, text=True, check=True)
                used_mb = int(du_res.stdout.split()[0])
                required_mb = int(used_mb * 1.30) + 600
                img_size = f"{required_mb}M"
                self.logger.info(f"[disk] Dynamically calculated image size: {img_size} (rootfs is ~{used_mb}MB)")
            except Exception as e:
                self.logger.warning(f"[disk] Failed to calculate rootfs size: {e}. Falling back to 4G.")
                img_size = "4G"

        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        if is_mock:
            self.logger.info(f"[disk] [MOCK] Would create {output_format.upper()} disk image: {output_abs_path} ({img_size})")
            output_abs_path.touch()
            self._generate_manifest_and_checksums(str(output_abs_path))
            return str(output_abs_path)

        if os.geteuid() != 0:
            raise ISOBuilderError(f"Root privileges (sudo) are required to generate bootable {output_format.upper()} disk images.")

        raw_staging = output_abs_path.parent / f"{output_abs_path.stem}.raw_staging"
        self.logger.info(f"[disk] Creating raw staging disk image: {raw_staging} ({img_size})")

        # 1. Truncate file
        subprocess.run(["truncate", "-s", img_size, str(raw_staging)], check=True)

        # 2. Partition with GPT (ESP + Root)
        sfdisk_cmd = (
            "label: gpt\n"
            "unit: sectors\n"
            "first-lba: 2048\n"
            "name=EFI, size=524288, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, bootable\n"
            "name=VoidLinux, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n"
        )
        subprocess.run(["sfdisk", str(raw_staging)], input=sfdisk_cmd.encode(), check=True)

        # 3. Setup Loop
        res = subprocess.run(["losetup", "--show", "--find", "--partscan", str(raw_staging)], capture_output=True, text=True, check=True)
        loop_dev = res.stdout.strip()
        subprocess.run(["udevadm", "settle"], check=False)

        try:
            # 4. Format EFI (FAT32) and Root (ext4)
            self.logger.info(f"[disk] Formatting partitions on {loop_dev}...")
            subprocess.run(["mkfs.vfat", "-F32", "-n", "VOID_BOOT", f"{loop_dev}p1"], check=True)
            subprocess.run(["mkfs.ext4", "-F", "-L", "void_root", f"{loop_dev}p2"], check=True)

            # 5. Mount and Copy
            mnt_root = Path(self.workdir) / "mnt_disk"
            mnt_root.mkdir(parents=True, exist_ok=True)

            subprocess.run(["mount", f"{loop_dev}p2", str(mnt_root)], check=True)
            (mnt_root / "boot" / "efi").mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", f"{loop_dev}p1", str(mnt_root / "boot" / "efi")], check=True)

            try:
                self.logger.info(f"[disk] Copying rootfs into disk partitions...")
                subprocess.run(["cp", "-a", f"{self.chroot_path}/.", f"{mnt_root}/"], check=True)

                # Fix fstab with UUIDs
                boot_uuid_res = subprocess.run(["blkid", "-s", "UUID", "-o", "value", f"{loop_dev}p1"], capture_output=True, text=True)
                root_uuid_res = subprocess.run(["blkid", "-s", "UUID", "-o", "value", f"{loop_dev}p2"], capture_output=True, text=True)
                boot_uuid = boot_uuid_res.stdout.strip()
                root_uuid = root_uuid_res.stdout.strip()

                fstab_content = (
                    f"UUID={root_uuid} / ext4 defaults,noatime 0 1\n"
                    f"UUID={boot_uuid} /boot/efi vfat umask=0077 0 2\n"
                )
                (mnt_root / "etc" / "fstab").write_text(fstab_content)

                # Install GRUB bootloader to EFI partition
                self.logger.info(f"[disk] Installing bootloader into virtual disk...")
                from void_builder.utils.lib import mount_pseudofs, umount_pseudofs, run_cmd_chroot
                try:
                    mount_pseudofs(str(mnt_root))
                    grub_target = "x86_64-efi" if self.arch == "x86_64" else ("i386-efi" if self.arch == "i686" else "arm64-efi")
                    run_cmd_chroot(
                        str(mnt_root),
                        f"grub-install --target={grub_target} --efi-directory=/boot/efi --bootloader-id=void --removable",
                        check=False
                    )
                    run_cmd_chroot(str(mnt_root), "grub-mkconfig -o /boot/grub/grub.cfg", check=False)
                finally:
                    umount_pseudofs(str(mnt_root))

            finally:
                subprocess.run(["umount", "-f", str(mnt_root / "boot" / "efi")], check=False)
                subprocess.run(["umount", "-f", str(mnt_root)], check=False)
                try:
                    os.rmdir(str(mnt_root))
                except OSError:
                    pass

        finally:
            subprocess.run(["losetup", "-d", loop_dev], check=False)

        # 6. Convert to target virtual disk format (QCOW2, VDI, VMDK, VHDX, RAW/IMG)
        final_file = self._convert_disk_image(raw_staging, output_format, output_abs_path)
        self._generate_manifest_and_checksums(str(final_file))
        return str(final_file)


class ISOBuilder:
    """Canonical high-level build orchestrator used by the project."""

    def __init__(self, arch: str, config: Config, toolchain: Any):
        self.arch = arch
        self.config = config
        self.toolchain = toolchain
        self.timings: Dict[str, float] = {}
        
        # Instantiate the correct engine based on target architecture
        engine_cls = _ENGINE_REGISTRY.get(arch)
        if not engine_cls:
            raise ISOBuilderError(f"No build engine registered for architecture '{arch}'.")
        self.engine = engine_cls(arch, config, toolchain)

    def build(self, output_path: str, workdir: Optional[str] = None, output_format: str = "iso") -> str:
        """Execute the full build pipeline with per-stage timing metrics."""
        import time
        t_start = time.perf_counter()
        self.timings = {}

        logger.info(f"=== Starting build pipeline for architecture {self.arch} ===")

        # 1. Setup workdir & chroot
        t_step = time.perf_counter()
        workdir_path = self.engine.setup_workdir(workdir)
        self.engine.setup_chroot(str(workdir_path))
        self.timings["setup_chroot"] = time.perf_counter() - t_step

        # 2. Install packages
        t_step = time.perf_counter()
        self.engine.install_packages()
        self.timings["install_packages"] = time.perf_counter() - t_step

        # 3. Run post-install configuration & customizations
        t_step = time.perf_counter()
        self.engine.post_install_configure()
        self.timings["post_install"] = time.perf_counter() - t_step

        # 4. Build bootloaders
        t_step = time.perf_counter()
        self.engine.build_bootloaders(str(workdir_path))
        self.timings["build_bootloaders"] = time.perf_counter() - t_step

        # 5. Finalize ISO / IMG / Tarball file
        t_step = time.perf_counter()
        if output_format == "tarball" or self.config.get("create_tarball"):
            final_tarball = self.engine.export_tarball(output_path)
            if self.config.get("create_tarball"):
                cache_dest = resolve_from_project(f"cache/tarballs/void-base-{self.arch}.tar.xz")
                stage_seed_dest = resolve_from_project(f"output/stage_seeds/void-base-{self.arch}.tar.xz")
                for dest in (cache_dest, stage_seed_dest):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if Path(final_tarball).exists() and Path(final_tarball) != dest:
                        import shutil
                        try:
                            shutil.copy2(final_tarball, dest)
                            logger.info(f"[tarball] Saved stage seed tarball to: {dest}")
                            # Also copy checksum files if they exist
                            src_p = Path(final_tarball)
                            for ext in (".sha256", ".sha512", ".md5", ".manifest.json"):
                                src_c = src_p.parent / f"{src_p.name}{ext}"
                                if src_c.exists():
                                    shutil.copy2(src_c, dest.parent / f"{dest.name}{ext}")
                        except Exception as e:
                            logger.warning(f"[tarball] Could not copy stage tarball to {dest}: {e}")
            if output_format == "tarball":
                final_file = final_tarball
            else:
                res = self.engine.finalize_isofile(output_path, output_format=output_format)
                final_file = str(res) if res else str(resolve_from_project(output_path))
        else:
            res = self.engine.finalize_isofile(output_path, output_format=output_format)
            final_file = str(res) if res else str(resolve_from_project(output_path))

        self.timings["finalize_artifact"] = time.perf_counter() - t_step
        self.timings["total"] = time.perf_counter() - t_start

        logger.info(f"=== Build completed in {self.timings['total']:.2f}s ===")
        return final_file

@ISOEngine.register("rpi-aarch64")
@ISOEngine.register("rpi-armv7l")
@ISOEngine.register("rpi-armv6l")
@ISOEngine.register("pinebookpro")
@ISOEngine.register("asahi")
@ISOEngine.register("x13s")
class PlatformEngine(VoidEngine):
    """Engine in charge of Single Board Computers and specialized platforms (Raspberry Pi, Pinebook Pro, Asahi, ThinkPad X13s, etc.)"""

    def build_bootloaders(self, workdir: str) -> None:
        self.logger.info("=== Step 5: Bootloaders ===")
        if self.arch.startswith("rpi"):
            self.logger.info("Platform image (rpi) relies on native firmware from rpi-base. Skipping GRUB/Syslinux.")
        elif self.arch == "pinebookpro":
            self.logger.info("Pinebook Pro relies on u-boot written directly to disk. Skipping GRUB/Syslinux inside chroot.")
        elif self.arch in ("asahi", "x13s"):
            self.logger.info(f"{self.arch} requires GRUB EFI. Will be installed during image finalization.")

    def finalize_isofile(self, output_path: str, output_format: str = "img") -> Optional[str]:
        self.logger.info(f"=== Step 6: Finalizing Platform Image ({output_format.upper()}) ===")
        output_format = (output_format or "img").lower()
        if output_format == "iso":
            output_format = "img"

        import subprocess
        import os
        from void_builder.core.path_utils import resolve_from_project
        
        output_abs_path = resolve_from_project(output_path)
        ext_map = {
            "qcow2": ".qcow2",
            "vdi": ".vdi",
            "vmdk": ".vmdk",
            "vhdx": ".vhdx",
            "vhd": ".vhdx",
            "raw": ".raw",
            "img": ".img",
        }
        target_ext = ext_map.get(output_format, f".{output_format}")
        if output_abs_path.suffix != target_ext:
            output_abs_path = output_abs_path.with_suffix(target_ext)

        output_abs = str(output_abs_path)
        output_abs_path.parent.mkdir(parents=True, exist_ok=True)

        # Calculate required size dynamically if not hardcoded in config
        img_size_config = self._cfg_get("system.img_size", None)
        if img_size_config:
            img_size = img_size_config
        else:
            try:
                du_res = subprocess.run(["du", "--apparent-size", "-sm", str(self.chroot_path)], capture_output=True, text=True, check=True)
                used_mb = int(du_res.stdout.split()[0])
                required_mb = int(used_mb * 1.25) + 600
                img_size = f"{required_mb}M"
                self.logger.info(f"[finalize] Dynamically calculated image size: {img_size} (rootfs is ~{used_mb}MB)")
            except Exception as e:
                self.logger.warning(f"[finalize] Failed to calculate rootfs size: {e}. Falling back to 4G.")
                img_size = "4G"
        
        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        if is_mock:
            self.logger.info(f"[finalize] [MOCK] Would create platform image: {output_abs} ({img_size})")
            output_abs_path.touch()
            self._generate_manifest_and_checksums(output_abs)
            return output_abs

        self.logger.info(f"[finalize] Creating platform image: {output_abs} ({img_size})")
        if os.geteuid() != 0:
            raise ISOBuilderError("Root privileges are required to generate platform images via loop devices.")
            
        # 1. Create file
        raw_staging = output_abs_path.parent / f"{output_abs_path.stem}.raw_staging"
        subprocess.run(["truncate", "-s", img_size, str(raw_staging)], check=True)
        
        # 2. Partition
        boot_size = "256MiB"
        if self.arch == "pinebookpro":
            boot_size = "512MiB" # RK3399 needs larger boot space for kernels
            sfdisk_cmd = f"label: gpt\nunit: sectors\nfirst-lba: 32768\nname=BootFS, size={boot_size}, type=L, bootable, attrs=\"LegacyBIOSBootable\"\nname=RootFS, type=L\n"
        elif self.arch in ("asahi", "x13s"):
            sfdisk_cmd = f"label: dos\n2048,{boot_size},b,*\n,+,L\n"
        else:
            sfdisk_cmd = f"label: dos\n2048,{boot_size},b,*\n,+,L\n"

        subprocess.run(["sfdisk", str(raw_staging)], input=sfdisk_cmd.encode(), check=True)
        
        # 3. Setup Loop
        res = subprocess.run(["losetup", "--show", "--find", "--partscan", str(raw_staging)], capture_output=True, text=True, check=True)
        loop_dev = res.stdout.strip()
        subprocess.run(["udevadm", "settle"], check=False)
        
        try:
            # 4. Format
            self.logger.info(f"[finalize] Formatting partitions on {loop_dev}...")
            subprocess.run(["mkfs.vfat", "-I", "-F16", f"{loop_dev}p1"], check=True)
            subprocess.run(["mkfs.ext4", "-F", "-O", "^has_journal", f"{loop_dev}p2"], check=True)
            
            # 5. Mount and Copy
            mnt_root = Path(self.workdir) / "mnt_platform"
            mnt_root.mkdir(parents=True, exist_ok=True)
            
            subprocess.run(["mount", f"{loop_dev}p2", str(mnt_root)], check=True)
            (mnt_root / "boot").mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", f"{loop_dev}p1", str(mnt_root / "boot")], check=True)
            
            try:
                self.logger.info(f"[finalize] Copying target rootfs into platform partitions...")
                subprocess.run(["cp", "-a", f"{self.chroot_path}/.", f"{mnt_root}/"], check=True)
                
                # Fix fstab with UUIDs
                self.logger.info(f"[finalize] Generating /etc/fstab for platform image...")
                boot_uuid_res = subprocess.run(["blkid", "-s", "UUID", "-o", "value", f"{loop_dev}p1"], capture_output=True, text=True)
                root_uuid_res = subprocess.run(["blkid", "-s", "UUID", "-o", "value", f"{loop_dev}p2"], capture_output=True, text=True)
                
                boot_uuid = boot_uuid_res.stdout.strip()
                root_uuid = root_uuid_res.stdout.strip()
                
                fstab_content = f"UUID={root_uuid} / ext4 defaults 0 1\nUUID={boot_uuid} /boot vfat defaults 0 2\n"
                (mnt_root / "etc" / "fstab").write_text(fstab_content)
                
                # Board-specific final adjustments
                if self.arch.startswith("rpi"):
                    self.logger.info(f"[finalize] Updating cmdline.txt for Raspberry Pi...")
                    root_partuuid_res = subprocess.run(["blkid", "-s", "PARTUUID", "-o", "value", f"{loop_dev}p2"], capture_output=True, text=True)
                    root_partuuid = root_partuuid_res.stdout.strip()
                    
                    cmdline_txt = mnt_root / "boot" / "cmdline.txt"
                    if cmdline_txt.exists():
                        import re
                        content = cmdline_txt.read_text()
                        content = re.sub(r'root=[^ ]+', f'root=PARTUUID={root_partuuid}', content)
                        cmdline_txt.write_text(content)
                
                elif self.arch == "pinebookpro":
                    self.logger.info(f"[finalize] Flashing Pinebook Pro U-Boot...")
                    uboot_dir = mnt_root / "usr" / "lib" / "pinebookpro-uboot"
                    if uboot_dir.exists():
                        subprocess.run(["dd", f"if={uboot_dir}/idbloader.img", f"of={loop_dev}", "bs=512", "seek=64", "conv=notrunc,fsync"], check=True)
                        subprocess.run(["dd", f"if={uboot_dir}/u-boot.itb", f"of={loop_dev}", "bs=512", "seek=16384", "conv=notrunc,fsync"], check=True)
                    else:
                        self.logger.warning("[finalize] U-Boot binaries not found in /usr/lib/pinebookpro-uboot!")
                    
                    from void_builder.utils.lib import mount_pseudofs, umount_pseudofs, run_cmd_chroot
                    try:
                        mount_pseudofs(str(mnt_root))
                        run_cmd_chroot(str(mnt_root), "xbps-reconfigure -f pinebookpro-kernel", check=False)
                    finally:
                        umount_pseudofs(str(mnt_root))
                
                elif self.arch in ("asahi", "x13s"):
                    self.logger.info(f"[finalize] Installing GRUB EFI for {self.arch}...")
                    from void_builder.utils.lib import mount_pseudofs, umount_pseudofs, run_cmd_chroot
                    try:
                        mount_pseudofs(str(mnt_root))
                        run_cmd_chroot(str(mnt_root), f"grub-install --target=arm64-efi --efi-directory=/boot --removable {loop_dev}", check=False)
                        kernel_pkg = "linux-asahi" if self.arch == "asahi" else "linux"
                        run_cmd_chroot(str(mnt_root), f"xbps-reconfigure -f {kernel_pkg}", check=False)
                    finally:
                        umount_pseudofs(str(mnt_root))
                    
            finally:
                subprocess.run(["umount", "-f", str(mnt_root / "boot")], check=False)
                subprocess.run(["umount", "-f", str(mnt_root)], check=False)
                try:
                    os.rmdir(str(mnt_root))
                except OSError:
                    pass
                
        finally:
            subprocess.run(["partx", "-d", loop_dev], check=False)
            subprocess.run(["losetup", "-d", loop_dev], check=False)

        final_file = self._convert_disk_image(raw_staging, output_format, output_abs_path)
        self._generate_manifest_and_checksums(str(final_file))
        return str(final_file)
