# Void-Builder Comprehensive Manual

Welcome to the exhaustive technical documentation for **Void-Builder**, the modular, dynamic, and multi-architecture Void Linux ISO and disk image building toolkit.

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

## Overview & Technical Summary

Void-Builder is a enterprise-grade Python application designed to assemble bootable live ISO images, raw Single-Board Computer (SBC) disk images, and container rootfs archives for **Void Linux**. It provides a fully decoupled architecture separating configuration resolution, host toolchain management, pseudo-filesystem chroot management, system customization, and output finalization.

### Supported Target Architectures (12 Total)

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
