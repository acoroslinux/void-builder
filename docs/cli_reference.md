# CLI Complete Technical Reference

This reference documents every command-line option, environment variable, exit code, and execution behavior supported by `cli.py` and the `void-builder` console script.

---

## Command Syntax

```bash
void-builder [ARCHITECTURE] [OPTIONS]
# or:
python3 cli.py [ARCHITECTURE] [OPTIONS]
```

---

## Positional Arguments

### `ARCHITECTURE`
- **Description**: Target architecture or hardware platform profile.
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

## Presets & Editions

### `-P PRESET`, `--preset PRESET`
- **Description**: Pre-defined unified profile preset from `configs/presets/`. Configures desktops, package sets, kernel, bootloader, services, and repositories in a single flag.
- **Available Presets**:
  - `minimal`: Minimal console/server system without X11/Wayland.
  - `desktop-xfce`: Fast and lightweight XFCE workstation with LightDM.
  - `desktop-kde`: Modern KDE Plasma 6 environment.
  - `desktop-gnome`: GNOME 4x desktop with GDM.
  - `rescue-sysadmin`: Forensics, disk rescue, partition recovery, and network diagnostic tools (GParted, TestDisk, ddrescue, Wireshark, Nmap).
  - `developer`: Comprehensive developer environment (Rust, Go, Python, Podman, Neovim, Zsh, Clang, CMake, Git).
  - `gaming`: Steam, Vulkan drivers, MangoHud, GameMode, Wine, and automated multilib/nonfree repository enablement.

---

## Performance & Speed Flags

### `--fast`, `--quick`
- **Description**: Activates ultra-fast build pipeline.
  - Switches compression to `zstd` with level `3` (5x to 10x faster than XZ).
  - Optimizes SquashFS block size to `256K`.
  - Enables fast disk formatting (`fast_commit` and lazy inode table initialization).

### `--tmpfs`
- **Description**: Stages and mounts the entire `workdir/` build tree inside RAM (`tmpfs`), boosting I/O throughput (3x-5x faster) and preventing SSD/NVMe write wear. Automatically unmounts on completion.

### `--benchmark`
- **Description**: Records and prints a structured execution timing report measuring each build stage (Toolchain/Chroot setup, Package installation, Post-install customizations, Bootloader generation, SquashFS compression, and Final artifact generation).

### `-j JOBS`, `--jobs JOBS`
- **Description**: Number of CPU threads to allocate for multi-threaded compression and packaging (default: all available CPU cores).

---

## Execution Modes & Actions

### `--mode {mock,real}`
- **Description**: Execution mode.
  - `mock`: Non-root simulation. Validates configurations, simulates XBPS installation, writes placeholder images.
  - `real`: Performs actual package downloading, mounting, chroot operations, and binary image creation. Requires `root` / `sudo`.
- **Default**: `mock`

### `--dry-run`
- **Description**: Alias for `--mode mock`.

### `-i`, `--interactive`
- **Description**: Launches the interactive configuration wizard in the terminal, guiding the user step-by-step through architecture, preset, format, and mode selection.

### `--check`, `--validate`
- **Description**: Runs comprehensive configuration audit (JSON file integrity, profile resolution, package list assembly) and exits without building.
- **Exit Code**: `0` on success, `1` on validation failure.

### `--clean-cache`
- **Description**: Clears downloaded XBPS packages and cached stage seed tarballs (`workdir/cache/xbps`, `workdir/cache/tarballs`), then exits.

---

## System & Localization Overrides

### `--hostname HOSTNAME`
- **Description**: Overrides system hostname (written to `/etc/hostname`).

### `--locale LOCALE`
- **Description**: Overrides system default locale (e.g. `pt_PT.UTF-8`, `en_US.UTF-8`, `de_DE.UTF-8`). Configures `/etc/default/libc-locales` and `/etc/locale.conf`.

### `--timezone TIMEZONE`
- **Description**: Overrides system timezone (e.g. `Europe/Lisbon`, `America/Sao_Paulo`, `UTC`). Sets `/etc/localtime`.

### `--keymap KEYMAP`
- **Description**: Overrides console keymap (e.g. `pt-latin1`, `br-abnt2`, `us`). Configures `/etc/rc.conf`.

---

## Security & User Management

### `--root-password PASSWORD`
- **Description**: Sets the root user password directly during system configuration.

### `--lock-root`
- **Description**: Disables/locks the root account password for security (`passwd -l root`).

### `--live-password PASSWORD`
- **Description**: Sets a custom password for the live user (default: `live`).

### `--ssh-key PATH`
- **Description**: Path to an SSH public key file to inject into `/root/.ssh/authorized_keys` and `/home/<live_user>/.ssh/authorized_keys` with secure permissions (`0700`/`0600`). Can be specified multiple times.

### `--ssh-pubkey "KEY"`
- **Description**: Direct SSH public key string to append to authorized keys.

---

## Lifecycle Hooks Engine

### `--hook PHASE:PATH`
- **Description**: Registers a custom shell hook script to be executed at a specific build stage.
- **Phases**:
  - `pre-install`: Runs before XBPS installs packages.
  - `post-install`: Runs inside the chroot after package installation and configuration.
  - `pre-iso`: Runs outside the chroot before SquashFS/disk image compression.
  - `post-iso`: Runs after output artifacts and checksums are finalized.
- **Example**: `--hook post-install:configs/hooks/post-install.example.sh`

---

## Output & Formats

### `--format {iso,img,tarball}`
- **Description**: Target build artifact format.
  - `iso`: Hybrid ISO 9660 image with BIOS/UEFI bootloaders.
  - `img`: Partitioned disk image (VFAT `/boot` + EXT4 `/`).
  - `tarball`: Compressed `.tar.xz` rootfs archive for containers/LXC.
- **Default**: `iso`

### `--compression {xz,zstd,gzip}`
- **Description**: Compression algorithm for SquashFS container and Dracut initramfs image. Default: `xz` (or `zstd` with `--fast`).

### `--save-config PATH`
- **Description**: Exports the assembled build configuration snapshot as JSON to the specified path for documentation and reproducible builds.

### `--use-tarball [SOURCE]`, `--tarball [SOURCE]`
- **Description**: Rapidly builds target ISO/image by unpacking a pre-built base system stage seed (`.tar.xz` / `.tar.zst`), running `xbps-install -Syu` inside the chroot, and layering requested desktop/delta package profiles.

### `--create-tarball`
- **Description**: Saves the bootstrapped base rootfs as a reusable stage seed tarball in `output/stage_seeds/void-base-<arch>.tar.xz` and `workdir/cache/tarballs/void-base-<arch>.tar.xz`.

### `--generate-manifest` / `--no-manifest`
- **Description**: Enables/disables creation of `.sha256`, `.sha512`, `.md5`, and `.manifest.json` files alongside the output image. Default: enabled.

---

## Exit Codes

- `0`: Successful execution / validation.
- `1`: Build failure, configuration validation error, or permission error.
- `127`: Missing system command dependencies.

