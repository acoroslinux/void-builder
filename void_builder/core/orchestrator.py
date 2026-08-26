import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from void_builder.core.chroot_manager import ChrootManager
from void_builder.core.iso_engine import ISOBuilder, ISOBuilderError
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
        toolchain_retries: int = 3,
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
        update_toolchain: bool = False,
        compression: str = "xz",
        generate_manifest: bool = True,
        use_tarball: Optional[str] = None,
        create_tarball: bool = False,
        preset: Optional[str] = None,
        hostname: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        keymap: Optional[str] = None,
        root_password: Optional[str] = None,
        lock_root: bool = False,
        live_password: Optional[str] = None,
        boot_title: Optional[str] = None,
        iso_label: Optional[str] = None,
        boot_cmdline: Optional[str] = None,
        extra_kernel_args: Optional[str] = None,
        ssh_keys: Optional[List[str]] = None,
        hooks: Optional[Dict[str, Any]] = None,
        save_config_path: Optional[str] = None,
        use_tmpfs: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False,
        jobs: Optional[int] = None,
    ):
        VALID_ARCHS = (
            "x86_64", "x86_64-musl",
            "i686",
            "aarch64", "aarch64-musl",
            "armv7l", "armv7l-musl",
            "armv6l", "armv6l-musl",
            "riscv64", "riscv64-musl",
            "rpi-aarch64", "rpi-armv7l", "rpi-armv6l",
            "pinebookpro", "asahi", "x13s", "rockpro64", "pine64", "odroid-c4", "odroid-n2", "visionfive2",
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
        self.update_toolchain = update_toolchain
        self.fast_mode = fast_mode
        self.use_tmpfs = use_tmpfs
        self.benchmark = benchmark
        self.jobs = jobs
        self.compression = "zstd" if fast_mode else compression
        self.generate_manifest = generate_manifest
        self.use_tarball = use_tarball
        self.create_tarball = create_tarball
        self.preset = preset
        self.hostname = hostname
        self.timezone = timezone
        self.locale = locale
        self.keymap = keymap
        self.root_password = root_password
        self.lock_root = lock_root
        self.live_password = live_password
        self.boot_title = boot_title
        self.iso_label = iso_label
        self.boot_cmdline = boot_cmdline
        self.extra_kernel_args = extra_kernel_args
        self.ssh_keys = ssh_keys or []
        self.hooks = hooks or {}
        self.save_config_path = save_config_path
        self._tmpfs_mounted = False

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
                preset=self.preset,
                hostname=self.hostname,
                timezone=self.timezone,
                locale=self.locale,
                keymap=self.keymap,
                root_password=self.root_password,
                lock_root=self.lock_root,
                live_password=self.live_password,
                boot_title=self.boot_title,
                iso_label=self.iso_label,
                boot_cmdline=self.boot_cmdline,
                extra_kernel_args=self.extra_kernel_args,
                ssh_keys=self.ssh_keys,
                hooks=self.hooks,
            )
        except Exception as e:
            raise BuildOrchestratorError(f"Failed to load configuration: {e}")

        if not self.config:
            raise BuildOrchestratorError("The generated configuration is null or invalid.")

        # Save config snapshot if requested
        if self.save_config_path:
            save_p = resolve_from_project(self.save_config_path)
            save_p.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(save_p, "w", encoding="utf-8") as sf:
                json.dump(self.config.to_dict(), sf, indent=2)
            print(f"[ORCHESTRATOR] Saved assembled configuration to: {save_p}")

        # Apply compression, manifest, and tarball options to config
        self.config._data.setdefault("iso", {})["compression_type"] = self.compression
        self.config._data["generate_manifest"] = self.generate_manifest
        self.config._data["use_tarball"] = self.use_tarball
        self.config._data["create_tarball"] = self.create_tarball

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

        if self.fast_mode:
            self.config._data["fast_mode"] = True
            self.config._data["squashfs_compression"] = "zstd"
            self.config._data["zstd_level"] = "3"

        if self.compression:
            self.config._data["squashfs_compression"] = self.compression

        if self.jobs:
            self.config._data["jobs"] = self.jobs

        # 2. Workdir resolution
        configured_base = self.config.get("system.workdir_base", "workdir")
        base_workdir = resolve_from_project(str(configured_base))
        workdir = self._resolve_writable_workdir(base_workdir)

        if self.use_tmpfs:
            if self.mode == "real" and os.geteuid() == 0:
                # Compute safe tmpfs size based on available RAM + Swap (default 16G, up to 75% of total memory)
                tmpfs_size = "16G"
                try:
                    total_kb = 0
                    with open("/proc/meminfo", "r") as f:
                        for line in f:
                            if line.startswith("MemTotal:") or line.startswith("SwapTotal:"):
                                total_kb += int(line.split()[1])
                    total_gb = total_kb / (1024 * 1024)
                    safe_gb = max(4, min(16, int(total_gb * 0.75)))
                    tmpfs_size = f"{safe_gb}G"
                except Exception:
                    pass

                # Check if workdir is already a mountpoint from an interrupted previous run
                try:
                    resolved_workdir = str(workdir.resolve())
                    with open("/proc/mounts", "r") as f:
                        if any(len(line.split()) >= 2 and line.split()[1] == resolved_workdir for line in f):
                            import subprocess
                            subprocess.run(["umount", "-f", resolved_workdir], check=False)
                except Exception:
                    pass

                print(f"[ORCHESTRATOR] 🚀 Mounting tmpfs ({tmpfs_size} RAM disk) on {workdir}...")
                import subprocess
                subprocess.run(["mount", "-t", "tmpfs", "-o", f"size={tmpfs_size},mode=0755", "tmpfs", str(workdir)], check=True)
                self._tmpfs_mounted = True
            else:
                print(f"[ORCHESTRATOR] 🚀 [MOCK/SIM] Fast RAM staging enabled for {workdir}")

        if self.clean:
            stale_paths = [
                workdir / "airootfs",
                workdir / "mnt",
                workdir / "iso-staging",
                workdir / "build_host",
            ]
            from void_builder.utils.lib import umount_pseudofs
            for stale_dir in stale_paths:
                if stale_dir.exists():
                    umount_pseudofs(str(stale_dir))
                    shutil.rmtree(stale_dir, ignore_errors=True)

        self.toolchain = ToolchainManager(
            workdir_base=workdir,
            mode=self.mode,
            force_isolated=self.force_isolated_toolchain,
            arch=self.arch,
            update_toolchain=self.update_toolchain,
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

    def validate(self) -> Dict[str, Any]:
        """Validate configuration files and components without running the build."""
        from void_builder.core.config_loader import ConfigAssembler
        assembler = ConfigAssembler(str(Path(self.config_path).parent))
        return assembler.validate(
            target_arch=self.arch,
            target_desktop=self.desktop,
            target_kernel=self.kernel,
            target_bootloader=self.bootloader,
            package_profiles=self.package_profiles,
            service_profiles=self.service_profiles,
            preset=self.preset,
        )

    def run_build(self, output_iso: str, output_format: str = "iso") -> Union[str, Path]:
        try:
            self._setup()

            print(f"\n[STEP 1/1] Running build pipeline (format: {output_format})...")
            output_p = Path(output_iso)
            if not output_p.is_absolute() and not output_iso.startswith("output/"):
                output_path = resolve_from_project("output") / output_p
            else:
                output_path = resolve_from_project(output_iso)

            result_iso = self.builder.build(output_path, str(self.workdir), output_format=output_format)

            print("\n✅ BUILD SUCCEEDED!")
            print(f"Artifact generated at: {result_iso}")

            # Display benchmark report if requested
            if self.benchmark and hasattr(self.builder, "timings") and self.builder.timings:
                t = self.builder.timings
                print("\n" + "=" * 58)
                print(" ⏱️  BUILD BENCHMARK & EXECUTION TIMINGS REPORT")
                print("=" * 58)
                print(f"  ├── [1/5] Setup & Chroot:        {t.get('setup_chroot', 0):6.2f}s")
                print(f"  ├── [2/5] Package Installation:  {t.get('install_packages', 0):6.2f}s")
                print(f"  ├── [3/5] Customizations/Dracut: {t.get('post_install', 0):6.2f}s")
                print(f"  ├── [4/5] Bootloader Generation: {t.get('build_bootloaders', 0):6.2f}s")
                print(f"  ├── [5/5] Finalize & Compression:{t.get('finalize_artifact', 0):6.2f}s")
                print(f"  └── 🏁 TOTAL BUILD TIME:         {t.get('total', 0):6.2f}s")
                print("=" * 58 + "\n")

            return result_iso

        except Exception as e:
            print(f"\n❌ CRITICAL BUILD ERROR: {e}")
            raise BuildOrchestratorError(f"Pipeline failed: {e}")

        finally:
            if self.workdir:
                from void_builder.utils.lib import umount_pseudofs
                umount_pseudofs(str(self.workdir / "airootfs"))
                umount_pseudofs(str(self.workdir / "mnt"))

            if self.chroot:
                self.chroot.umount()

            if self.workdir:
                try:
                    import subprocess
                    resolved_workdir = str(self.workdir.resolve())
                    with open("/proc/mounts", "r") as f:
                        if any(len(line.split()) >= 2 and line.split()[1] == resolved_workdir for line in f):
                            subprocess.run(["umount", "-f", resolved_workdir], check=False)
                            self._tmpfs_mounted = False
                except Exception as e:
                    print(f"[ORCHESTRATOR] Warning: Could not unmount tmpfs: {e}")
            
            if self.workdir and self.workdir.exists():
                # Safety check: verify no active child mount points remain under self.workdir before running rmtree
                active_mount = False
                try:
                    resolved_workdir = self.workdir.resolve()
                    with open("/proc/mounts", "r") as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                mp = Path(parts[1]).resolve()
                                if mp != resolved_workdir and resolved_workdir in mp.parents:
                                    active_mount = True
                                    break
                except Exception:
                    pass

                if active_mount:
                    print(f"\n[ORCHESTRATOR] ⚠️ Safety Warning: Active mounts detected under {self.workdir}. Skipping rmtree to protect host system.")
                else:
                    print(f"\n[ORCHESTRATOR] Performing post-build cleanup: Removing {self.workdir}...")
                    import shutil
                    try:
                        shutil.rmtree(self.workdir, ignore_errors=True)
                        print("[ORCHESTRATOR] Cleanup complete. Workspace is pristine.")
                    except Exception as e:
                        print(f"[ORCHESTRATOR] Warning: Could not fully remove workdir: {e}")
