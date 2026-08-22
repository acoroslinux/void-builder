# Void-Builder Comprehensive Technical Manual

Welcome to the comprehensive technical documentation for **Void-Builder**, the enterprise-grade, modular, dynamic, and multi-architecture Void Linux ISO and disk image building toolkit.

```text
                  _     _                      _  _     _                 
  _   ___ (_) __| |   |__  _  _  _ | |__| |___  _ __ 
 | |/ / _ \| |/ _` |  | '_ \| | | | | | / _` / _ \| '__|
 | < (_) | | (_| |  | |_) | |_| | |_| | (_| | __/ |   
 |_|\_\___/|_|\__,_|  |_.__/ \__,_|\__,_|\__,_|\___|_|   
```

---

## Technical Documentation Index

```{toctree}
:maxdepth: 2
:caption: User Guide

getting_started
usage
cli_reference
configuration
package_rules
custom_packages
```

```{toctree}
:maxdepth: 2
:caption: Architecture & Bootloaders

architecture
bootloaders
calamares
api_reference
troubleshooting
```

---

## Overview & Architecture Highlights

**Void-Builder** is an advanced Python-based toolkit designed to assemble bootable live ISO images, raw Single-Board Computer (SBC) disk images, and container rootfs archives for **Void Linux**. It provides a fully decoupled architecture separating configuration resolution, host toolchain management, pseudo-filesystem chroot management, system customization, and output finalization.

### Key Capabilities

* 🌐 **12 Hardware Architectures & Platforms**: Build for x86_64, x86_64-musl, i686, aarch64, aarch64-musl, armv7l, armv7l-musl, Raspberry Pi (aarch64, armv7l, armv6l), Pinebook Pro, and Apple Silicon (Asahi).
* 🎯 **Unified Presets & Flavours (`-P` / `--preset`)**: Ready-to-build editions (`minimal`, `desktop-xfce`, `desktop-kde`, `desktop-gnome`, `rescue-sysadmin`, `developer`, `gaming`).
* ⚡ **High-Speed Turbo Pipeline (`--fast`, `--tmpfs`, `--benchmark`)**: Multi-threaded `zstd` compression level 3, fast formatting, build in memory RAM (`tmpfs`), and per-stage timing breakdown.
* 📦 **Gentoo-Style Stage Seed Tarballs (`--use-tarball`, `--create-tarball`)**: Bootstraps from reusable base archives and layers delta packages in seconds.
* 🔑 **Security & SSH Public Key Ingestion**: Inject root passwords, lock accounts, and provision SSH keys directly into `authorized_keys`.
* 🪝 **Lifecycle Hooks Engine**: Execute customized shell scripts at `pre-install`, `post-install`, and `pre-iso` stages.
* 🤖 **Interactive Wizard Mode (`-i` / `--interactive`)**: Intuitive terminal menu for step-by-step image creation.
* 🛡️ **Zero Host Dependencies**: Downloads verified static `xbps-install.static` binaries directly from Void Linux infrastructure.
* 🧾 **Automated Checksums & Manifests**: Automatically generates `.sha256`, `.sha512`, `.md5`, and `.manifest.json` metadata for all build artifacts.

---

## Supported Target Architectures

1. **`x86_64`**: Standard 64-bit AMD/Intel PC (glibc)
2. **`x86_64-musl`**: 64-bit AMD/Intel PC with Musl C library
3. **`i686`**: 32-bit Legacy x86 PC
4. **`aarch64`**: 64-bit ARM64 Generic (glibc)
5. **`aarch64-musl`**: 64-bit ARM64 Generic (Musl)
6. **`armv7l`**: 32-bit ARMv7 Hard Float (glibc)
7. **`armv7l-musl`**: 32-bit ARMv7 Hard Float (Musl)
8. **`rpi-aarch64`**: Raspberry Pi 3/4/5 (64-bit)
9. **`rpi-armv7l`**: Raspberry Pi 2/3 (32-bit v7)
10. **`rpi-armv6l`**: Raspberry Pi 1/Zero (32-bit v6)
11. **`pinebookpro`**: Pine64 Pinebook Pro (RK3399 SoC)
12. **`asahi`**: Apple Silicon (M1/M2/M3) Asahi Linux

---

## Author & Maintainer

- **Developer & Lead Maintainer**: Manuel Rosa ([manuelsilvarosa@gmail.com](mailto:manuelsilvarosa@gmail.com))


