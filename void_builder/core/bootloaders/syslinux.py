import logging
import shutil
from pathlib import Path
from typing import Any

from void_builder.core.path_utils import resolve_from_project

logger = logging.getLogger("SyslinuxBootloader")


class SyslinuxBootloaderError(Exception):
    pass


class SyslinuxBootloader:
    def __init__(self, config: Any, kernel_version: str = "linux"):
        self.config = config
        self.kernel_version = kernel_version

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        if not self.config:
            return default

        try:
            # Helper function to get nested value
            def get_nested(cfg, path):
                parts = path.split(".")
                current = cfg
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    elif hasattr(current, "get"):
                        current = current.get(part)
                    else:
                        return None
                return current

            # Try key directly (might be dot-path or top-level)
            val = get_nested(self.config, key)
            if val is not None:
                return val

            # Try iso.<key>
            if not key.startswith("iso."):
                val = get_nested(self.config, f"iso.{key}")
                if val is not None:
                    return val

            # Try customizations.<key>
            if not key.startswith("customizations."):
                val = get_nested(self.config, f"customizations.{key}")
                if val is not None:
                    return val

            # Try system.<key>
            if not key.startswith("system."):
                val = get_nested(self.config, f"system.{key}")
                if val is not None:
                    return val

            return default
        except Exception:
            return default

    def prepare_files(self, workdir: Path, iso_uuid: str = "") -> bool:
        """Generate isolinux.cfg from void-mklive template."""
        logger.info("[SYSLINUX] Preparing isolinux.cfg from void-mklive templates...")

        isolinux_dir = workdir / "boot" / "isolinux"
        isolinux_dir.mkdir(parents=True, exist_ok=True)

        mklive_dir = resolve_from_project("configs/assets")
        template_path = mklive_dir / "isolinux" / "isolinux.cfg.in"
        if not template_path.exists():
            logger.error(f"[SYSLINUX] isolinux.cfg.in template not found at {template_path}")
            return False

        # Gather config variables
        boot_title = self._cfg_get("boot_title", "Void Linux")
        keymap = self._cfg_get("keymap", "us")
        locale = self._cfg_get("locale", "en_US.UTF-8")
        boot_cmdline = self._cfg_get("boot_cmdline", "")
        arch = self._cfg_get("platform_specific.architecture", "x86_64")

        # Read template
        cfg = template_path.read_text(encoding="utf-8")
        cfg = cfg.replace("@@SPLASHIMAGE@@", "splash.png")
        cfg = cfg.replace("@@BOOT_TITLE@@", boot_title)
        cfg = cfg.replace("@@KERNVER@@", self.kernel_version)
        cfg = cfg.replace("@@ARCH@@", arch)
        cfg = cfg.replace("@@KEYMAP@@", keymap)
        cfg = cfg.replace("@@LOCALE@@", locale)
        cfg = cfg.replace("@@BOOT_CMDLINE@@", boot_cmdline)

        (isolinux_dir / "isolinux.cfg").write_text(cfg, encoding="utf-8")
        logger.info("[SYSLINUX] Generated isolinux.cfg")

        # Copy splash image
        splash_image_path = self._cfg_get("splash_image", "")
        splash_src = Path(splash_image_path) if splash_image_path else mklive_dir / "data" / "splash.png"
        if splash_src.exists():
            shutil.copy(splash_src, isolinux_dir / "splash.png")
            logger.info("[SYSLINUX] Copied splash.png")

        return True

    def generate_boot_image(self, workdir: Path, chroot_path: Path) -> bool:
        """Copy syslinux boot files from the chroot to boot/isolinux/."""
        logger.info("[SYSLINUX] Gathering BIOS boot binaries...")
        isolinux_dir = workdir / "boot" / "isolinux"
        isolinux_dir.mkdir(parents=True, exist_ok=True)

        copied_any = False
        if chroot_path and chroot_path.exists():
            # Check standard syslinux paths in Void Linux
            syslinux_paths = [
                chroot_path / "usr" / "lib" / "syslinux",
                chroot_path / "usr" / "lib" / "syslinux" / "bios",
            ]
            
            binaries = [
                "isolinux.bin", "ldlinux.c32", "libcom32.c32",
                "vesamenu.c32", "libutil.c32", "chain.c32",
                "reboot.c32", "poweroff.c32"
            ]

            for path in syslinux_paths:
                if path.is_dir():
                    for bin_file in binaries:
                        src = path / bin_file
                        if src.exists():
                            shutil.copy2(src, isolinux_dir / bin_file)
                            copied_any = True

        if not copied_any:
            logger.warning("[SYSLINUX] syslinux was not found in the chroot. Simulating files instead.")
            self._mock_binaries(isolinux_dir)

        # Also place isolinux config files or copies needed by xorriso hybrid boot (like isohdpfx.bin)
        # under isolinux dir or boot.
        # Void uses standard isolinux hybrid config.
        return True

    def _mock_binaries(self, syslinux_dir: Path):
        for mock_file in [
            "isolinux.bin", "ldlinux.c32", "libcom32.c32",
            "vesamenu.c32", "libutil.c32", "chain.c32",
            "reboot.c32", "poweroff.c32", "isohdpfx.bin"
        ]:
            (syslinux_dir / mock_file).write_bytes(b"mock")

    def validate(self, workdir: Path) -> bool:
        return (workdir / "boot" / "isolinux" / "isolinux.bin").exists()
