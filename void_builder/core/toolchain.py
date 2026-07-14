import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("Toolchain")

class ToolchainManager:
    def __init__(
        self,
        workdir_base: Path,
        mode: str = "mock",
        force_isolated: bool = False,
        pacman_retries: int = 3,
        diagnostics_enabled: bool = False,
        diagnostics_log_path: Optional[Path] = None,
        pacman_cache_dir: Optional[Path] = None,
        arch: Optional[str] = None,
        update_toolchain: bool = False,
    ):
        self.mode = mode
        self.force_isolated = force_isolated
        self.toolchain_dir = workdir_base / "build_host"
        self.arch = arch or "x86_64"
        self.update_toolchain = update_toolchain
        self._is_ready = False
        
        # Tools directory path
        self.tools_dir = resolve_from_project("void_builder/tools")
        self.xbps_install_static = self.tools_dir / "usr" / "bin" / "xbps-install.static"
        self.proot = self.tools_dir / "proot"

    def setup(self):
        """Ensure static xbps and proot are available."""
        logger.info(f"[TOOLCHAIN] Initializing toolchain in {self.tools_dir}...")
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        
        self.host_dir = self.toolchain_dir / "void-host"
        self.target_dir = self.toolchain_dir / "void-target"
        
        if self.mode == "real":
            # Call the utility functions to download and extract them if missing
            from void_builder.utils.lib import ensure_static_xbps, ensure_proot
            ensure_static_xbps(str(self.tools_dir), force_update=self.update_toolchain)
            ensure_proot(str(self.tools_dir), force_update=self.update_toolchain)
            
            self.host_dir.mkdir(parents=True, exist_ok=True)
            self.target_dir.mkdir(parents=True, exist_ok=True)
            self._bootstrap_toolchain_dirs()
            
            self._is_ready = True
            logger.info("[TOOLCHAIN] Static toolchain binaries and isolated chroots ready.")
        else:
            logger.info("[TOOLCHAIN] [MOCK] Toolchain setup simulated.")
            self._is_ready = True

    def _copy_void_keys(self, target_dir: Path):
        key_dir = target_dir / "var" / "db" / "xbps" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        mklive_keys = resolve_from_project("configs/assets/keys")
        if mklive_keys.exists():
            for f in mklive_keys.glob("*.plist"):
                shutil.copy2(f, key_dir)

    def _get_host_arch(self) -> str:
        try:
            res = subprocess.run(["xbps-uhelper", "arch"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        import platform
        m = platform.machine()
        if m == "x86_64":
            return "x86_64"
        elif m in ("i386", "i686"):
            return "i686"
        elif m in ("aarch64", "arm64"):
            return "aarch64"
        return "x86_64"

    def _run_xbps_install(self, rootdir: Path, arch: str, packages: List[str], repos: List[str]):
        from void_builder.core.path_utils import resolve_from_project
        cache_dir = resolve_from_project("output/cache/xbps") / arch
        cache_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.xbps_install_static), "-S", "-r", str(rootdir),
            "-c", str(cache_dir),
            "-y"
        ]
        for repo in repos:
            cmd.extend(["-R", repo])
        cmd.extend(packages)

        cmd_env = os.environ.copy()
        cmd_env["XBPS_ARCH"] = arch

        logger.info(f"[TOOLCHAIN] Bootstrapping packages in {rootdir}: {', '.join(packages)}")
        res = subprocess.run(cmd, env=cmd_env)
        if res.returncode != 0:
            logger.error(f"[TOOLCHAIN] Bootstrap failed (exit {res.returncode}).")
            raise RuntimeError(f"Bootstrap failed with exit code {res.returncode}")

    def _bootstrap_toolchain_dirs(self):
        # 1. Copy keys
        self._copy_void_keys(self.host_dir)
        self._copy_void_keys(self.target_dir)

        # 2. Install host prereqs into self.host_dir
        host_arch = self._get_host_arch()
        repos = [
            "https://repo-default.voidlinux.org/current",
            "https://repo-default.voidlinux.org/current/musl",
            "https://repo-default.voidlinux.org/current/aarch64"
        ]
        
        from void_builder.utils.lib import filter_repositories
        host_repos = filter_repositories(repos, host_arch)
        host_pkgs = ["base-files", "libgcc", "dash", "coreutils", "sed", "tar", "gawk", "squashfs-tools", "xorriso"]
        self._run_xbps_install(self.host_dir, host_arch, host_pkgs, host_repos)

        # 3. Install target bootloader packages into self.target_dir
        target_pkgs = ["base-files", "bash", "mtools", "dosfstools"]
        if self.arch.startswith(("x86_64", "i686")):
            target_pkgs.extend(["syslinux", "grub-i386-efi", "grub-x86_64-efi", "memtest86+"])
        elif self.arch.startswith("aarch64"):
            target_pkgs.extend(["grub-arm64-efi"])
            
        target_repos = filter_repositories(repos, self.arch)
        self._run_xbps_install(self.target_dir, self.arch, target_pkgs, target_repos)

    def execute_command(
        self,
        command: List[str],
        chroot_path: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = False
    ) -> Tuple[int, str, str]:
        """Run a command inside the chroot (using proot or native chroot)."""
        if self.mode == "mock":
            logger.info(f"[TOOLCHAIN] [MOCK] Executing: {' '.join(command)}")
            return 0, "mock output", ""

        # Determine if we should run inside a chroot
        if chroot_path:
            chroot_path = Path(chroot_path)
            
            # Setup QEMU user static binary if not native
            from void_builder.utils.lib import is_target_native, setup_qemu_binfmt
            if not is_target_native(self.arch):
                setup_qemu_binfmt(self.arch)
                
            # Check host UID to decide on native chroot vs proot
            import os
            if os.geteuid() == 0:
                # Native chroot
                chroot_cmd = ["chroot", str(chroot_path), "/bin/sh", "-c", " ".join(command)]
                cmd_env = os.environ.copy()
                if env:
                    cmd_env.update(env)
                logger.info(f"[TOOLCHAIN] [REAL-CHROOT] Running: {' '.join(chroot_cmd)}")
                res = subprocess.run(chroot_cmd, env=cmd_env, text=True, capture_output=True)
                return res.returncode, res.stdout, res.stderr
            else:
                # Proot
                proot_bin = str(self.proot)
                proot_cmd = [
                    proot_bin, "-r", str(chroot_path), "-0", "-w", "/",
                    "-b", "/dev", "-b", "/sys", "-b", "/proc",
                    "/bin/sh", "-c", " ".join(command)
                ]
                cmd_env = os.environ.copy()
                if env:
                    cmd_env.update(env)
                logger.info(f"[TOOLCHAIN] [PROOT] Running: {' '.join(proot_cmd)}")
                res = subprocess.run(proot_cmd, env=cmd_env, text=True, capture_output=True)
                return res.returncode, res.stdout, res.stderr
        else:
            # Run directly on host
            logger.info(f"[TOOLCHAIN] [HOST] Running: {' '.join(command)}")
            cmd_env = os.environ.copy()
            if env:
                cmd_env.update(env)
            res = subprocess.run(command, env=cmd_env, text=True, capture_output=True)
            return res.returncode, res.stdout, res.stderr
