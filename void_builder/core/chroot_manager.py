import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from void_builder.utils.logger import setup_logger

logger = setup_logger("ChrootManager")

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

        if self._mounted:
            logger.info(f"[Chroot] Virtual filesystems already mounted at {self.chroot_path}.")
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

        if not self._mounted:
            logger.info(f"[Chroot] Virtual filesystems already unmounted at {self.chroot_path}.")
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

    def install_packages(self, plan: Dict[str, List[str]], repos: List[str] = None) -> None:
        """Install packages into the chroot using xbps-install.static."""
        packages = plan.get("official", [])
        if not packages:
            logger.info("[Chroot] No packages to install.")
            return

        # Determine package cache path
        from void_builder.core.path_utils import resolve_from_project
        cache_path_str = None
        if hasattr(self, "config") and self.config:
            system_cfg = self.config.get("system", {})
            cache_path_str = system_cfg.get("xbps_cache")
        
        if not cache_path_str:
            cache_path_str = "cache/xbps"
            
        import tempfile
        cache_dir = resolve_from_project(cache_path_str) / self.arch
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            probe = cache_dir / ".write_test"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
        except Exception:
            cache_dir = Path(tempfile.gettempdir()) / "void-builder-cache" / "xbps" / self.arch
            cache_dir.mkdir(parents=True, exist_ok=True)

        # Determine package repositories
        internal_repos = []
        config_repos = []
        if repos:
            config_repos.extend(repos)
        if hasattr(self, "config") and self.config:
            r = self.config.get("repositories")
            if isinstance(r, list):
                config_repos.extend(r)
            cr = self.config.get("custom_repositories")
            if isinstance(cr, list):
                config_repos.extend(cr)

        if config_repos:
            for r in config_repos:
                if r not in internal_repos:
                    internal_repos.append(r)
        else:
            if self.arch.endswith("-musl"):
                internal_repos.append("https://repo-default.voidlinux.org/current/musl")
            else:
                internal_repos.append("https://repo-default.voidlinux.org/current")

        # Auto-enable nonfree repository if requested by packages
        nonfree_pkgs = ("void-repo-nonfree", "unrar", "intel-ucode", "amd-ucode", "nvidia", "broadcom-wl")
        if any(any(p.startswith(n) for n in nonfree_pkgs) for p in packages):
            nonfree_repo = "https://repo-default.voidlinux.org/current/nonfree"
            if self.arch.endswith("-musl") or "musl" in self.arch:
                nonfree_repo = "https://repo-default.voidlinux.org/current/musl/nonfree"
            if nonfree_repo not in internal_repos:
                internal_repos.append(nonfree_repo)

        # Auto-enable multilib repositories if requested by packages on x86_64
        if self.arch == "x86_64" and any(p in packages for p in ("void-repo-multilib", "void-repo-multilib-nonfree", "steam", "wine")):
            for mrepo in ("https://repo-default.voidlinux.org/current/multilib", "https://repo-default.voidlinux.org/current/multilib/nonfree"):
                if mrepo not in internal_repos:
                    internal_repos.append(mrepo)

        # Filter repos to only use compatible ones for target arch
        from void_builder.utils.lib import filter_repositories
        internal_repos = filter_repositories(internal_repos, self.arch)

        logger.info(f"[Chroot] Installing {len(packages)} packages: {', '.join(packages)}")
        logger.info(f"[Chroot] Using package cache directory: {cache_dir}")
        logger.info(f"[Chroot] Using package repositories: {', '.join(internal_repos)}")

        # Copy repository public keys to the target chroot
        if self.mode == "real":
            self.toolchain._setup_keys(self.chroot_path)

        if self.mode == "mock":
            logger.info(f"[Chroot] [MOCK] Would install packages: {packages}")
            return

        xbps_install = str(self.toolchain.xbps_install_static)
        from void_builder.utils.lib import map_xbps_arch, is_target_native, setup_qemu_binfmt, copy_qemu_user_binary
        xbps_arch = map_xbps_arch(self.arch)
        is_native = is_target_native(self.arch)
        if not is_native:
            setup_qemu_binfmt(self.arch)
            copy_qemu_user_binary(self.arch, self.chroot_path)

        cmd_env = os.environ.copy()
        cmd_env["XBPS_ARCH"] = xbps_arch

        max_attempts = 3
        if hasattr(self, "toolchain") and hasattr(self.toolchain, "retries"):
            max_attempts = max(1, self.toolchain.retries)

        import time
        mirror_fallbacks = [
            ("https://repo-default.voidlinux.org", "https://repo-fi.voidlinux.org"),
            ("https://repo-default.voidlinux.org", "https://repo-de.voidlinux.org"),
            ("https://repo-default.voidlinux.org", "https://repo-fastly.voidlinux.org"),
        ]

        current_repos = list(internal_repos)
        last_rc = 1

        for attempt in range(1, max_attempts + 1):
            cmd = [
                xbps_install, "-S", "-r", str(self.chroot_path),
                "-c", str(cache_dir),
            ]
            for repo in current_repos:
                cmd.extend(["-R", repo])
            cmd.extend(["-y", "-U"])
            cmd.extend(packages)

            logger.info(f"[Chroot] Running host-side xbps-install.static (attempt {attempt}/{max_attempts}) for {xbps_arch}...")
            res = subprocess.run(cmd, env=cmd_env)
            if res.returncode == 0:
                logger.info("[Chroot] Package installation completed successfully.")
                return

            last_rc = res.returncode
            logger.warning(f"[Chroot] Package installation attempt {attempt} failed with exit code {res.returncode}.")
            if attempt < max_attempts:
                for old_m, new_m in mirror_fallbacks:
                    if any(old_m in r for r in current_repos):
                        current_repos = [r.replace(old_m, new_m) for r in current_repos]
                        logger.info(f"[Chroot] Retrying with alternative mirror: {new_m}")
                        break
                time.sleep(2 * attempt)

        logger.error(f"[Chroot] Package installation failed after {max_attempts} attempts (exit {last_rc}).")
        raise ChrootError(f"Package installation failed with exit code {last_rc}")

    def run_reconfigure(self) -> None:
        """Perform 3-pass package reconfiguration inside Void Linux rootfs."""
        if self.mode == "mock":
            logger.info("[Chroot] [MOCK] Would run 3-pass reconfiguration.")
            return

        logger.info("[Chroot] Starting 3-pass package reconfiguration...")

        # Ensure QEMU user binary is in chroot for foreign arch
        from void_builder.utils.lib import is_target_native, copy_qemu_user_binary
        if not is_target_native(self.arch):
            copy_qemu_user_binary(self.arch, self.chroot_path)
        
        # Pass 1: Reconfigure base-files from host (if native)
        from void_builder.utils.lib import is_target_native
        if is_target_native(self.arch):
            import shutil
            if shutil.which("xbps-reconfigure"):
                from void_builder.utils.lib import map_xbps_arch
                xbps_arch = map_xbps_arch(self.arch)

                cmd_env = os.environ.copy()
                cmd_env["XBPS_ARCH"] = xbps_arch
                subprocess.run(
                    ["xbps-reconfigure", "--rootdir", str(self.chroot_path), "base-files"],
                    env=cmd_env, capture_output=True
                )
        
        # Pass 2: Reconfigure base-files inside chroot
        try:
            self.run_command("env -i xbps-reconfigure -f base-files", check=False)
        except Exception as e:
            logger.warning(f"[Chroot] Reconfiguring base-files in chroot warned: {e}")

        # Pass 2.5: Reconfigure DKMS beforehand if present (creates /var/lib/dkms before modules configure)
        try:
            self.run_command("env -i xbps-reconfigure dkms", check=False)
        except Exception:
            pass

        # Pass 3: Reconfigure all packages inside chroot
        try:
            self.run_command("xbps-reconfigure -a", check=False)
        except Exception as e:
            logger.warning(f"[Chroot] Reconfiguring all packages in chroot warned: {e}")

        # Set default /bin/sh alternative to dash if installed (matches void-mklive)
        try:
            self.run_command("xbps-alternatives -s dash", check=False)
        except Exception:
            pass

        # Autoload dm-raid if module is present (prevents boot failure on RAID disks)
        try:
            modules_load_dir = self.chroot_path / "etc" / "modules-load.d"
            modules_load_dir.mkdir(parents=True, exist_ok=True)
            modules_path = self.chroot_path / "usr" / "lib" / "modules"
            if modules_path.exists():
                for ko in modules_path.glob("*/kernel/drivers/md/dm-raid.ko*"):
                    (modules_load_dir / "dm-raid.conf").write_text("dm-raid\n", encoding="utf-8")
                    break
        except Exception:
            pass
