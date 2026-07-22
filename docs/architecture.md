# Architectural Blueprint & Engine Design

This document provides a deep architectural analysis of **Void-Builder**, detailing component responsibilities, class hierarchies, data flows, sequence diagrams, and pipeline execution stages.

---

## 1. Architectural Principles

Void-Builder is built around four core design principles:

1. **Separation of Concerns**: Configuration parsing (`config_loader`), host tools (`toolchain`), environment execution (`chroot_manager`), image generation (`iso_engine`), and rootfs configuration (`customizer`) are decoupled into specialized modules.
2. **Abstract Engine Registry**: Architecture engines (`VoidEngine`, `PlatformEngine`) register via `@ISOEngine.register("name")` decorators, allowing new hardware platforms to be added without modifying existing code.
3. **Dual Execution Modes**: High-speed `--mode mock` non-root simulation alongside production `--mode real` root operations.
4. **Resilient Workdir Fallbacks**: Automated permission testing for workspace directories, falling back to `/tmp/void-builder-fallback` and `/tmp/void-builder-cache` if project root permissions are restricted.

---

## 2. Complete Execution Sequence Diagram

```text
User / Terminal
      |
      | 1. Execute cli.py [arch] [options]
      v
  cli.py
      |
      | 2. Instantiate BuildOrchestrator
      v
BuildOrchestrator
      |
      | 3. ConfigAssembler.assemble()
      v
ConfigAssembler  ===> Reads global_build.json + architectures/ + desktops/ + package_rules.json
      |
      | 4. Return Config object
      v
BuildOrchestrator
      |
      | 5. ToolchainManager.setup() -> Ensure static xbps binaries
      | 6. ChrootManager(chroot_path)
      | 7. ISOBuilder(arch, config, toolchain)
      v
  ISOBuilder
      |
      | 8. Select engine: VoidEngine or PlatformEngine
      v
Target Engine (VoidEngine / PlatformEngine)
      |
      +---> 1. setup_workdir()
      |
      +---> 2. setup_chroot()
      |
      +---> 3. install_packages() -> ChrootManager.install_packages()
      |
      +---> 4. post_install_configure() -> SystemConfigurator.apply()
      |
      +---> 5. build_bootloaders() -> SYSLINUX / GRUB / U-Boot
      |
      +---> 6. finalize_isofile() / export_tarball() -> mksquashfs / xorriso / sfdisk / tar
      |
      +---> 7. _generate_manifest_and_checksums() -> .sha256, .md5, .manifest.json
      v
Output Artifacts (.iso / .img / .tar.xz + Manifests)
```

---

## 3. Class Hierarchy & Responsibilities

### Module: `void_builder.core.config_loader`

#### `Config`
- **Role**: Read-only configuration wrapper providing dot-notation access (`cfg.get("system.iso_label")`).

#### `ConfigAssembler`
- **Role**: Recursive dictionary merger.
- **Methods**:
  - `_deep_merge(base, update)`: Combines nested dicts and appends list items uniquely.
  - `assemble(...)`: Merges global build settings, architecture config, desktop profile, kernel override, package profiles, service profiles, and dynamic package rules.
  - `validate(...)`: Validates that all requested profile files exist in `configs/` and produces a structured audit dictionary.

#### `ConfigLoader`
- **Role**: Backward-compatible loader helper.

---

### Module: `void_builder.core.toolchain`

#### `ToolchainManager`
- **Role**: Downloads and validates static `xbps-install.static` and `xbps-rindex.static` binaries.
- **Methods**:
  - `setup()`: Verifies host static tools or downloads pre-compiled static binaries into `void_builder/tools`.
  - `_run_xbps_install(...)`: Executes static `xbps-install.static` against the target rootfs.

---

### Module: `void_builder.core.chroot_manager`

