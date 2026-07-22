# Getting Started & System Preparation

Welcome to the comprehensive setup and getting started guide for **Void-Builder**. This document provides an exhaustive explanation of what Void-Builder is, its system requirements, host machine preparation across multiple Linux distributions, and step-by-step initial build walkthroughs.

---

## 1. What is Void-Builder?

**Void-Builder** is an enterprise-grade, modular Python framework designed to build custom Void Linux live ISO images, raw Single-Board Computer (SBC) disk images, and rootfs container archives.

### Why Void-Builder?
Traditional image generation scripts (such as original `void-mklive` bash scripts) are often tightly coupled to single architectures, hard to extend, and difficult to automate. Void-Builder addresses these limitations by providing:
- **Decoupled Architecture**: Separates configuration loading, toolchain isolation, chroot management, system customization, and output finalization.
- **Dynamic Configuration Composition**: Merges modular JSON profiles for desktops, kernels, bootloaders, packages, services, and platforms into unified build manifests.
- **Multi-Architecture & Cross-Building**: Supports 12 hardware architecture targets natively or via QEMU binfmt user-mode emulation.
- **Non-Root Simulation**: Features a `--mode mock` flag allowing developers to test and validate complex image configurations without root permissions.

---

## 2. System Requirements & Prerequisites

### Minimum Host Hardware Specifications
- **CPU**: x86_64 or aarch64 dual-core processor (quad-core recommended for fast compression).
- **RAM**: 4 GB minimum (8 GB recommended for real chroot package installations).
- **Disk Space**: 10 GB free space on a local Linux filesystem (EXT4, Btrfs, XFS). Avoid NTFS or FAT host mounts due to Linux file permission requirements.

### Supported Host Linux Distributions
- **Void Linux** (x86_64 / aarch64) - *Native Host Environment*
- **Debian / Ubuntu / Linux Mint**
- **Arch Linux / Manjaro**
- **Fedora / RHEL / AlmaLinux**
- **openSUSE Leap / Tumbleweed**

---

## 3. Host Dependencies & Toolchain Installation

Void-Builder requires specific host utilities depending on whether you are running in `--mode mock` or `--mode real`.

### Dependency Summary Table

| Utility | Package Name | Required For | Purpose |
| :--- | :--- | :--- | :--- |
| `python3` | `python3` | All modes | Core runtime engine. |
| `xbps-install.static` | Automatically managed | Real mode | Downloads and unpacks Void Linux XBPS packages into target rootfs. |
| `qemu-user-static` | `qemu-user-static` | Cross-architecture | Emulates foreign CPU architectures (e.g. building ARM on x86_64). |
| `binfmt-support` | `binfmt-support` | Cross-architecture | Registers QEMU emulators with the Linux kernel binfmt_misc system. |
| `xorriso` | `xorriso` | ISO Finalization | Assembles hybrid El Torito BIOS/UEFI bootable `.iso` files. |
| `squashfs-tools` | `squashfs-tools` | ISO Finalization | Compresses rootfs into SquashFS container image. |
| `dracut` | `dracut` | Initramfs | Builds custom initramfs images inside the target rootfs. |
| `dosfstools` | `dosfstools` | SBC Images | Creates VFAT boot partitions (`mkfs.vfat`). |
| `e2fsprogs` | `e2fsprogs` | SBC Images | Creates EXT4 root partitions (`mkfs.ext4`). |

---

## 4. Distribution-Specific Host Setup

### A. Void Linux Host
```bash
sudo xbps-install -S
sudo xbps-install -y python3 qemu-user qemu-user-aarch64 qemu-user-arm binfmt-support xorriso squashfs-tools dosfstools e2fsprogs
```

### B. Debian / Ubuntu Host
```bash
sudo apt-get update
sudo apt-get install -y python3 qemu-user-static binfmt-support xorriso squashfs-tools dosfstools e2fsprogs
```

### C. Arch Linux Host
```bash
sudo pacman -Syu --noconfirm python qemu-user-static binfmt-support xorriso squashfs-tools dosfstools e2fsprogs
```

### D. Fedora / RHEL Host
```bash
sudo dnf install -y python3 qemu-user-static binfmt-support xorriso squashfs-tools dosfstools e2fsprogs
```

---

## 5. Host Cross-Building Setup Script

When building for foreign architectures (such as building `aarch64` or `rpi-aarch64` on an `x86_64` host machine), you must run `setup_host_build_env.sh` once with root privileges.

```bash
sudo ./setup_host_build_env.sh
```

### What `setup_host_build_env.sh` Does Step-by-Step:
1. **Package Manager Detection**: Identifies host distro (`apt`, `pacman`, `dnf`, `zypper`, `xbps`).
2. **QEMU Emulator Installation**: Installs `qemu-user-static` emulators for `aarch64`, `armv7l`, `armv6l`, `ppc64le`, `riscv64`.
3. **Kernel Module Loading**: Executes `modprobe binfmt_misc` to load the kernel binfmt module.
4. **Filesystem Mounting**: Mounts `binfmt_misc` filesystem at `/proc/sys/fs/binfmt_misc`.
5. **Emulator Registration**: Registers QEMU user binaries so that executing foreign ELF binaries inside chroot works transparently.

---

## 6. First Walkthrough: Testing & Verification

### Step 1: Configuration Validation
Run `--check` to verify that all JSON configuration profiles and dynamic rules are intact:

```bash
python3 cli.py --check
```

Expected Output:
```text
🔍 Validating configuration for target architecture 'x86_64'...
2026-07-22 11:30:00 - ConfigLoader - INFO - Starting configuration assembly for x86_64...
2026-07-22 11:30:00 - ConfigLoader - INFO - Applied dynamic package rules from package_rules.json successfully.
2026-07-22 11:30:00 - ConfigLoader - INFO - Configuration assembly completed successfully.
✅ Configuration is VALID!
Summary:
  - Target Architecture: x86_64
  - Desktop Profile:     base
  - Total Packages:      136
  - Enabled Services:    dbus, NetworkManager, polkitd, bluetoothd, cupsd, avahi-daemon, sshd, chronyd, alsa, acpid, elogind, wpa_supplicant
```

### Step 2: First Mock Build (Simulation)
Simulate building an x86_64 ISO with XFCE desktop environment:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

This generates `void-builder-xfce-x86_64.iso` in mock mode without needing `sudo`.

### Step 3: First Real ISO Build
Build a real production ISO with XFCE:

```bash
sudo python3 cli.py x86_64 -d xfce --mode real
```
