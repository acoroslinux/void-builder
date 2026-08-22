# Comprehensive Usage Manual & Examples

This manual provides an in-depth operational guide for **Void-Builder**, detailing all command-line options, architecture targets, output formats, compression choices, and 10 complete end-to-end execution examples.

---

## 1. Supported Architecture Targets Matrix

Void-Builder natively supports 12 target architectures and single-board computer platform profiles.

| Target Name | Architecture Family | C Standard Library | Target Hardware | Default Engine |
| :--- | :--- | :--- | :--- | :--- |
| `x86_64` | x86 64-bit | glibc | Standard Intel/AMD 64-bit PCs & Laptops | `VoidEngine` |
| `x86_64-musl` | x86 64-bit | musl | Lightweight 64-bit PCs & Servers | `VoidEngine` |
| `i686` | x86 32-bit | glibc | Legacy 32-bit Intel/AMD PCs | `VoidEngine` |
| `aarch64` | ARM64 64-bit | glibc | Generic ARM64 Servers & Workstations | `VoidEngine` |
| `aarch64-musl` | ARM64 64-bit | musl | Lightweight ARM64 Containers & SBCs | `VoidEngine` |
| `armv7l` | ARMv7 32-bit | glibc | Generic 32-bit ARMv7 Hard-Float SBCs | `VoidEngine` |
| `armv7l-musl` | ARMv7 32-bit | musl | Lightweight 32-bit ARMv7 Devices | `VoidEngine` |
| `rpi-aarch64` | ARM64 64-bit | glibc | Raspberry Pi 3, 4, 400, 5, Zero 2 W | `PlatformEngine` |
| `rpi-armv7l` | ARMv7 32-bit | glibc | Raspberry Pi 2, 3 (32-bit mode) | `PlatformEngine` |
| `rpi-armv6l` | ARMv6 32-bit | glibc | Raspberry Pi 1, Zero (32-bit ARMv6) | `PlatformEngine` |
| `pinebookpro` | ARM64 64-bit | glibc | Pine64 Pinebook Pro (Rockchip RK3399) | `PlatformEngine` |
| `asahi` | ARM64 64-bit | glibc | Apple Silicon Macs (M1, M1 Pro/Max, M2) | `PlatformEngine` |

---

## 2. Output Formats Explained

Void-Builder supports three primary output format types specified via `--format`:

### A. Bootable ISO Image (`--format iso`)
- **Extension**: `.iso`
- **Use Case**: Bootable Live USB flash drives, DVDs, virtual machines (QEMU, KVM, VirtualBox, VMware).
- **Structure**: Hybrid ISO 9660 filesystem containing a SquashFS container image (`LiveOS/squashfs.img`), El Torito BIOS MBR boot code (SYSLINUX), and UEFI FAT boot image (`boot/grub/efiboot.img`).

### B. Raw Platform Disk Image (`--format img`)
- **Extension**: `.img` (or `.img.xz` compressed)
- **Use Case**: Single-Board Computers (Raspberry Pi, Pinebook Pro, Asahi). Designed to be flashed directly to SD cards, eMMC drives, or NVMe storage using `dd`, Raspberry Pi Imager, or BalenaEtcher.
- **Structure**: Partitioned disk image (Partition 1: VFAT `/boot` partition; Partition 2: EXT4 root `/` partition).

### C. RootFS Container Tarball (`--format tarball`)
- **Extension**: `.tar.xz`
- **Use Case**: Docker container base images, Podman containers, LXC/Proxmox templates, systemd-nspawn containers, chroot bootstrap environments.
- **Structure**: Compressed tar archive containing the exact customized root directory structure (`/bin`, `/etc`, `/usr`, `/var`).

---

## 3. Stage Seed Tarball System (Gentoo-Style Rapid ISO Builds)

Void-Builder incorporates a Stage Seed Tarball mechanism inspired by Gentoo Linux's Stage3 seed architecture:

1. **`--use-tarball [SOURCE]`**:
   - Unpacks a pre-built base rootfs tarball (`void-base-<arch>.tar.xz`) directly into the target chroot.
   - Automatically runs `xbps-install -Syu` inside the chroot to bring base packages up to the latest Void Linux repository release.
   - Layers requested desktop environments and additional package profiles in seconds, bypassing redundant base downloads.
   - **Supported Sources**:
     - `--use-tarball y` / `--use-tarball auto`: Automatically looks for cached stage seeds in `output/stage_seeds/` or `workdir/cache/tarballs/`.
     - Local file: `/path/to/stage.tar.xz` or `file:///...`
     - Remote URL: `https://...` (downloads and caches the tarball automatically).

