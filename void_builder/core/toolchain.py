import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from void_builder.core.path_utils import resolve_from_project

logger = logging.getLogger("Toolchain")

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
    ):
        self.mode = mode
        self.force_isolated = force_isolated
        self.toolchain_dir = workdir_base / "build_host"
        self.arch = arch or "x86_64"
        self._is_ready = False
        
        # Tools directory path
        self.tools_dir = resolve_from_project("void_builder/tools")
        self.xbps_install_static = self.tools_dir / "usr" / "bin" / "xbps-install.static"
        self.proot = self.tools_dir / "proot"

    def setup(self):
        """Ensure static xbps and proot are available."""
        logger.info(f"[TOOLCHAIN] Initializing toolchain in {self.tools_dir}...")
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        
        if self.mode == "real":
            # Call the utility functions to download and extract them if missing
            from void_builder.utils.lib import ensure_static_xbps, ensure_proot
            ensure_static_xbps(str(self.tools_dir))
            ensure_proot(str(self.tools_dir))
            self._is_ready = True
            logger.info("[TOOLCHAIN] Static toolchain binaries verified and ready.")
        else:
            logger.info("[TOOLCHAIN] [MOCK] Toolchain setup simulated.")
            self._is_ready = True

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
