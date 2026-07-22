# Usage & Examples

This document provides a comprehensive command-line reference and practical usage examples for **Void-Builder**.

---

## Command Line Interface Reference

```bash
python3 cli.py [ARCHITECTURE] [OPTIONS]
```

### Primary Arguments

| Argument | Default | Description |
| :--- | :--- | :--- |
| `ARCHITECTURE` | `x86_64` | Target architecture: `x86_64`, `x86_64-musl`, `i686`, `aarch64`, `aarch64-musl`, `armv7l`, `armv7l-musl`, `rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l`, `pinebookpro`, `asahi`. |

### Execution & Output Options

| Flag | Choices | Default | Description |
| :--- | :--- | :--- | :--- |
| `--mode` | `mock`, `real` | `mock` | Execution mode: `mock` (simulation, no root required) or `real` (actual build). |
| `--format` | `iso`, `img`, `tarball` | `iso` | Target build format: `.iso` (bootable ISO), `.img` (disk image), or `.tar.xz` (rootfs tarball). |
| `--compression` | `xz`, `zstd`, `gzip` | `xz` | Compression algorithm for SquashFS and Initramfs. |
| `--check` / `--validate` | - | - | Validate configurations, profiles, and package dependencies without building. |
| `--generate-manifest` | - | `True` | Automatically generate `.sha256`, `.md5`, and `.manifest.json`. |
| `--no-manifest` | - | - | Disable checksum and manifest generation. |
| `-o`, `--output` | string | auto | Custom output filename. |
| `--clean` / `--no-clean` | - | `--clean` | Pre-build workdir cleanup control. |

### Customization Overrides

| Flag | Example | Description |
| :--- | :--- | :--- |
| `-d`, `--desktop` | `-d xfce` | Desktop environment profile from `configs/desktops`. |
| `-k`, `--kernel` | `-k linux-lts` | Kernel selection (profile or package name). |
| `-b`, `--bootloader` | `-b grub` | Bootloader profile from `configs/bootloaders`. |
| `-p`, `--package-profile` | `-p dev-tools` | Additional package profile from `configs/packages`. |
| `-s`, `--service-profile` | `-s ssh` | Additional service profile from `configs/services`. |
| `--live-user` | `--live-user void` | Custom username for live ISO environment. |
| `--live-groups` | `--live-groups wheel,audio` | Custom groups for live user. |
| `-R`, `--repository` | `-R https://...` | Custom XBPS repository URL. |

---

## Practical Examples

### 1. Fast Mock Build (x86_64 with XFCE)

Simulate building an x86_64 ISO with XFCE desktop environment:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

### 2. Real Production ISO Build (x86_64 with GNOME)

Create an official bootable ISO for x86_64 running GNOME:

```bash
sudo python3 cli.py x86_64 -d gnome --mode real
```

### 3. Raspberry Pi 4 Disk Image (`rpi-aarch64`)

Generate a bootable SD Card raw image (`.img`) for Raspberry Pi 4:

```bash
# Prepare host environment once
sudo ./setup_host_build_env.sh

# Build platform image
sudo python3 cli.py rpi-aarch64 --mode real
```

Output files:
- `void-builder-base-rpi-aarch64.img.xz`
- `void-builder-base-rpi-aarch64.img.xz.sha256`
- `void-builder-base-rpi-aarch64.img.xz.md5`
- `void-builder-base-rpi-aarch64.img.xz.manifest.json`

### 4. Container / LXC RootFS Tarball Export

Create a `.tar.xz` tarball of the custom system rootfs:

```bash
sudo python3 cli.py x86_64 -d base --mode real --format tarball
```

Output file:
- `void-builder-base-x86_64.tar.xz`

### 5. High-Speed ZSTD Compression Build

Build an ISO using `zstd` compression for ultra-fast boot performance:

```bash
sudo python3 cli.py x86_64 -d kde --mode real --compression zstd
```

### 6. Calamares Installer Build Pipeline

Build the Calamares installer package locally and inject it into the ISO:

```bash
sudo python3 cli.py x86_64 -d xfce --with-calamares --mode real
```
