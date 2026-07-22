# Configuration Guide

Void-Builder uses modular JSON configuration files located under the `configs/` directory.

---

## Directory Structure

```text
configs/
├── architectures/        # Architecture profiles (x86_64, rpi-aarch64, etc.)
├── assets/               # Splash images, artwork, isolinux templates
├── base_customizations.json
├── bootloaders/          # Bootloader configs (grub.json)
├── custom_files/         # Overlay files to copy into rootfs
├── desktops/             # Desktop environment package profiles (gnome, kde, xfce, etc.)
├── global_build.json     # Master build settings and repository definitions
├── kernels/              # Kernel profiles (linux-lts.json, linux-mainline.json)
├── live-users/           # Pre-configured live user profiles
├── package_rules.json    # Dynamic package matching rules
├── packages/             # Optional package bundle profiles
├── platforms/            # Hardware-specific SBC platform settings
└── services/             # Runit service profiles (ssh.json, bluetooth.json)
```

---

## Master Config: `global_build.json`

Key sections of `global_build.json`:

```json
{
  "system": {
    "iso_label": "VOID_MODERN",
    "workdir_base": "workdir",
    "xbps_cache": "workdir/cache/xbps"
  },
  "iso": {
    "compression_type": "xz"
  },
  "boot_title": "Void Modern Live",
  "boot_cmdline": "quiet splash live.user=live live.autologin rd.live.overlay.overlayfs=1",
  "repositories": [
    "https://repo-default.voidlinux.org/current",
    "https://repo-default.voidlinux.org/current/musl",
    "https://repo-default.voidlinux.org/current/aarch64"
  ],
  "customizations": {
    "hostname": "void-modern",
    "timezone": "UTC",
    "locale": "en_US.UTF-8",
    "keymap": "us",
    "services": [
      "dbus",
      "NetworkManager",
      "polkitd"
    ]
  }
}
```

---

## Adding Custom Desktop Profiles

To create a custom desktop environment profile (e.g. `configs/desktops/hyprland.json`):

```json
{
  "desktop_environment": "hyprland",
  "package_sources": {
    "official": [
      "hyprland",
      "waybar",
      "kitty",
      "wofi",
      "dunst",
      "polkit-gnome",
      "pipewire",
      "wireplumber"
    ]
  },
  "customizations": {
    "services": [
      "dbus",
      "seatd"
    ]
  }
}
```

Then build using:

```bash
python3 cli.py x86_64 -d hyprland --mode mock
```