#### `ChrootManager`
- **Role**: Handles pseudo-filesystem mounts (`/proc`, `/sys`, `/dev`, `/dev/pts`, `/dev/shm`), package installations, user creation, and chroot command execution.
- **Methods**:
  - `mount()`: Mounts virtual filesystems into target rootfs.
  - `umount()`: Safely unmounts all virtual filesystems.
  - `install_packages(package_plan, repos)`: Installs packages into chroot via XBPS.
  - `run_command(cmd, check)`: Executes shell command inside chroot using `chroot` or `proot`.
  - `run_reconfigure()`: Runs Void 3-pass `xbps-reconfigure -f <pkg>` for system packages.

---

### Module: `void_builder.core.iso_engine`

#### `ISOEngine`
- **Role**: Metaclass and engine registry.
- **Registry**: Maps architecture names to engine implementation classes.

#### `BaseEngine`
- **Role**: Abstract base engine providing workspace resolution, manifest generation, and tarball export.
- **Methods**:
  - `setup_workdir(workdir)`: Resolves and creates workspace paths.
  - `_generate_manifest_and_checksums(output_path)`: Computes SHA256/MD5 hashes and generates `manifest.json`.
  - `export_tarball(output_path)`: Packs rootfs into `.tar.xz` container tarball.

#### `VoidEngine(BaseEngine)`
- **Role**: Handles PC ISO 9660 hybrid ISO image building (`x86_64`, `i686`, `aarch64`).
- **Methods**:
  - `_create_squashfs()`: Invokes `mksquashfs` with configured compression (`xz`, `zstd`, `gzip`).
  - `finalize_isofile(output_path)`: Assembles ISO using `xorriso` with BIOS El Torito and UEFI GRUB EFI options.

#### `PlatformEngine(VoidEngine)`
- **Role**: Handles Single-Board Computer raw disk images (`rpi-aarch64`, `pinebookpro`, `asahi`).
- **Methods**:
  - `finalize_isofile(output_path)`: Dynamically calculates required image size, runs `sfdisk` partitioning, sets up loop device via `losetup`, formats VFAT/EXT4 partitions, copies rootfs, writes U-Boot / GRUB EFI bootloaders, and compresses raw `.img` with `xz`.

---

### Module: `void_builder.core.customizer`

#### `SystemConfigurator`
- **Role**: Performs low-level system configuration inside target rootfs.
- **Methods**:
  - `load_from_config(config)`: Reads hostname, locale, timezone, user accounts, runit services, Plymouth theme, and Dracut options.
  - `apply()`: Executes individual configurator actions sequentially (`apply_locale`, `apply_users`, `apply_services`, `apply_dracut`, `apply_plymouth`).

---

## 4. Step-by-Step Pipeline Phases

1. **Phase 1 - Initialization**: `BuildOrchestrator` parses arguments, instantiates `ConfigAssembler`, and builds master `Config` object.
2. **Phase 2 - Workdir Resolution**: Tests write permissions on `workdir/<arch>`, falling back to `/tmp/void-builder-fallback/<arch>` if write permission is denied.
3. **Phase 3 - Toolchain Preparation**: Initializes `ToolchainManager` and verifies static `xbps` binaries.
4. **Phase 4 - Chroot Provisioning**: Creates `airootfs` directory and mounts virtual filesystems (`/proc`, `/sys`, `/dev`, `/dev/pts`, `/dev/shm`).
5. **Phase 5 - Package Installation**: Invokes `xbps-install.static` with target package plan and repository list.
6. **Phase 6 - System Customization**: `SystemConfigurator` configures `/etc/hostname`, `/etc/locale.conf`, `/etc/rc.conf`, creates user accounts, symlinks Runit services into `/etc/runit/runsvdir/default/`, and runs Dracut initramfs generator.
7. **Phase 7 - 3-Pass Reconfiguration**: Runs `xbps-reconfigure -a` inside chroot.
8. **Phase 8 - Bootloaders & Finalization**:
   - For ISO: Generates SYSLINUX/GRUB configs, creates SquashFS, runs `xorriso`.
   - For SBC: Partition image with `sfdisk`, format VFAT/EXT4, write U-Boot, compress image with `xz`.
   - For Tarball: Packs rootfs into `.tar.xz`.
9. **Phase 9 - Checksums & Manifest**: Calculates SHA256 and MD5 hashes, writes `manifest.json`, unmounts virtual filesystems, and cleans temporary files.
