import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("Toolchain")

class ToolchainManager:
    def __init__(
        self,
        workdir_base: Path,
        mode: str = "mock",
        force_isolated: bool = False,
        arch: Optional[str] = None,
        update_toolchain: bool = False,
        retries: int = 3,
        **kwargs: Any,
    ):
        self.mode = mode
        self.force_isolated = force_isolated
        self.toolchain_dir = Path(workdir_base) / "build_host"
        self.arch = arch or "x86_64"
        self.update_toolchain = update_toolchain
        self.retries = retries
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

    def _setup_keys(self, target_dir: Path):
        key_dir = target_dir / "var/db/xbps/keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        
        mklive_keys = resolve_from_project("configs/assets/keys")
        if mklive_keys.exists():
            for f in mklive_keys.glob("*.plist"):
                shutil.copy2(f, key_dir)

    _copy_void_keys = _setup_keys

    def _get_host_arch(self) -> str:
        from void_builder.utils.lib import get_host_arch
        return get_host_arch()

    def _run_xbps_install(self, rootdir: Path, arch: str, packages: List[str], repos: List[str], unpack_only: bool = False):
        from void_builder.core.path_utils import resolve_from_project
        import tempfile
        cache_dir = resolve_from_project("cache/xbps") / arch
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            probe = cache_dir / ".write_test"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
        except Exception:
            cache_dir = Path(tempfile.gettempdir()) / "void-builder-cache" / "xbps" / arch
            cache_dir.mkdir(parents=True, exist_ok=True)

        from void_builder.utils.lib import map_xbps_arch
        xbps_arch = map_xbps_arch(arch)

        cmd_env = os.environ.copy()
        cmd_env["XBPS_ARCH"] = xbps_arch

        mirror_fallbacks = [
            ("https://repo-default.voidlinux.org", "https://repo-fi.voidlinux.org"),
            ("https://repo-default.voidlinux.org", "https://repo-de.voidlinux.org"),
            ("https://repo-default.voidlinux.org", "https://repo-fastly.voidlinux.org"),
        ]

        current_repos = list(repos)
        max_attempts = max(1, getattr(self, "retries", 3))
        last_error_code = 1

        import time
        for attempt in range(1, max_attempts + 1):
            cmd = [
                str(self.xbps_install_static), "-S", "-r", str(rootdir),
                "-c", str(cache_dir),
                "-y"
            ]
            if unpack_only:
                cmd.append("-U")
            for repo in current_repos:
                cmd.extend(["-R", repo])
            cmd.extend(packages)

            logger.info(f"[TOOLCHAIN] Bootstrapping packages (attempt {attempt}/{max_attempts}) in {rootdir}: {', '.join(packages)}")
            res = subprocess.run(cmd, env=cmd_env)
            if res.returncode == 0:
                return

            last_error_code = res.returncode
            logger.warning(f"[TOOLCHAIN] Bootstrap attempt {attempt} failed with exit code {res.returncode}.")
            if attempt < max_attempts:
                # Try replacing primary mirror with a healthy mirror fallback
                for old_m, new_m in mirror_fallbacks:
                    if any(old_m in r for r in current_repos):
                        current_repos = [r.replace(old_m, new_m) for r in current_repos]
                        logger.info(f"[TOOLCHAIN] Retrying with alternative mirror: {new_m}")
                        break
                time.sleep(2 * attempt)

        logger.error(f"[TOOLCHAIN] Bootstrap failed after {max_attempts} attempts (exit {last_error_code}).")
        raise RuntimeError(f"Bootstrap failed with exit code {last_error_code}")

    # ------------------------------------------------------------------
    # Arch-mismatch detection helpers
    # ------------------------------------------------------------------

    _ARCH_MARKER = ".arch"

    def _read_dir_arch(self, directory: Path) -> Optional[str]:
        """Return the arch stored in the marker file, or None if absent."""
        marker = directory / self._ARCH_MARKER
        try:
            return marker.read_text().strip() or None
        except OSError:
            return None

    def _write_dir_arch(self, directory: Path, arch: str) -> None:
        """Write (or overwrite) the arch marker file inside *directory*."""
        (directory / self._ARCH_MARKER).write_text(arch)

    def _wipe_dir(self, directory: Path) -> None:
        """Remove all contents of *directory* while keeping the directory itself."""
        import shutil
        if directory.exists():
            logger.info(f"[TOOLCHAIN] Arch mismatch — wiping stale dir: {directory}")
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)

    def _bootstrap_toolchain_dirs(self):
        from void_builder.utils.lib import filter_repositories, is_target_native

        host_arch = self._get_host_arch()

        # Wipe host_dir if it was previously built for a different host arch.
        stored_host_arch = self._read_dir_arch(self.host_dir)
        if stored_host_arch and stored_host_arch != host_arch:
            logger.warning(
                f"[TOOLCHAIN] host_dir arch mismatch: stored={stored_host_arch}, "
                f"current={host_arch}. Rebuilding."
            )
            self._wipe_dir(self.host_dir)

        # Wipe target_dir if it was previously built for a different target arch.
        from void_builder.utils.lib import map_xbps_arch
        canonical_target = map_xbps_arch(self.arch)
        stored_target_arch = self._read_dir_arch(self.target_dir)
        if stored_target_arch and stored_target_arch != canonical_target:
            logger.warning(
                f"[TOOLCHAIN] target_dir arch mismatch: stored={stored_target_arch}, "
                f"current={canonical_target}. Rebuilding."
            )
            self._wipe_dir(self.target_dir)

        # 1. Copy keys (after possible wipe)
        self._setup_keys(self.host_dir)
        self._setup_keys(self.target_dir)

        # 2. Install host prereqs into self.host_dir
        repos = [
            "https://repo-default.voidlinux.org/current",
            "https://repo-default.voidlinux.org/current/musl",
            "https://repo-default.voidlinux.org/current/aarch64"
        ]

        host_repos = filter_repositories(repos, host_arch)
        host_pkgs = ["base-files", "libgcc", "dash", "coreutils", "sed", "tar", "gawk", "squashfs-tools", "xorriso", "dosfstools", "mtools", "grub"]
        self._run_xbps_install(self.host_dir, host_arch, host_pkgs, host_repos)
        self._write_dir_arch(self.host_dir, host_arch)

        # 3. Install target bootloader packages into self.target_dir (unpack only)
        target_pkgs = []
        if self.arch.startswith(("x86_64", "i686")):
            target_pkgs.extend(["syslinux", "grub-i386-efi", "grub-x86_64-efi", "memtest86+"])
        elif self.arch.startswith("aarch64") or "aarch64" in self.arch or "arm" in self.arch:
            target_pkgs.extend(["grub-arm64-efi"])

        if target_pkgs:
            target_repos = filter_repositories(repos, self.arch)
            self._run_xbps_install(self.target_dir, self.arch, target_pkgs, target_repos, unpack_only=True)
            self._write_dir_arch(self.target_dir, canonical_target)

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
            from void_builder.utils.lib import is_target_native, setup_qemu_binfmt, map_xbps_arch
            canonical_arch = map_xbps_arch(self.arch)
            if not is_target_native(canonical_arch):
                setup_qemu_binfmt(canonical_arch)
                
            # Check host UID to decide on native chroot vs proot
            import os
            import shlex
            if len(command) == 1:
                cmd_to_run = command[0]
            else:
                cmd_to_run = shlex.join(command)

            if os.geteuid() == 0:
                # Native chroot
                chroot_cmd = ["chroot", str(chroot_path), "/bin/sh", "-c", cmd_to_run]
                cmd_env = os.environ.copy()
                if env:
                    cmd_env.update(env)
                logger.info(f"[TOOLCHAIN] [REAL-CHROOT] Running: {' '.join(chroot_cmd)}")
                res = subprocess.run(chroot_cmd, env=cmd_env, text=True, capture_output=True)
                return res.returncode, res.stdout, res.stderr
            else:
                # Unprivileged container execution
                proot_bin = str(self.proot)
                has_proot = self.proot.exists()
                has_bwrap = bool(shutil.which("bwrap"))

                if has_proot:
                    runner_cmd = [
                        proot_bin, "-r", str(chroot_path), "-0", "-w", "/",
                        "-b", "/dev", "-b", "/sys", "-b", "/proc",
                        "/bin/sh", "-c", cmd_to_run
                    ]
                    logger.info(f"[TOOLCHAIN] [PROOT] Running: {' '.join(runner_cmd)}")
                elif has_bwrap:
                    runner_cmd = [
                        "bwrap",
                        "--bind", str(chroot_path), "/",
                        "--dev", "/dev",
                        "--proc", "/proc",
                        "--dir", "/sys",
                        "--uid", "0",
                        "--gid", "0",
                        "--chdir", "/",
                        "/bin/sh", "-c", cmd_to_run
                    ]
                    logger.info(f"[TOOLCHAIN] [BWRAP] Running: {' '.join(runner_cmd)}")
                else:
                    # Fallback to xbps-uunshare if available
                    uunshare_bin = self.tools_dir / "usr" / "bin" / "xbps-uunshare.static"
                    if uunshare_bin.exists():
                        runner_cmd = [str(uunshare_bin), str(chroot_path), "/bin/sh", "-c", cmd_to_run]
                        logger.info(f"[TOOLCHAIN] [XBPS-UUNSHARE] Running: {' '.join(runner_cmd)}")
                    else:
                        raise RuntimeError("No unprivileged container runner available (proot or bwrap required).")

                cmd_env = os.environ.copy()
                if env:
                    cmd_env.update(env)
                res = subprocess.run(runner_cmd, env=cmd_env, text=True, capture_output=True)
                return res.returncode, res.stdout, res.stderr
        else:
            # Run directly on host
            logger.info(f"[TOOLCHAIN] [HOST] Running: {' '.join(command)}")
            cmd_env = os.environ.copy()
            if env:
                cmd_env.update(env)
            res = subprocess.run(command, env=cmd_env, text=True, capture_output=True)
            return res.returncode, res.stdout, res.stderr

    def run_in_build_host(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
    ) -> Tuple[int, str, str]:
        """Execute host-level toolchain commands (truncate, mkfs, mcopy, etc.)."""
        if self.mode == "mock":
            logger.info(f"[TOOLCHAIN] [MOCK-HOST] Executing: {' '.join(command)}")
            return 0, "mock output", ""

        # Prefer running with isolated host_dir PATH if available
        cmd_env = os.environ.copy()
        if hasattr(self, "host_dir") and self.host_dir and self.host_dir.exists():
            bin_dir = str(self.host_dir / "usr" / "bin")
            sbin_dir = str(self.host_dir / "usr" / "sbin")
            cmd_env["PATH"] = f"{bin_dir}:{sbin_dir}:{cmd_env.get('PATH', '')}"

        if env:
            cmd_env.update(env)

        logger.info(f"[TOOLCHAIN] [BUILD-HOST] Executing: {' '.join(command)}")
        res = subprocess.run(command, env=cmd_env, text=True, capture_output=True)
        if check and res.returncode != 0:
            raise RuntimeError(
                f"Command '{' '.join(command)}' failed with exit code {res.returncode}: {res.stderr or res.stdout}"
            )
        return res.returncode, res.stdout, res.stderr
