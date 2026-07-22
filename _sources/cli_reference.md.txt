# CLI Complete Reference

This reference documents every command-line option, environment variable, exit code, and execution behavior supported by `cli.py`.

---

## Command Syntax

```bash
python3 cli.py [ARCHITECTURE] [OPTIONS]
```

---

## Positional Arguments

### `ARCHITECTURE`
- **Description**: Target architecture or platform profile to build.
- **Allowed Values**:
  - `x86_64` (default)
  - `x86_64-musl`
  - `i686`
  - `aarch64`
  - `aarch64-musl`
  - `armv7l`
  - `armv7l-musl`
  - `rpi-aarch64`
  - `rpi-armv7l`
  - `rpi-armv6l`
  - `pinebookpro`
  - `asahi`
- **Default**: `x86_64`

---

## Core Execution Flags

### `-c CONFIG`, `--config CONFIG`
- **Description**: Path to master global JSON configuration file.
- **Default**: `configs/global_build.json`

### `--mode {mock,real}`
- **Description**: Execution mode.
  - `mock`: Non-root simulation. Validates configurations, simulates XBPS installation, writes placeholder images.
  - `real`: Performs actual package downloading, mounting, chroot operations, and binary image creation. Requires `root` / `sudo`.
- **Default**: `mock`

### `--check`, `--validate`
- **Description**: Runs comprehensive configuration audit (JSON file integrity, profile resolution, package list assembly) and exits without building.
- **Exit Code**: `0` on success, `1` on validation failure.

### `--clean` / `--no-clean`
- **Description**: Controls pre-build workspace directory cleaning.
  - `--clean`: Purges previous `airootfs` and `iso-staging` before starting (default).
  - `--no-clean`: Preserves existing chroot files for incremental builds.

### `--format {iso,img,tarball}`
- **Description**: Selects output artifact format.
  - `iso`: Hybrid ISO 9660 image with BIOS/UEFI bootloaders.
  - `img`: Partitioned disk image (VFAT `/boot` + EXT4 `/`).
  - `tarball`: Compressed `.tar.xz` rootfs archive for containers/LXC.
- **Default**: `iso`

### `--compression {xz,zstd,gzip}`
- **Description**: Compression algorithm for SquashFS container and Dracut initramfs image.
- **Default**: `xz`

### `--generate-manifest` / `--no-manifest`
- **Description**: Enables/disables creation of `.sha256`, `.md5`, and `.manifest.json` files alongside the output image. Enabled by default.

---

## Customization Overrides

### `-d DESKTOP`, `--desktop DESKTOP`
- **Description**: Desktop environment profile name located in `configs/desktops/<DESKTOP>.json`.
- **Available Profiles**: `awesome`, `bspwm`, `budgie`, `cinnamon`, `enlightenment`, `fluxbox`, `gnome`, `herbstluftwm`, `i3`, `icewm`, `kde`, `lxde`, `lxqt`, `mate`, `openbox`, `qtile`, `sway`, `xfce`.

### `-k KERNEL`, `--kernel KERNEL`
- **Description**: Kernel profile name from `configs/kernels/` or direct XBPS package name (e.g., `linux-lts`, `linux6.6`).

### `-b BOOTLOADER`, `--bootloader BOOTLOADER`
- **Description**: Bootloader profile name from `configs/bootloaders/` (e.g., `grub`).

### `-p PACKAGE_PROFILE`, `--package-profile PACKAGE_PROFILE`
- **Description**: Additional package bundle profile from `configs/packages/` (can be passed multiple times).

### `-s SERVICE_PROFILE`, `--service-profile SERVICE_PROFILE`
- **Description**: Additional Runit service profile from `configs/services/` (can be passed multiple times).

### `--live-user USERNAME`
- **Description**: Overrides the live ISO username (default: `live`).

### `--live-groups GROUPS`
- **Description**: Comma-separated list of group memberships for live user (e.g., `wheel,audio,video,storage,network`).

### `-R REPOSITORY`, `--repository REPOSITORY`
- **Description**: Appends a custom XBPS repository URL (can be passed multiple times). Evaluated at highest priority.

### `-I INCLUDE_DIR`, `--include INCLUDE_DIR`
- **Description**: Copies custom directory tree into the target rootfs at `/` (can be passed multiple times).

---

## Toolchain & Advanced Flags

### `--force-isolated-toolchain`
- **Description**: Forces downloading static XBPS binaries even if host system provides `xbps-install`.

### `--update-toolchain`
- **Description**: Redownloads and updates static `xbps-install.static` binaries.

### `--list-options`
- **Description**: Lists all available desktops, kernels, bootloaders, architectures, and profiles then exits.

### `--with-calamares`
- **Description**: Compiles local Calamares package via `void-packages` and injects it into the live ISO image.

---

## Exit Codes

- `0`: Successful execution / validation.
- `1`: Build failure, configuration validation error, or permission error.
- `127`: Missing system command dependencies.

---

## Environment Variables

| Variable | Description |
| :--- | :--- |
| `SUDO_USER` | Used during Calamares non-root build compilation. |
| `XBPS_ARCH` | Override target XBPS architecture. |
| `PYTHONPATH` | Python import path search directory. |
