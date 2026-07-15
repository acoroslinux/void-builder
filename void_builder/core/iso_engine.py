from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Type, Union

from void_builder.core.config_loader import Config
from void_builder.core.bootloaders.grub2 import Grub2Bootloader
from void_builder.core.bootloaders.syslinux import SyslinuxBootloader
from void_builder.core.chroot_manager import ChrootManager
from void_builder.core.customizer import SystemConfigurator
from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("ISOBuilder")
_ENGINE_REGISTRY: Dict[str, Type["BaseEngine"]] = {}

class ISOBuilderError(Exception):
    """Raised when the build orchestration flow cannot proceed."""
    pass


class ISOEngine(ABC):
    """Abstract base for architecture-specific build engines."""

    @classmethod
    def register(cls, arch_name: str):
        def decorator(engine_class: Type["BaseEngine"]):
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
            or "void-builder/workdir"
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

        if self.config.get("desktop_environment") or any(d in str(official_all) for d in ("xfce", "kde", "gnome", "mate")):
            common_desktop = self._normalize_packages(self._cfg_get("common_desktop_packages", []))
            official_all.extend(pkg for pkg in common_desktop if pkg not in official_all)

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
    def finalize_isofile(self, output_path: str) -> None:
        """Produce the final ISO file."""


@ISOEngine.register("x86_64")
@ISOEngine.register("x86_64-musl")
@ISOEngine.register("i686")
@ISOEngine.register("aarch64")
@ISOEngine.register("aarch64-musl")
@ISOEngine.register("armv7l")
@ISOEngine.register("armv7l-musl")
@ISOEngine.register("armv6l")
@ISOEngine.register("armv6l-musl")
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

        repos = self._cfg_get("repositories", []) + self._cfg_get("custom_repositories", [])
        
        # Support for Custom Local Packages (e.g. Calamares)
        local_pkgs_dir_str = self.config.get("system", {}).get("local_packages_dir", "custom_packages")
        local_pkgs_dir = resolve_from_project(local_pkgs_dir_str)
        
        if local_pkgs_dir.exists() and local_pkgs_dir.is_dir():
            has_xbps = any(local_pkgs_dir.glob("*.xbps"))
            if has_xbps:
                self.logger.info(f"[Packages] Found custom local packages in {local_pkgs_dir}. Indexing...")
                import subprocess
                try:
                    subprocess.run(["xbps-rindex", "-a", f"{local_pkgs_dir}/*.xbps"], shell=True, check=True)
                    repos.insert(0, str(local_pkgs_dir))  # Insert at priority 0
                    self.logger.info(f"[Packages] Added local repository to the front: {local_pkgs_dir}")
                except Exception as e:
                    self.logger.warning(f"[Packages] Failed to index local packages: {e}")
            else:
                self.logger.debug(f"[Packages] No .xbps files found in {local_pkgs_dir}")

        chroot_manager.install_packages(plan["official"], repos=repos)

    def post_install_configure(self) -> None:
        chroot_manager = getattr(self.toolchain, "chroot_manager", None)
        if not chroot_manager:
            raise ISOBuilderError("ChrootManager missing.")

        # 1. Mount virtual systems
        chroot_manager.mount()

        # 2. Run system configuration / customizations
        self.logger.info("[post_install] Running customizations through configurator...")
        configurator = SystemConfigurator(chroot_manager)
        configurator.load_from_config(self.config)
        configurator.apply()

        # 3. 3-pass package reconfigure
        self.logger.info("[post_install] Running Void 3-pass reconfigure...")
        chroot_manager.run_reconfigure()

        # 4. Cleanup rootfs before unmounting (cache, tmp, dracut modules)
        self.logger.info("[post_install] Cleaning up rootfs caches and temporary files...")
        chroot_manager.run_command("rm -rf /var/cache/xbps/*", check=False)
        chroot_manager.run_command("rm -rf /var/tmp/* /tmp/* /run/*", check=False)
        chroot_manager.run_command("rm -rf /usr/lib/dracut/modules.d/01vmklive", check=False)

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
        modules_dir = chroot_boot.parent / "lib" / "modules"
        if modules_dir.is_dir():
            versions_dirs = [d for d in modules_dir.iterdir() if d.is_dir()]
            if versions_dirs:
                versions_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                kernel_version = versions_dirs[0].name
                self.logger.info(f"[bootloaders] Staging kernel version: {kernel_version}")

                # Copy the specific kernel matched to the initrd
                vmlinuz_src = chroot_boot / f"vmlinuz-{kernel_version}"
                vmlinux_src = chroot_boot / f"vmlinux-{kernel_version}"
                
                if vmlinuz_src.exists():
                    shutil.copy2(vmlinuz_src, staging_boot / kernel_name)
                    kernel_found = True
                elif vmlinux_src.exists():
                    shutil.copy2(vmlinux_src, staging_boot / kernel_name)
                    kernel_found = True
                
                # Copy the strictly custom initrd generated by our dracut run (NOT the xbps generic ones)
                initrd_src = chroot_boot / "initrd"
                if initrd_src.exists():
                    shutil.copy2(initrd_src, staging_boot / "initrd")
                    initrd_found = True

        if not kernel_found or not initrd_found:
            self.logger.warning("[bootloaders] Kernel or initramfs not found in chroot /boot. Using mock placeholders.")
            if getattr(self.toolchain, "mode", "mock") == "mock":
                (staging_boot / kernel_name).write_text("mock-kernel")
                (staging_boot / "initrd").write_text("mock-initrd")
            else:
                raise ISOBuilderError("Real build failed: kernel or initramfs missing in target chroot.")

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
        grub = Grub2Bootloader(self.config, root_device_id="VOID_LIVE", kernel_version=kernel_version)
        grub.prepare_files(self.iso_staging)
        grub.generate_boot_image(self.iso_staging, bootloader_chroot)

    def _create_squashfs(self) -> None:
        """Create the squashed root filesystem (wrapped in ext3fs.img for dmsquash-live)."""
        self.logger.info("=== Step 4: Compressing Root Filesystem ===")

        liveos_dir = self.iso_staging / "LiveOS"
        liveos_dir.mkdir(parents=True, exist_ok=True)
        squashfs_img = liveos_dir / "squashfs.img"

        if squashfs_img.exists():
            self.logger.info("SquashFS already exists, skipping compression.")
            return

        if getattr(self.toolchain, "mode", "mock") == "mock":
            self.logger.info(f"[MOCK] mksquashfs {self.chroot_path} {squashfs_img} -comp xz")
            squashfs_img.write_text("mock squashfs content")
            return

        import os
        import subprocess
        import tempfile
        import time
        import shutil

        # 1. Determine rootfs size
        try:
            res = subprocess.run(["du", "-sm", str(self.chroot_path)], capture_output=True, text=True, check=True)
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
            
            # 3. Run mkfs.ext3
            subprocess.run(["mkfs.ext3", "-F", "-m1", str(ext3_img)], check=True)
            
            # 4. Mount and copy
            mount_point = tmp_path / "mnt"
            mount_point.mkdir(parents=True, exist_ok=True)

            chroot_cmd = []
            if os.geteuid() != 0:
                chroot_cmd = ["sudo"]

            subprocess.run(chroot_cmd + ["mount", "-o", "loop", str(ext3_img), str(mount_point)], check=True)
            try:
                self.logger.info(f"Copying rootfs into ext3fs.img (Size: {img_size_mb}MB)...")
                subprocess.run(chroot_cmd + ["cp", "-a", f"{self.chroot_path}/.", str(mount_point)], check=True)
            finally:
                for _ in range(5):
                    res = subprocess.run(chroot_cmd + ["umount", "-f", str(mount_point)], capture_output=True)
                    if res.returncode == 0:
                        break
                    time.sleep(1)

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
            self.logger.info(f"[squashfs] Command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=False)

        self.logger.info(f"[squashfs] SquashFS created: {squashfs_img}")

    def finalize_isofile(self, output_path: str) -> None:
        # 1. Create squashfs
        self._create_squashfs()

        # 2. Xorriso ISO creation
        output_abs = str(resolve_from_project(output_path))
        Path(output_abs).parent.mkdir(parents=True, exist_ok=True)

        is_mock = getattr(self.toolchain, "mode", "mock") == "mock"
        iso_label = self._cfg_get("system.iso_label", "VOID_LIVE")

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
            isohdpfx_path = self.chroot_path / "usr" / "lib" / "syslinux" / "isohdpfx.bin"
            if isohdpfx_path.exists():
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
            return

        self.logger.info(f"[finalize] Creating bootable hybrid ISO with xorriso: {output_abs}")
        self.logger.info(f"[finalize] Command: {' '.join(command)}")

        import subprocess
        res = subprocess.run(command, capture_output=True, text=True)
        if res.returncode != 0:
            if Path(output_abs).exists() and Path(output_abs).stat().st_size > 1000000:
                self.logger.warning(
                    f"xorriso reported an exit error/crash ({res.stderr}), "
                    f"but the ISO file was successfully generated at {output_abs}."
                )
            else:
                self.logger.error(f"xorriso failed: {res.stderr}")
                raise ISOBuilderError(f"xorriso failed: {res.stderr}")

        self.logger.info(f"[finalize] Bootable ISO created: {output_abs}")


class ISOBuilder:
    """Canonical high-level build orchestrator used by the project."""

    def __init__(self, arch: str, config: Config, toolchain: Any):
        self.arch = arch
        self.config = config
        self.toolchain = toolchain
        
        # Instantiate the correct engine based on target architecture
        engine_cls = _ENGINE_REGISTRY.get(arch)
        if not engine_cls:
            raise ISOBuilderError(f"No build engine registered for architecture '{arch}'.")
        self.engine = engine_cls(arch, config, toolchain)

    def build(self, output_path: str, workdir: Optional[str] = None) -> str:
        """Execute the full build pipeline."""
        logger.info(f"=== Starting build pipeline for architecture {self.arch} ===")

        # 1. Setup workdir
        workdir_path = self.engine.setup_workdir(workdir)

        # 2. Setup chroot environment
        self.engine.setup_chroot(str(workdir_path))

        # 3. Install packages
        self.engine.install_packages()

        # 4. Run post-install configuration & customizations
        self.engine.post_install_configure()

        # 5. Build bootloaders
        self.engine.build_bootloaders(str(workdir_path))

        # 6. Finalize ISO file
        self.engine.finalize_isofile(output_path)

        logger.info("=== Build completed successfully! ===")
        return str(resolve_from_project(output_path))
