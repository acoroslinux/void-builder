# Dynamic Package Rules & Resolution

This document explains the dynamic package matching engine in **Void-Builder**, defined in `configs/package_rules.json`.

---

## Overview of Package Rules Engine

Instead of hardcoding architecture-specific or desktop-specific packages into Python logic, Void-Builder uses `package_rules.json` to dynamically inject packages into the official package list based on three criteria:

1. **Architecture Rules**: Matches target architecture strings (`x86_64`, `i686`, `aarch64`, `armv7l`).
2. **Platform Rules**: Matches specific SBC hardware platforms (`asahi`, `pinebookpro`, `x13s`).
3. **Desktop Rules**: Matches common desktop utilities (`pipewire`, `polkit`, `dbus-x11`) and specific desktop environments (`gnome`, `kde`, `xfce`, `sway`).

---

## File Structure of `package_rules.json`

```json
{
  "_comment": "Dynamic package injection rules based on architecture, platform, and desktop choices.",
  "architecture_packages": {
    "x86_64": [
      "grub-x86_64-efi",
      "syslinux",
      "qemu-firmware",
      "sof-firmware",
      "xf86-video-intel",
      "xf86-video-amdgpu",
      "xf86-video-ati",
      "xf86-video-nouveau",
      "xf86-video-vesa"
    ],
    "i686": [
      "grub-i386-efi",
      "syslinux",
      "xf86-video-intel",
      "xf86-video-vesa"
    ],
    "aarch64": [
      "grub-arm64-efi",
      "qemu-firmware"
    ],
    "rpi": [
      "rpi-base",
      "rpi-kernel"
    ]
  },
  "platform_packages": {
    "pinebookpro": [
      "pinebookpro-base",
      "pinebookpro-kernel",
      "pinebookpro-uboot"
    ],
    "asahi": [
      "asahi-base",
      "asahi-scripts",
      "linux-asahi",
      "mesa-asahi-dri",
      "grub-arm64-efi"
    ]
  },
  "desktop_packages": {
    "common": [
      "pipewire",
      "alsa-pipewire",
      "wireplumber",
      "dbus",
      "polkit",
      "elogind"
    ],
    "gnome": [
      "gnome-core",
      "gdm"
    ],
    "kde": [
      "kde5",
      "sddm"
    ],
    "xfce": [
      "xfce4",
      "lightdm",
      "lightdm-gtk-greeter"
    ]
  }
}
```

---

## Deduplication & Evaluation Order

When `ConfigAssembler.assemble()` runs:

1. **Global Base Packages**: Loaded from `global_build.json` (`package_sources.official`).
2. **Architecture Configuration**: Merged from `configs/architectures/<arch>.json`.
3. **Desktop Configuration**: Merged from `configs/desktops/<desktop>.json`.
4. **Dynamic Rule Matching**: `package_rules.json` matches keys against `target_arch`, `platforms`, and `target_desktop`.
5. **Deduplication**: Packages are deduplicated while preserving declaration order so critical base dependencies are processed first.
