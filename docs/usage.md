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

## 3. Compression Algorithms Compared

Select the compression algorithm via `--compression`:

| Algorithm | Compression Ratio | Decompression Speed | CPU Usage | Best For |
| :--- | :--- | :--- | :--- | :--- |
| `xz` (default) | Very High (Smallest file size) | Moderate | High | Distribution ISOs, internet downloads |
| `zstd` | High (Very close to XZ) | **Ultra Fast (3-5x faster boot)** | Low | High-performance desktop ISOs, fast boots |
| `gzip` | Moderate | Fast | Low | Compatibility with legacy systems |

---

## 4. 10 Complete Usage Examples

### Example 1: Standard Non-Root Simulation (Mock Build)
Simulate an x86_64 ISO build with XFCE desktop environment without root privileges:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

Expected Output Files:
- `void-builder-xfce-x86_64.iso`
- `void-builder-xfce-x86_64.iso.sha256`
- `void-builder-xfce-x86_64.iso.md5`
- `void-builder-xfce-x86_64.iso.manifest.json`

---

### Example 2: Production Real ISO Build (GNOME Desktop)
Build a real production ISO containing the GNOME desktop environment for 64-bit PCs:

```bash
sudo python3 cli.py x86_64 -d gnome --mode real
```

---

### Example 3: Ultra-Fast Boot ISO with ZSTD Compression
Build a KDE Plasma desktop ISO compressed with `zstd` for maximum boot speed:

```bash
sudo python3 cli.py x86_64 -d kde --mode real --compression zstd
```

---

### Example 4: Raspberry Pi 4 64-Bit Disk Image
Generate a bootable SD Card image for Raspberry Pi 4:

```bash
# Setup host cross-emulation once
sudo ./setup_host_build_env.sh

# Build Raspberry Pi 64-bit disk image
sudo python3 cli.py rpi-aarch64 --mode real
```

Generated Artifact:
- `void-builder-base-rpi-aarch64.img.xz`

---

### Example 5: Container Base Tarball Export
Export a customized Void Linux rootfs tarball for LXC, Docker, or Podman:

```bash
sudo python3 cli.py x86_64 -d base --mode real --format tarball
```

Generated Artifact:
- `void-builder-base-x86_64.tar.xz`

---

### Example 6: Pinebook Pro Laptop Image
Build a raw disk image for the Pine64 Pinebook Pro laptop featuring Rockchip RK3399 U-Boot loader:

```bash
sudo python3 cli.py pinebookpro -d sway --mode real
```

---

### Example 7: Apple Silicon Mac Image (Asahi Linux)
Build an Apple Silicon ARM64 disk image formatted with Asahi Linux kernel and GRUB EFI:

```bash
sudo python3 cli.py asahi -d gnome --mode real
```

---

### Example 8: Lightweight Musl C Library ISO
Build an `x86_64-musl` lightweight ISO for server deployments:

```bash
sudo python3 cli.py x86_64-musl -d base -s ssh --mode real
```

---

### Example 9: Offline Graphical Installer ISO with Calamares
Compile the Calamares graphical installer from source templates and inject it into an XFCE live ISO:

```bash
sudo python3 cli.py x86_64 -d xfce --with-calamares --mode real
```

---

### Example 10: Custom Repository & Included Directory Overlay
Build an ISO with custom XBPS packages from an external repository and overlay local configuration files:

```bash
sudo python3 cli.py x86_64 -d awesome \
  -R https://my-custom-repo.org/voidlinux \
  -I /home/user/custom_skel:/etc/skel \
  -p dev-tools \
  --mode real
```
