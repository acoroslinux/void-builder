# Python API Reference

This page documents the Python classes, interfaces, methods, and functions in `void_builder`.

---

## Module: `void_builder.core.config_loader`

### Class `Config(data)`
Data wrapper for configuration dictionaries with dot-notation access.

#### Methods
- `get(path: str, default: Any = None) -> Any`: Retrieves configuration value using dot notation (e.g., `system.iso_label`).
- `to_dict() -> Dict[str, Any]`: Returns raw dictionary underlying data.

---

### Class `ConfigAssembler(config_root)`
Composition brain that merges global manifests and component profiles.

#### Parameters
- `config_root` (`str` or `Path`): Directory containing configuration subfolders.

#### Methods
- `assemble(target_arch: str, target_desktop: Optional[str] = None, target_kernel: Optional[str] = None, target_bootloader: Optional[str] = None, package_profiles: Optional[List[str]] = None, service_profiles: Optional[List[str]] = None, target_live_profile: Optional[str] = None, live_user: Optional[str] = None, live_groups: Optional[List[str]] = None, platforms: Optional[List[str]] = None) -> Config`:
  Assembles and merges configuration profiles into a unified `Config` object.
- `validate(target_arch: str, target_desktop: Optional[str] = None, target_kernel: Optional[str] = None, target_bootloader: Optional[str] = None, package_profiles: Optional[List[str]] = None, service_profiles: Optional[List[str]] = None) -> Dict[str, Any]`:
  Validates component profile existence and returns structured audit report `{"valid": bool, "errors": list, "summary": dict}`.

---

## Module: `void_builder.core.orchestrator`

### Class `BuildOrchestrator(...)`
High-level build controller coordinating configuration assembly, toolchain setup, chroot creation, and image generation.

#### Methods
- `validate() -> Dict[str, Any]`: Runs configuration validation without executing build pipeline.
- `run_build(output_iso: str, output_format: str = "iso") -> Path`: Executes the complete build workflow and returns output file path.

---

## Module: `void_builder.core.iso_engine`

### Class `ISOEngine`
Abstract base class and registry for architecture build engines.

#### Registered Engines
- `@ISOEngine.register("x86_64")` / `@ISOEngine.register("i686")` / `@ISOEngine.register("aarch64")`: `VoidEngine`
- `@ISOEngine.register("rpi-aarch64")` / `@ISOEngine.register("pinebookpro")` / `@ISOEngine.register("asahi")`: `PlatformEngine`

---

### Class `BaseEngine(arch, config, toolchain)`
Abstract engine providing core utility functions.

#### Methods
- `setup_workdir(workdir: Optional[Union[str, Path]] = None) -> Path`: Resolves writable workspace directory.
- `_generate_manifest_and_checksums(output_file_path: str) -> None`: Calculates SHA256/MD5 hashes and writes `manifest.json`.
- `export_tarball(output_path: str) -> str`: Compresses rootfs into `.tar.xz` archive.

---

### Class `VoidEngine`
Engine handling standard PC ISO 9660 hybrid image creation.

#### Methods
- `setup_chroot(workdir: str) -> None`: Prepares `airootfs` and `iso-staging` directories.
- `install_packages() -> None`: Invokes `ChrootManager` to install target packages.
- `post_install_configure() -> None`: Applies locale, user, service, and Plymouth customizations.
- `build_bootloaders(mountpoint: str) -> None`: Assembles SYSLINUX and GRUB EFI boot files.
- `finalize_isofile(output_path: str) -> None`: Runs `mksquashfs` and `xorriso` to create final `.iso`.

---

### Class `PlatformEngine`
Engine handling SBC raw disk image generation.

#### Methods
- `finalize_isofile(output_path: str) -> None`: Calculates required rootfs size, formats disk image with `sfdisk`, mounts loop device, copies rootfs, and writes U-Boot/GRUB EFI binaries.

---

## Module: `void_builder.core.chroot_manager`

### Class `ChrootManager(chroot_path, toolchain, mode, arch, config)`
Manages virtual filesystem mounting (`/proc`, `/sys`, `/dev`), `xbps-install` commands, and user/service setup inside target chroot.

#### Methods
- `mount() -> None`: Mounts pseudo-filesystems.
- `umount() -> None`: Safely unmounts pseudo-filesystems.
- `install_packages(package_plan: Dict[str, List[str]], repos: Optional[List[str]] = None) -> None`: Executes `xbps-install` for package set.
- `run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess`: Runs command inside chroot environment.
- `run_reconfigure() -> None`: Executes Void 3-pass `xbps-reconfigure -a`.

---

## Module: `void_builder.core.customizer`

### Class `SystemConfigurator(chroot_manager)`
Applies low-level Linux system customizations inside target rootfs.

#### Methods
- `load_from_config(config: Config) -> None`: Loads hostname, locale, timezone, users, services, Plymouth, and Dracut configurations.
- `apply() -> None`: Executes customization steps sequentially.
