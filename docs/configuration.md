# Configuration Guide & JSON Schemas

This document provides a comprehensive specification of the configuration subdirectories, JSON file formats, schema fields, and customization mechanics in **Void-Builder**.

---

## 1. Directory Layout & Profile Roles

All configuration files reside in the `configs/` directory:

```text
configs/
├── global_build.json     # Master build manifest (repositories, defaults, services)
├── package_rules.json    # Dynamic package matching and injection rules
├── base_customizations.json # System customization baseline (hostname, timezone, locale)
├── architectures/        # Target architecture profiles (x86_64.json, rpi-aarch64.json)
├── desktops/             # Desktop environment package bundles (gnome.json, xfce.json)
├── kernels/              # Kernel package selection profiles (linux-lts.json)
├── bootloaders/          # Bootloader installation profiles (grub.json)
├── packages/             # Optional package bundle profiles (dev-tools.json)
├── services/             # Runit service activation profiles (ssh.json, bluetooth.json)
├── live-users/           # Live environment account profiles (admin.json, guest.json)
├── platforms/            # Single-board hardware platform overrides (pinebookpro.json)
├── assets/               # Artwork, isolinux configuration templates, GRUB fonts
└── custom_files/         # Overlay file tree copied directly into rootfs at /
```

---

## 2. Master Manifest: `global_build.json`

`global_build.json` defines the foundational baseline settings for every build.

### Complete Annotated Schema

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
  "initramfs": {
    "compression": "xz"
  },
  "boot_title": "Void Modern Live",
  "boot_cmdline": "quiet splash live.user=live live.autologin rd.live.overlay.overlayfs=1",
  "splash_image": "configs/assets/data/splash.png",
  "repositories": [
    "https://repo-default.voidlinux.org/current",
    "https://repo-default.voidlinux.org/current/musl",
    "https://repo-default.voidlinux.org/current/aarch64"
  ],
  "custom_repositories": [],
  "customizations": {
    "hostname": "void-modern",
    "timezone": "UTC",
    "locale": "en_US.UTF-8",
    "keymap": "us",
    "users": [
      {
        "name": "live",
        "groups": [
          "wheel",
          "audio",
          "video",
          "storage",
          "network"
        ],
        "password": "live"
      }
    ],
    "services": [
      "dbus",
      "NetworkManager",
      "polkitd",
      "bluetoothd",
      "cupsd",
      "avahi-daemon",
      "sshd",
      "chronyd",
      "alsa",
      "acpid",
      "elogind",
      "wpa_supplicant"
    ]
  },
  "common_desktop_packages": [
    "NetworkManager",
    "alsa-firmware",
    "alsa-pipewire",
    "alsa-utils",
    "avahi",
    "blueman",
    "bluez",
    "dbus",
    "elogind",
    "flatpak",
    "git",
    "nano",
    "pipewire",
    "plymouth",
    "polkit",
    "python3",
    "sudo",
    "vim",
    "wpa_supplicant",
    "xorg"
  ],
  "package_sources": {
    "official": [
      "base-system",
      "vim",
      "git",
      "curl",
      "bash-completion",
      "mtools",
      "gptfdisk",
      "efibootmgr",
      "dosfstools",
      "binutils",
      "xz",
      "device-mapper",
      "dhclient",
      "dracut-network",
      "openresolv"
    ]
  }
}
```

### Key Field Descriptions
- **`system.iso_label`**: Volume identifier string for the ISO9660 volume (`VOID_MODERN`).
- **`system.workdir_base`**: Base working directory for staging files.
- **`system.xbps_cache`**: Target directory for cached `.xbps` binary package archives.
- **`boot_cmdline`**: Linux kernel boot command-line parameters passed by isolinux/GRUB.
- **`repositories`**: Official Void Linux XBPS mirror URLs evaluated in order.
- **`customizations.services`**: List of Runit services enabled by symlinking `/etc/sv/<service>` into `/etc/runit/runsvdir/default/`.
- **`customizations.users`**: Account definitions to create during rootfs provisioning.

---

## 3. Architecture Profiles (`configs/architectures/`)

Architecture profiles define specific package lists, repositories, or flags for particular architectures.

### Example: `configs/architectures/rpi-aarch64.json`

```json
{
  "architecture": "rpi-aarch64",
  "xbps_arch": "aarch64",
  "engine": "PlatformEngine",
  "repositories": [
    "https://repo-default.voidlinux.org/current/aarch64"
  ],
  "package_sources": {
    "official": [
      "rpi-base",
      "rpi-kernel",
      "raspberrypi-userland"
    ]
  }
}
```

---

## 4. Desktop Profiles (`configs/desktops/`)

Desktop profiles specify packages required to build a functional graphical desktop environment.

### Example: `configs/desktops/xfce.json`

```json
{
  "desktop_environment": "xfce",
  "display_manager": "lightdm",
  "package_sources": {
    "official": [
      "xfce4",
      "xfce4-panel",
      "xfce4-settings",
      "xfce4-session",
      "xfwm4",
      "xfdesktop",
      "thunar",
      "lightdm",
      "lightdm-gtk-greeter",
      "network-manager-applet",
      "pavucontrol"
    ]
  },
  "customizations": {
    "services": [
      "lightdm",
      "dbus",
      "NetworkManager"
    ]
  }
}
```

---

## 5. Runit Service Profiles (`configs/services/`)

Service profiles allow easily toggling background daemons.

### Example: `configs/services/ssh.json`

```json
{
  "service_name": "ssh",
  "package_sources": {
    "official": [
      "openssh"
    ]
  },
  "customizations": {
    "services": [
      "sshd"
    ]
  }
}
```

---

## 6. How to Create a Brand New Desktop Profile

To add a new desktop environment profile (e.g. `configs/desktops/pantheon.json`):

1. Create `configs/desktops/pantheon.json`:
   ```json
   {
     "desktop_environment": "pantheon",
     "package_sources": {
       "official": [
         "pantheon-desktop",
         "lightdm",
         "lightdm-pantheon-greeter",
         "gsettings-desktop-schemas"
       ]
     },
     "customizations": {
       "services": [
         "lightdm",
         "dbus"
       ]
     }
   }
   ```

2. Validate the configuration:
   ```bash
   python3 cli.py x86_64 -d pantheon --check
   ```

3. Build ISO:
   ```bash
   sudo python3 cli.py x86_64 -d pantheon --mode real
   ```

---

## 7. File Overlays (`configs/custom_files/`)

Any directory or file placed inside `configs/custom_files/` is automatically copied directly into the target rootfs at `/` during system customization.

Example:
- `configs/custom_files/etc/motd` -> copied to `/etc/motd` in target system.
- `configs/custom_files/etc/skel/.config/xfce4/` -> copied to `/etc/skel/.config/xfce4/` in target system.
