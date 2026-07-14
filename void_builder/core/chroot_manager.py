import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ChrootManager")

class ChrootError(Exception):
    """Exception raised for ChrootManager operations."""
    pass

class ChrootManager:
    def __init__(
        self,
        chroot_path: Path,
        toolchain,
        mode: str = "mock",
        arch: Optional[str] = None,
        chroot_mode: str = "chroot",
        config: Optional[Any] = None,
    ):
        self.chroot_path = Path(chroot_path)
        self.toolchain = toolchain
        self.mode = mode
        self.arch = arch or "x86_64"
        self._mounted = False
        self.config = config

    def mount(self) -> None:
        """Mount virtual filesystems into the chroot if running in real root mode."""
        if self.mode != "real":
            return
        
        import os
        if os.geteuid() != 0:
            # Under proot we do not mount virtual filesystems manually
            return

        from void_builder.utils.lib import mount_pseudofs
        logger.info(f"[Chroot] Mounting virtual filesystems at {self.chroot_path}...")
        mount_pseudofs(str(self.chroot_path))
        self._mounted = True

    def umount(self) -> None:
        """Unmount virtual filesystems."""
        if self.mode != "real":
            return
            
        import os
        if os.geteuid() != 0:
            return

        from void_builder.utils.lib import umount_pseudofs
        logger.info(f"[Chroot] Unmounting virtual filesystems at {self.chroot_path}...")
        umount_pseudofs(str(self.chroot_path))
        self._mounted = False

    def run_command(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
    ) -> str:
        """Run a shell command string inside the chroot."""
        if self.mode == "mock":
            logger.info(f"[Chroot] [MOCK] Command inside chroot: {command}")
            return "mock chroot output"

        # Execute as a shell string inside toolchain
        ret, stdout, stderr = self.toolchain.execute_command(
            [command],
            chroot_path=self.chroot_path,
            env=env
        )
        if ret != 0 and check:
            raise ChrootError(f"Chroot command failed (exit {ret}): {stderr or stdout}")
        return stdout

    def install_packages(self, plan: Dict[str, List[str]]) -> None:
        """Install packages into the chroot using xbps-install.static."""
        packages = plan.get("official", [])
        if not packages:
            logger.info("[Chroot] No packages to install.")
            return

        logger.info(f"[Chroot] Installing {len(packages)} packages: {', '.join(packages)}")
        if self.mode == "mock":
            logger.info(f"[Chroot] [MOCK] Would install packages: {packages}")
            return

        # Target repository
        repo_url = "https://repo-default.voidlinux.org/current"

        # Determine package cache path
        from void_builder.core.path_utils import resolve_from_project
        cache_path_str = None
        if hasattr(self, "config") and self.config:
            cache_path_str = self.config.get("system.xbps_cache")
        
        if not cache_path_str:
            cache_path_str = "output/cache/xbps"
            
        cache_dir = resolve_from_project(cache_path_str)
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Chroot] Using package cache directory: {cache_dir}")

        xbps_install = str(self.toolchain.xbps_install_static)
        cmd = [
            xbps_install, "-S", "-r", str(self.chroot_path),
            "-c", str(cache_dir),
            "-R", repo_url, "-y"
        ] + list(packages)

        cmd_env = os.environ.copy()
        cmd_env["XBPS_ARCH"] = self.arch

        logger.info(f"[Chroot] Running host-side xbps-install.static: {' '.join(cmd)}")
        res = subprocess.run(cmd, env=cmd_env, text=True, capture_output=True)
        if res.returncode != 0:
            logger.error(f"[Chroot] Package installation failed (exit {res.returncode}): {res.stderr}")
            raise ChrootError(f"Package installation failed: {res.stderr}")

        logger.info("[Chroot] Package installation completed successfully.")

    def run_reconfigure(self) -> None:
        """Perform 3-pass package reconfiguration inside Void Linux rootfs."""
        if self.mode == "mock":
            logger.info("[Chroot] [MOCK] Would run 3-pass reconfiguration.")
            return

        logger.info("[Chroot] Starting 3-pass package reconfiguration...")
        
        # Pass 1: Reconfigure base-files from host (if native)
        from void_builder.utils.lib import is_target_native
        if is_target_native(self.arch):
            import shutil
            if shutil.which("xbps-reconfigure"):
                cmd_env = os.environ.copy()
                cmd_env["XBPS_ARCH"] = self.arch
                subprocess.run(
                    ["xbps-reconfigure", "--rootdir", str(self.chroot_path), "base-files"],
                    env=cmd_env, capture_output=True
                )
        
        # Pass 2: Reconfigure base-files inside chroot
        try:
            self.run_command("env -i xbps-reconfigure -f base-files", check=False)
        except Exception as e:
            logger.warning(f"[Chroot] Reconfiguring base-files in chroot warned: {e}")

        # Pass 3: Reconfigure all packages inside chroot
        try:
            self.run_command("xbps-reconfigure -a", check=False)
        except Exception as e:
            logger.warning(f"[Chroot] Reconfiguring all packages in chroot warned: {e}")
