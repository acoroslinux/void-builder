# Void-Builder

> **Modular, Dynamic, and Multi-Architecture Void Linux ISO & Disk Image Building Toolkit**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Online Documentation](https://img.shields.io/badge/docs-online--sphinx-red.svg)](https://acoroslinux.github.io/void-builder/)

---

## 📖 Online Documentation

The complete, interactive HTML documentation for Void-Builder is hosted online:

👉 **[https://acoroslinux.github.io/void-builder/](https://acoroslinux.github.io/void-builder/)**

The online manual covers:
- [Getting Started & System Requirements](https://acoroslinux.github.io/void-builder/getting_started.html)
- [CLI Reference & End-to-End Examples](https://acoroslinux.github.io/void-builder/usage.html)
- [Complete JSON Configuration Schemas](https://acoroslinux.github.io/void-builder/configuration.html)
- [Stage Seed Tarball System (Gentoo-Style)](https://acoroslinux.github.io/void-builder/usage.html#stage-seeds)
- [System Architecture & Build Pipeline](https://acoroslinux.github.io/void-builder/architecture.html)
- [Bootloaders (BIOS, UEFI, Raspberry Pi, Pinebook Pro, Asahi)](https://acoroslinux.github.io/void-builder/bootloaders.html)
- [Python API Reference](https://acoroslinux.github.io/void-builder/api_reference.html)
- [Troubleshooting & FAQ](https://acoroslinux.github.io/void-builder/troubleshooting.html)

---

## Overview

**Void-Builder** is an advanced python-based ISO and disk image orchestrator for **Void Linux**. It provides a flexible composition engine to build custom live ISO images, raw single-board computer disk images, and rootfs container tarballs across 12 distinct hardware architectures and platforms.

---

## Key Features

- 🌐 **12 Supported Architectures & Platforms**:
  - **PC / Generic**: `x86_64`, `x86_64-musl`, `i686`, `aarch64`, `aarch64-musl`, `armv7l`, `armv7l-musl`
  - **SBCs & Arm Platforms**: `rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l`, `pinebookpro`, `asahi`
- 🎯 **Unified Presets & Flavours System**:
  - Build specialized editions with a single command using `-P` / `--preset`: `minimal`, `desktop-xfce`, `desktop-kde`, `desktop-gnome`, `rescue-sysadmin`, `developer`, and `gaming`.
- ⚡ **Stage Seed Tarball System (Gentoo-Style Rapid Builds)**:
  - `--use-tarball`: Unpacks a pre-built base system stage seed (`.tar.xz`), runs `xbps-install -Syu` to update base packages, and layers requested desktop/delta packages in seconds!
  - `--create-tarball`: Generates reusable base system stage seeds and stores them in `output/stage_seeds/` and `cache/tarballs/`.
  - Flexible Sources: Accepts local files (`file:///...`), HTTP/HTTPS URLs (`https://...`), or automatic local cache lookup (`--use-tarball y`).
- 🛡️ **Total Build Isolation & Auto-Recovery**: Zero host package manager dependencies! Downloads static `xbps-install.static` from official Void mirrors (`repo-default.voidlinux.org`) and uses native `chroot` or `proot`.
- 🔑 **Security & SSH Injection**: Direct flags for `--root-password`, `--lock-root`, `--live-password`, and `--ssh-key` / `--ssh-pubkey` injection.
- 🪝 **Lifecycle Hooks Engine**: Execute custom scripts at distinct lifecycle points (`pre-install`, `post-install`, `pre-iso`, `post-iso`) with `--hook`.
- 🛠️ **Multiple Output Formats & Checksums**:
  - `.iso`: Hybrid bootable ISO images (BIOS + UEFI)
  - `.img`: Partitioned raw disk images for SD cards / eMMC
  - `.tar.xz`: Compressed RootFS container tarballs
  - Comprehensive checksums: `.sha256`, `.sha512`, `.md5`, and `.manifest.json`.
- 🚀 **Interactive Terminal Wizard**: Launch step-by-step interactive configuration with `-i` / `--interactive`.
- 📦 **Clean Package Profiles & Automatic Defaults**:
  - All 16 package profiles use a clean schema: `"packages"`, `"optional_packages"`, and `"_comment"`.
  - Automatic non-free and multilib repository enablement when non-free/multilib packages (`void-repo-nonfree`, `steam`, `nvidia`, etc.) are requested.
  - Automatic service conflict resolution (e.g. omits standalone `dhcpcd` when `NetworkManager` is enabled).
- ⚡ **Turbo Speed Optimizations**:
  - `--fast` / `--quick`: Ultra-fast build pipeline with multi-threaded `zstd` compression level 3, fast block sizes, and optimized staging.
  - `--tmpfs`: Build entirely inside RAM (`tmpfs`) to maximize I/O throughput (3x-5x faster) and prevent SSD wear.
  - `--benchmark`: Measures and displays per-stage execution timings (Setup, Packages, Dracut, Bootloader, SquashFS, Finalization).
  - Multi-threaded parallel extraction and compression (`zstd -T0`, `pixz`, `pigz`).
- 🧹 **Cache Management**: Instantly clear local package and stage tarball caches with `--clean-cache`.
- 🧪 **Full Pytest/Unittest Suite**: 100% passing unit and integration tests (22/22 tests passing).
- ⚙️ **CI/CD Ready**: Automated GitHub Actions testing workflow for Python 3.10 through 3.13.

---

## Quick Start

### 1. Verification & Validation (`--check`)

Audit your environment and configurations:

```bash
python3 cli.py --check
```

### 2. High-Speed Benchmark Build (`--fast` & `--benchmark`)

Run an ultra-fast build in RAM with per-stage timing breakdown:

```bash
sudo python3 cli.py x86_64 --preset desktop-xfce --fast --tmpfs --benchmark --mode real
```

### 3. Interactive Wizard (`--interactive`)

Configure and build interactively:

```bash
python3 cli.py -i
```

### 4. Build a Pre-defined Edition / Preset (`--preset`)

Build specialized flavours in simulation or production mode:

```bash
# Minimal Server/Console
python3 cli.py x86_64 --preset minimal --mode mock

# Rescue & SysAdmin Edition (Forensics, Partitioning, Network Tools)
python3 cli.py x86_64 --preset rescue-sysadmin --mode mock

# Developer Workstation
python3 cli.py x86_64 --preset developer --mode mock

# Gaming Edition with Steam & Vulkan
python3 cli.py x86_64 --preset gaming --mode mock
```

### 5. Custom Hostname, Locale, Timezone & Keymap

Customize system localization directly from the CLI:

```bash
sudo python3 cli.py x86_64 -P desktop-xfce \
    --hostname my-void \
    --locale pt_PT.UTF-8 \
    --timezone Europe/Lisbon \
    --keymap pt-latin1 \
    --mode real
```

### 6. Rapid Production ISO Build using Stage Seed (`--use-tarball`)

Build a production XFCE ISO in seconds by unpacking a pre-built base stage tarball and applying `xbps-install -Syu`:

```bash
sudo python3 cli.py x86_64 -d xfce -p desktop-essentials,internet --use-tarball y --mode real
```

### 7. Create a Reusable Base Stage Tarball (`--create-tarball`)

Generate a reusable stage seed tarball stored in `output/stage_seeds/void-base-x86_64.tar.xz`:

```bash
sudo python3 cli.py x86_64 --create-tarball --mode real
```

### 8. Raspberry Pi 4 Disk Image

Build a Raspberry Pi 64-bit disk image:

```bash
sudo python3 cli.py rpi-aarch64 --mode real
```

---

## Command Line Quick Reference

| Flag | Example | Description |
| :--- | :--- | :--- |
| `ARCHITECTURE` | `x86_64`, `rpi-aarch64` | Target architecture (default: `x86_64`). |
| `-P`, `--preset` | `-P desktop-xfce` | Pre-defined profile preset (`minimal`, `desktop-xfce`, `desktop-kde`, `desktop-gnome`, `rescue-sysadmin`, `developer`, `gaming`). |
| `--fast`, `--quick` | `--fast` | Ultra-fast build mode (`zstd -3`, fast block sizes, optimal staging). |
| `--tmpfs` | `--tmpfs` | Build in memory RAM (`tmpfs`) to maximize I/O throughput (3x-5x faster). |
| `--benchmark` | `--benchmark` | Record and display per-stage build timing breakdown. |
| `-j`, `--jobs` | `-j 8` | CPU threads for compression and packaging. |
| `--mode` | `mock` / `real` | Execution mode (default: `mock`). |
| `--dry-run` | `--dry-run` | Alias for `--mode mock`. |
| `--format` | `iso` / `img` / `tarball` | Build output format (default: `iso`). |
| `--hostname` | `--hostname void-pc` | Custom system hostname. |
| `--locale` | `--locale pt_PT.UTF-8` | Custom system locale. |
| `--timezone` | `--timezone Europe/Lisbon`| Custom system timezone. |
| `--keymap` | `--keymap pt-latin1` | Custom console keymap. |
| `--root-password` | `--root-password secret` | Set password for root user. |
| `--lock-root` | `--lock-root` | Lock root account password. |
| `--live-password` | `--live-password pass` | Custom password for live user (default: `live`). |
| `--ssh-key` | `--ssh-key ~/.ssh/id_ed25519.pub` | Inject SSH public key file into `authorized_keys`. |
| `--hook` | `--hook post-install:my_script.sh` | Execute lifecycle hook script (`pre-install`, `post-install`, `pre-iso`, `post-iso`). |
| `--use-tarball`, `--tarball` | `--use-tarball y` | Unpack a base stage seed (local path, URL, or `y`/`auto`) to speed up builds. |
| `--create-tarball` | `--create-tarball` | Save bootstrapped base system as a reusable stage seed in `output/stage_seeds/`. |
| `--compression` | `xz` / `zstd` / `gzip` | Compression algorithm (default: `xz`). |
| `--check` | `--check` | Validate configuration and exit. |
| `--save-config` | `--save-config build.json` | Export assembled configuration JSON snapshot. |
| `--clean-cache` | `--clean-cache` | Clear package and stage seed caches and exit. |
| `-i`, `--interactive`| `-i` | Launch interactive configuration wizard. |
| `-d`, `--desktop` | `-d xfce` | Desktop environment profile override. |
| `-k`, `--kernel` | `-k linux-lts` | Kernel selection. |
| `-p`, `--package-profile` | `-p desktop-essentials,internet` | Additional package profiles (comma-separated or repeated flags). |
| `--with-calamares` | `--with-calamares` | Compile and inject Calamares installer. |

---

## Building Documentation Locally

To compile the HTML documentation locally:

```bash
sphinx-build -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html` in your browser.

---

## Author & Credits

- **Author & Lead Maintainer**: Manuel Rosa (<manuelsilvarosa@gmail.com>)

---

## License

This project is licensed under the [MIT License](LICENSE).