2. **`--create-tarball`**:
   - Saves the bootstrapped base rootfs as a reusable stage seed in `output/stage_seeds/void-base-<arch>.tar.xz` and `workdir/cache/tarballs/void-base-<arch>.tar.xz` alongside its SHA256 and MD5 checksums.

---

## 4. Compression Algorithms Compared

Select the compression algorithm via `--compression`:

| Algorithm | Compression Ratio | Decompression Speed | CPU Usage | Best For |
| :--- | :--- | :--- | :--- | :--- |
| `xz` (default) | Very High (Smallest file size) | Moderate | High | Distribution ISOs, internet downloads |
| `zstd` | High (Very close to XZ) | **Ultra Fast (3-5x faster boot)** | Low | High-performance desktop ISOs, fast boots |
| `gzip` | Moderate | Fast | Low | Compatibility with legacy systems |

---

## 4. Complete Usage Examples

### Example 1: Standard Non-Root Simulation (Mock Build)
Simulate an x86_64 ISO build with XFCE desktop environment without root privileges:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

Expected Output Files in `output/`:
- `void-builder-xfce-x86_64.iso`
- `void-builder-xfce-x86_64.iso.sha256`
- `void-builder-xfce-x86_64.iso.sha512`
- `void-builder-xfce-x86_64.iso.md5`
- `void-builder-xfce-x86_64.iso.manifest.json`

---

### Example 2: Ultra-Fast RAM Build with Benchmark Timings
Build a live ISO entirely inside RAM (`tmpfs`) with `zstd` level 3 compression and per-stage timing breakdown:

```bash
sudo python3 cli.py x86_64 --preset desktop-xfce --fast --tmpfs --benchmark --mode real
```

---

### Example 3: Specialized Flavour Build (Rescue & SysAdmin Edition)
Build an all-in-one system rescue, forensics, and partition recovery ISO:

```bash
sudo python3 cli.py x86_64 --preset rescue-sysadmin --mode real
```

---

### Example 4: Full Localization & System Configuration
Build an ISO customized with Portuguese localization, custom hostname, and root credentials:

```bash
sudo python3 cli.py x86_64 -P desktop-xfce \
    --hostname void-portugal \
    --locale pt_PT.UTF-8 \
    --timezone Europe/Lisbon \
    --keymap pt-latin1 \
    --root-password "SecretPass123" \
    --mode real
```

---

### Example 5: Developer Workstation with SSH Key Ingestion
Build a developer environment with Rust, Go, Python, Podman, and inject your host SSH public key:

```bash
sudo python3 cli.py x86_64 --preset developer \
    --ssh-key ~/.ssh/id_ed25519.pub \
    --mode real
```

---

### Example 6: Gaming Edition with Steam & Multilib
Build a gaming-ready ISO with Steam, Vulkan drivers, Wine, and automated multilib/nonfree repo configuration:

```bash
sudo python3 cli.py x86_64 --preset gaming --mode real
```

---

### Example 7: Raspberry Pi 4 64-Bit Disk Image
Generate a bootable SD Card image for Raspberry Pi 4/5:

```bash
# Setup host cross-emulation once
sudo ./setup_host_build_env.sh

# Build Raspberry Pi 64-bit disk image
sudo python3 cli.py rpi-aarch64 --mode real
```

---

### Example 8: Lifecycle Hooks Execution
Execute customized shell scripts during build phases:

```bash
sudo python3 cli.py x86_64 -P minimal \
    --hook post-install:configs/hooks/post-install.example.sh \
    --mode real
```

---

### Example 9: Container RootFS Export
Export a customized Void Linux rootfs tarball for LXC, Docker, or Podman:

```bash
sudo python3 cli.py x86_64 -P minimal --format tarball --mode real
```

---

### Example 10: Calamares Graphical Installer Live ISO
Compile the Calamares graphical installer and inject it into an XFCE live ISO:

```bash
sudo python3 cli.py x86_64 -d xfce --with-calamares --mode real
```

