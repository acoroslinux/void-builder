import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from void_builder.core.chroot_manager import ChrootError, ChrootManager
from void_builder.core.config_loader import ConfigLoader
from void_builder.core.iso_engine import Config, ISOBuilder, ISOBuilderError
from void_builder.core.path_utils import resolve_from_project
from void_builder.core.toolchain import ToolchainManager


class BuildOrchestratorError(Exception):
    """Exception raised for build orchestration failures."""
    pass


class BuildOrchestrator:
    """
    Coordinates the Void Linux build workflow.
    It ties together configuration, the Void build engine, and the chroot environment.
    """

    def __init__(
        self,
        arch: str,
        config_path: str,
        mode: str = "mock",
        clean: bool = True,
        force_isolated_toolchain: bool = False,
        toolchain_debug: bool = False,
        toolchain_debug_log: Optional[str] = None,
        toolchain_pacman_retries: int = 3,
        desktop: Optional[str] = None,
        kernel: Optional[str] = None,
        bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        live_profile: Optional[str] = None,
        live_user: Optional[str] = None,
        live_groups: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        repositories: Optional[List[str]] = None,
        include_dirs: Optional[List[str]] = None,
    ):
        VALID_ARCHS = (
            "x86_64", "x86_64-musl",
            "i686",
            "aarch64", "aarch64-musl",
            "armv7l", "armv7l-musl",
            "armv6l", "armv6l-musl",
        )
        self.arch = (arch or "x86_64").lower()
        if self.arch not in VALID_ARCHS:
            raise BuildOrchestratorError(
                f"Architecture '{self.arch}' is not supported. "
                f"Supported: {', '.join(VALID_ARCHS)}"
            )
        self.config_path = str(resolve_from_project(config_path))
        self.mode = mode
        self.clean = clean
        self.force_isolated_toolchain = force_isolated_toolchain
        self.toolchain_debug = toolchain_debug
        self.toolchain_debug_log = toolchain_debug_log
        self.desktop = desktop
        self.kernel = kernel
        self.bootloader = bootloader
        self.package_profiles = package_profiles or []
        self.service_profiles = service_profiles or []
        self.live_profile = live_profile
        self.live_user = live_user
        self.live_groups = live_groups or []
        self.platforms = platforms or []
        self.repositories = repositories or []
        self.include_dirs = include_dirs or []

        # Ensure default workspace custom files directory exists
        custom_files_dir = resolve_from_project("custom_files")
        if not custom_files_dir.exists():
            try:
                custom_files_dir.mkdir(parents=True, exist_ok=True)
                (custom_files_dir / ".gitkeep").touch()
            except Exception as e:
                print(f"[ORCHESTRATOR] Warning: Could not create custom_files directory: {e}")

        # Automatically add custom_files directory if it contains items besides .gitkeep
        if custom_files_dir.exists():
            has_items = any(item.name != ".gitkeep" for item in custom_files_dir.iterdir())
            if has_items:
                if str(custom_files_dir) not in self.include_dirs:
                    self.include_dirs.append(str(custom_files_dir))

        self.config_loader = ConfigLoader()
        self.builder: Optional[ISOBuilder] = None
        self.chroot: Optional[ChrootManager] = None
        self.toolchain: Optional[ToolchainManager] = None
        self.workdir: Optional[Path] = None

    def _resolve_writable_workdir(self, base_workdir: Path) -> Path:
        preferred = base_workdir / self.arch
        fallback = resolve_from_project(Path("void-builder") / "fallback" / self.arch)
        temp_fallback = Path(tempfile.gettempdir()) / "void-builder-fallback" / self.arch

        for candidate in (preferred, fallback, temp_fallback):
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".write_test"
                probe.write_text("ok")
                probe.unlink(missing_ok=True)
                if candidate != preferred:
                    print(
                        f"[ORCHESTRATOR] Workdir fallback active: {candidate}"
                    )
                return candidate
            except Exception:
                continue

        raise BuildOrchestratorError(
            f"No writable workdir available (checked: {preferred} and {fallback})."
        )

    def _setup(self):
        print(f"\n[ORCHESTRATOR] Starting build workflow for {self.arch}...")
        if self.desktop:
            print(f"[ORCHESTRATOR] Desktop profile: {self.desktop}")
        if self.kernel:
            print(f"[ORCHESTRATOR] Kernel selection: {self.kernel}")
        if self.bootloader:
            print(f"[ORCHESTRATOR] Bootloader selection: {self.bootloader}")
        if self.package_profiles:
            print(
                f"[ORCHESTRATOR] Package profiles: {', '.join(self.package_profiles)}"
            )
        if self.service_profiles:
            print(
                f"[ORCHESTRATOR] Service profiles: {', '.join(self.service_profiles)}"
            )
        if self.live_profile:
            print(f"[ORCHESTRATOR] Live profile: {self.live_profile}")
        if self.live_user:
            print(f"[ORCHESTRATOR] Live user override: {self.live_user}")
        if self.live_groups:
            print(
                f"[ORCHESTRATOR] Live user groups: {', '.join(self.live_groups)}"
            )
        if self.platforms:
            print(
                f"[ORCHESTRATOR] Target platforms: {', '.join(self.platforms)}"
            )

        # 1. Load and validate configuration using the assembler.
        from void_builder.core.config_loader import ConfigAssembler

        assembler = ConfigAssembler(str(Path(self.config_path).parent))
        try:
            self.config = assembler.assemble(
                target_arch=self.arch,
                target_desktop=self.desktop,
                target_kernel=self.kernel,
                target_bootloader=self.bootloader,
                package_profiles=self.package_profiles,
                service_profiles=self.service_profiles,
                target_live_profile=self.live_profile,
                live_user=self.live_user,
                live_groups=self.live_groups,
                platforms=self.platforms,
            )
        except Exception as e:
            raise BuildOrchestratorError(f"Failed to load configuration: {e}")

        if not self.config:
            raise BuildOrchestratorError("The generated configuration is null or invalid.")

        # Inject command line custom repositories
        if self.repositories:
            custom_repos = self.config._data.setdefault("custom_repositories", [])
            for r in self.repositories:
                if r not in custom_repos:
                    custom_repos.append(r)

        # Inject command line include directories
        if self.include_dirs:
            inc_dirs = self.config._data.setdefault("customizations", {}).setdefault("include_dirs", [])
            for d in self.include_dirs:
                if d not in inc_dirs:
                    inc_dirs.append(d)

        # 2. Workdir resolution
        configured_base = self.config.get("system.workdir_base", "void-builder/workdir")
        base_workdir = resolve_from_project(str(configured_base))
        workdir = self._resolve_writable_workdir(base_workdir)

        if self.clean:
            stale_paths = [
                workdir / "airootfs",
                workdir / "mnt",
                workdir / "iso-staging",
                workdir / "build_host",
            ]
            for stale_dir in stale_paths:
                if stale_dir.exists():
                    shutil.rmtree(stale_dir, ignore_errors=True)

        # 3. Setup toolchain
        self.toolchain = ToolchainManager(
            workdir_base=workdir,
            mode=self.mode,
            force_isolated=self.force_isolated_toolchain,
            arch=self.arch,
        )
        try:
            self.toolchain.setup()
        except Exception as e:
            raise BuildOrchestratorError(f"Failed to setup build toolchain: {e}")

        # 4. Setup ChrootManager
        chroot_path = workdir / "airootfs"
        self.chroot = ChrootManager(
            chroot_path=chroot_path,
            toolchain=self.toolchain,
            mode=self.mode,
            arch=self.arch,
            config=self.config,
        )
        
        # Inject chroot_manager into toolchain
        self.toolchain.chroot_manager = self.chroot

        # 5. Initialize ISOBuilder
        try:
            self.builder = ISOBuilder(
                arch=self.arch,
                config=self.config,
                toolchain=self.toolchain,
            )
            self.workdir = workdir
        except ISOBuilderError as e:
            raise BuildOrchestratorError(f"Failed to initialize the builder: {e}")

    def run_build(self, output_iso: str) -> Path:
        try:
            self._setup()

            print("\n[STEP 1/1] Running build pipeline through the engine...")
            output_path = Path(output_iso)
            result_iso = self.builder.build(output_path, str(self.workdir))

            print("\n✅ BUILD SUCCEEDED!")
            print(f"ISO generated at: {result_iso}")

            return result_iso

        except Exception as e:
            print(f"\n❌ CRITICAL BUILD ERROR: {e}")
            raise BuildOrchestratorError(f"Pipeline failed: {e}")

        finally:
            if self.chroot:
                self.chroot.umount()
