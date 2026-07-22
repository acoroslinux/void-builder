# Void-Builder Documentation

Welcome to the official documentation for **Void-Builder**, a modular, dynamic, and multi-architecture Void Linux ISO and disk image building toolkit.

```
                  _     _                      _  _     _                 
  _   ___ (_) __| |   |__  _  _  _ | |__| |___  _ __ 
 | |/ / _ \| |/ _` |  | '_ \| | | | | | / _` / _ \| '__|
 | < (_) | | (_| |  | |_) | |_| | |_| | (_| | __/ |   
 |_|\_\___/|_|\__,_|  |_.__/ \__,_|\__,_|\__,_|\___|_|   
```

---

## Table of Contents

```{toctree}
:maxdepth: 2

getting_started
usage
architecture
configuration
calamares
troubleshooting
```

---

## Highlights & Key Features

- **Multi-Architecture Support**: Native and cross-architecture builds for `x86_64`, `x86_64-musl`, `i686`, `aarch64`, `aarch64-musl`, `armv7l`, `armv7l-musl`, `rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l`, `pinebookpro`, and `asahi`.
- **Multiple Output Formats**: Generate bootable ISO images (`.iso`), raw platform disk images (`.img`), or RootFS container tarballs (`.tar.xz`).
- **Flexible Execution Modes**: Simulation mode (`--mode mock`) for fast non-root configuration testing, and real mode (`--mode real`) for production image building.
- **Config Validation**: Built-in verification command (`--check`) to audit JSON configurations and profile integrity before starting a build.
- **Automatic Checksums & Manifests**: Automatically generates `.sha256`, `.md5`, and structured `.manifest.json` files detailing installed packages, versions, and build metadata.
- **Compression Algorithms**: Choose between `xz`, `zstd`, and `gzip` for SquashFS and Dracut initramfs.
- **Modular Profiles**: Dynamic JSON configuration profiles for desktops, kernels, bootloaders, packages, services, live users, and hardware platforms.
- **Calamares Pipeline**: Native compilation and local repository injection pipeline for the Calamares installer.
