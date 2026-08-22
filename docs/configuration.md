# Configuration Guide & JSON Schemas

This document provides a comprehensive specification of the configuration subdirectories, JSON file formats, schema fields, and customization mechanics in **Void-Builder**.

---

## 1. Directory Layout & Profile Roles

All configuration files reside in the `configs/` directory:

```text
configs/
├── global_build.json        # Master build manifest (repositories, defaults, services)
├── package_rules.json       # Dynamic package matching and injection rules
├── base_customizations.json # System customization baseline (hostname, timezone, locale)
├── presets/                 # Unified build presets (minimal.json, gaming.json, developer.json)
├── hooks/                   # Lifecycle hook script templates (pre-install, post-install, pre-iso)
├── architectures/           # Target architecture profiles (x86_64.json, rpi-aarch64.json)
├── desktops/                # Desktop environment package bundles (gnome.json, xfce.json)
├── kernels/                 # Kernel package selection profiles (linux-lts.json)
├── bootloaders/             # Bootloader installation profiles (grub.json)
├── packages/                # Modular package bundle profiles (dev-tools.json, gaming.json)
├── services/                # Runit service activation profiles (ssh.json, bluetooth.json)
├── live-users/              # Live environment account profiles (admin.json, guest.json)
├── platforms/               # Single-board hardware platform overrides (pinebookpro.json)
├── assets/                  # Artwork, isolinux configuration templates, GRUB fonts
└── custom_files/            # Overlay file tree copied directly into rootfs at /
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

## 4. Package Bundle Profiles (`configs/packages/`)

Package profiles allow modular bundle composition across 16 categories (`desktop-essentials`, `dev-tools`, `filesystems`, `multimedia`, `office`, `gaming`, `networking`, `virtualization`, `graphics`, `printing`, `xorg`, `wayland`, `internet`, `custom-user`, `base`, `installer`).

### Automatic Profile Defaults
- Both **`base.json`** and **`filesystems.json`** are loaded automatically by default for **all** builds to guarantee base system utilities and filesystem driver compatibility (`btrfs-progs`, `xfsprogs`, `f2fs-tools`, `ext4`, `ntfs-3g`, `exfatprogs`, `dosfstools`, `parted`, `gptfdisk`, etc.).

### Package Profile JSON Schema (`packages` + `optional_packages`)

All 16 package profile JSON files follow a clean, standardized schema:

```json
{
  "name": "desktop-essentials",
  "description": "Essential desktop GUI utilities, CLI networking tools, media codecs, archive tools, and rich typography",
  "_comment": "Note: Core desktop utilities are active defaults in 'packages'. Additional desktop helpers (Picom, Feh, Dmenu, Rofi) are listed in 'optional_packages' for easy enablement.",
  "packages": [
    "git",
    "curl",
    "wget",
    "octoxbps",
    "gparted",
    "keepassxc",
    "file-roller",
    "zip",
    "unzip",
    "p7zip",
    "unar",
    "tar",
    "zstd",
    "ffmpeg",
    "gst-plugins-base1",
    "gst-plugins-good1",
    "gst-plugins-bad1",
    "gst-plugins-ugly1",
    "gst-libav",
    "font-inter",
    "noto-fonts-ttf",
    "noto-fonts-cjk",
    "noto-fonts-emoji",
    "dejavu-fonts-ttf",
    "liberation-fonts-ttf",
    "font-awesome",
    "cantarell-fonts",
    "ttf-ubuntu-font-family"
  ],
  "optional_packages": [
    "unrar",
    "picom",
    "feh",
    "dmenu",
    "rofi"
  ]
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

## 7. Custom File Management & Scalable Overlays

**Void-Builder** provides 3 distinct, scalable mechanisms for copying custom files and directories into the target system:

### A. Direct Filesystem Overlay (`configs/overlay/`)
The simplest and most scalable method. Any file or directory placed inside `configs/overlay/` is automatically discovered and mirrored directly to the target rootfs at `/` with attributes preserved and ownership normalized:
* `configs/overlay/etc/motd` -> Copied to `/etc/motd`
* `configs/overlay/usr/share/backgrounds/wallpaper.png` -> Copied to `/usr/share/backgrounds/wallpaper.png`
* `configs/overlay/etc/polkit-1/rules.d/50-custom.rules` -> Copied to `/etc/polkit-1/rules.d/50-custom.rules`

You can also pass external overlay directories on the CLI using `--include-dir /path/to/my-overlay`.

### B. Declarative Structured Copy (`configs/base_customizations.json` & `copy_files`)
For granular control over source, destination, file permissions, and ownership, use declarative `copy_files` arrays in JSON:

```json
{
  "base_copy_files": [
    {
      "source": "samba",
      "destination": "/etc/samba"
    },
    {
      "source": "scripts/my-helper.sh",
      "destination": "/usr/local/bin/my-helper.sh",
      "mode": "0755",
      "owner": "0:0"
    },
    {
      "source": "sudoers.d",
      "destination": "/etc/sudoers.d",
      "mode": "0440"
    }
  ]
}
```

* **Automatic Executable Bits**: Any file copied into `/usr/bin/`, `/usr/local/bin/`, `/etc/cron.*`, or ending in `.sh` automatically receives execution permissions (`0755`).
* **Automatic Sudoers Security**: Any file copied into `/etc/sudoers.d/` is automatically restricted to `0440` mode and owned by `root:root`.

### C. Automatic `/etc/skel` to `/home/<user>` Propagation
When copying configuration files or dotfiles to `/etc/skel/` (e.g. `skel/.config/xfce4/`), Void-Builder automatically propagates these files into the home directories of all created users (e.g. `/home/live/`, `/home/void/`) and assigns proper user ownership (`chown -R <user>:<user>`).

---

## 8. Presets & Edition Profiles (`configs/presets/`)

Presets define unified, all-in-one edition specifications that configure desktop environments, package bundle combinations, system defaults, services, and repositories simultaneously.

### Example: `configs/presets/rescue-sysadmin.json`

```json
{
  "name": "rescue-sysadmin",
  "description": "System Rescue, Forensics, Network Troubleshooting, and Disk Partitioning Environment",
  "boot_title": "Void Linux Rescue & SysAdmin",
  "desktop": "xfce",
  "package_profiles": [
    "desktop-essentials",
    "filesystems",
    "networking"
  ],
  "additional_packages": [
    "gparted",
    "testdisk",
    "ddrescue",
    "smartmontools",
    "wireshark",
    "nmap",
    "tcpdump",
    "iperf3",
    "chntpw",
    "htop",
    "glances",
    "tmux",
    "rsync"
  ],
  "customizations": {
    "hostname": "void-rescue",
    "services": [
      "sshd",
      "NetworkManager"
    ]
  }
}
```

---

## 9. Lifecycle Hooks Engine (`configs/hooks/`)

Lifecycle hooks allow executing custom shell scripts at four deterministic points during the build:

1. **`pre-install`**: Executed outside the chroot before XBPS installs packages.
2. **`post-install`**: Executed directly inside the chroot environment after package installation and service configuration. Ideal for generating custom version tags, modifying `/etc/os-release`, or cloning custom dotfiles.
3. **`pre-iso`**: Executed outside the chroot before SquashFS or disk image compression.
4. **`post-iso`**: Executed after the final image, tarball, and checksums are generated.

### Hook Example (`configs/hooks/post-install.example.sh`):

```bash
#!/bin/sh
# Hook executed inside the chroot
echo "=> Branding custom Void build..."
echo "Void-Builder Custom Workstation v1.0" > /etc/void-custom-release
chmod 0644 /etc/void-custom-release
```

---

## 10. Security Actions & Service Conflict Resolution

The system configurator (`SystemConfigurator`) automatically manages:
- **`RootPasswordAction`**: Ingests `--root-password <pass>` or `--lock-root` to secure administrative accounts.
- **`SSHKeyAction`**: Provisions authorized keys into `/root/.ssh/authorized_keys` and `/home/<live_user>/.ssh/authorized_keys` with strict permissions (`0700` directory, `0600` file).
- **Service Conflict Engine**: Automatically detects if `NetworkManager` is enabled and suppresses conflicting standalone services like `dhcpcd` to prevent race conditions during boot.

