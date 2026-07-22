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
- [CLI Reference & 10 End-to-End Examples](https://acoroslinux.github.io/void-builder/usage.html)
- [Complete JSON Configuration Schemas](https://acoroslinux.github.io/void-builder/configuration.html)
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
- 🛡️ **Total Build Isolation**: Zero host package manager dependencies! Static `xbps-install.static` and `proot` binaries are automatically downloaded and executed in isolated environments.
- 🛠️ **Multiple Output Formats**:
  - `.iso`: Hybrid bootable ISO images (BIOS + UEFI)
  - `.img`: Partitioned raw disk images for SD cards / eMMC
  - `.tar.xz`: Compressed RootFS container tarballs
- ⚡ **Compression Flexibility**: Select between `xz`, `zstd`, and `gzip` for SquashFS and Dracut initramfs.
- 🔍 **Built-in Configuration Validator**: Run `--check` to audit JSON profiles before building.
- 🧾 **Automatic Manifest & Checksum Generation**: Generates `.sha256`, `.md5`, and structured `.manifest.json` files for every build artifact.
- 🍕 **Calamares Pipeline**: Native compilation and local XBPS repository injection for the Calamares installer.
- 🧪 **Full Pytest Suite**: 100% passing unit and integration tests.

---

## Quick Start

### 1. Verification & Validation (`--check`)

Audit your environment and configurations:

```bash
python3 cli.py --check
```

### 2. Fast Simulation (`--mode mock`)

Simulate an `x86_64` ISO build with XFCE without requiring root privileges:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

### 3. Production ISO Build (`--mode real`)

Create an official bootable x86_64 ISO:

```bash
sudo python3 cli.py x86_64 -d gnome --mode real
```

### 4. Raspberry Pi 4 Disk Image

Build a Raspberry Pi 64-bit disk image:

```bash
sudo python3 cli.py rpi-aarch64 --mode real
```

### 5. Container RootFS Export (`--format tarball`)

Export a custom rootfs tarball for containers or LXC:

```bash
sudo python3 cli.py x86_64 --mode real --format tarball
```

---

## Command Line Quick Reference

| Flag | Example | Description |
| :--- | :--- | :--- |
| `ARCHITECTURE` | `x86_64`, `rpi-aarch64` | Target architecture (default: `x86_64`). |
| `--mode` | `mock` / `real` | Execution mode (default: `mock`). |
| `--format` | `iso` / `img` / `tarball` | Build output format (default: `iso`). |
| `--compression` | `xz` / `zstd` / `gzip` | Compression algorithm (default: `xz`). |
| `--check` | `--check` | Validate configuration and exit. |
| `-d`, `--desktop` | `-d xfce` | Desktop environment profile. |
| `-k`, `--kernel` | `-k linux-lts` | Kernel selection. |
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