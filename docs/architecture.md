# Architecture & System Design

This document details the internal module design, class hierarchy, and build flow of **Void-Builder**.

---

## Architectural Overview

Void-Builder is designed around a modular pipeline architecture split into core components:

```
                      +-------------------+
                      |   cli.py (CLI)    |
                      +---------+---------+
                                |
                                v
                   +-------------------------+
                   |    BuildOrchestrator    |
                   +------------+------------+
                                |
             +------------------+------------------+
             |                                     |
             v                                     v
  +--------------------+                 +--------------------+
  |  ConfigAssembler   |                 |  ToolchainManager  |
  +---------+----------+                 +---------+----------+
            |                                      |
            +------------------+-------------------+
                               |
                               v
                     +-------------------+
                     |   ChrootManager   |
                     +---------+---------+
                               |
                               v
                      +------------------+
                      |   ISOBuilder     |
                      +--------+---------+
                               |
            +------------------+------------------+
            |                                     |
            v                                     v
  +------------------+                  +-------------------+
  |    VoidEngine    |                  |  PlatformEngine   |
  | (x86_64, i686)   |                  | (RPi, Pine, Asahi)|
  +------------------+                  +-------------------+
```

---

## Core Modules

### 1. `void_builder.core.config_loader`
- **`Config`**: Dot-notation wrapper class for dictionary configuration data.
- **`ConfigAssembler`**: The composition engine. Reads `configs/global_build.json` and deep-merges profile JSON files for architecture, desktop, kernel, bootloader, packages, services, and platforms. Also handles `validate()` verification.

### 2. `void_builder.core.toolchain`
- **`ToolchainManager`**: Manages static `xbps-install.static` binaries, architecture toolchain isolation, and package downloading.

### 3. `void_builder.core.chroot_manager`
- **`ChrootManager`**: Manages virtual filesystems (`/proc`, `/sys`, `/dev`, `/dev/pts`, `/dev/shm`), package installation commands, user account creation, service symlinking, and rootfs cleanup.

### 4. `void_builder.core.iso_engine`
- **`ISOEngine`**: Abstract base class and registry decorator (`@ISOEngine.register`).
- **`VoidEngine`**: Standard ISO engine for PC architectures (`x86_64`, `i686`, `aarch64` ISOs). Handles `mksquashfs`, ISOLINUX/GRUB setup, `xorriso` ISO generation, and checksum/manifest writing.
- **`PlatformEngine`**: SBC engine for single-board computers (`rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l`, `pinebookpro`, `asahi`). Handles loop device partitioning (`sfdisk`), VFAT/EXT4 formatting, U-Boot / GRUB EFI installation, and image compression (`xz`).

### 5. `void_builder.core.customizer`
- **`SystemConfigurator`**: Applies hostname, locale, timezone, user passwords/groups, runit services (`/etc/runit/runsvdir/default`), Plymouth themes, Flatpak remotes, and Dracut initramfs generation inside the target rootfs.

---

## Pipeline Execution Steps

1. **Config Assembly**: Merge `global_build.json` + `architectures/<arch>.json` + `desktops/<desktop>.json` + dynamic package rules.
2. **Toolchain Setup**: Prepare static `xbps` binaries in `void_builder/tools`.
3. **Chroot Initialization**: Create `airootfs` directory and mount pseudo-filesystems.
4. **Package Installation**: Run `xbps-install` to install target package set into `airootfs`.
5. **System Customization**: Configure locale, users, services, Plymouth, and generate initramfs with Dracut.
6. **3-Pass Reconfiguration**: Execute `xbps-reconfigure -a` inside chroot.
7. **Bootloader Setup**: Copy kernel/initrd, generate `isolinux.cfg` and `grub.cfg`, build `efiboot.img`.
8. **Finalization**: Compress rootfs with SquashFS (`xz`/`zstd`) and assemble hybrid ISO with `xorriso` (or format `.img` partition scheme for SBCs).
9. **Manifest & Checksums**: Calculate SHA256/MD5 hashes and write `manifest.json`.
