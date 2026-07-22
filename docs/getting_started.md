# Getting Started

This guide explains how to install dependencies, prepare your system, and execute your first build with **Void-Builder**.

---

## Requirements

### Host Operating System
- **Recommended**: Void Linux (x86_64 or aarch64)
- **Supported**: Any standard Linux distribution (Debian/Ubuntu, Arch, Fedora, openSUSE) with Python 3.10+ installed.

### Dependencies
- Python 3.10+
- `xbps` static tools (automatically downloaded if missing)
- `qemu-user-static` and `binfmt-support` (for cross-architecture builds)
- `xorriso`, `mtools`, `syslinux`, `dracut`, `squashfs-tools` (for real ISO finalization)

---

## Host Environment Setup

When building images for foreign architectures (for example, building `aarch64` or `rpi-armv7l` on an `x86_64` host machine), you must set up QEMU user-mode emulators and `binfmt_misc`.

A helper script is provided at the root of the repository:

```bash
sudo ./setup_host_build_env.sh
```

What `setup_host_build_env.sh` does:
1. Detects your host distribution package manager (`apt`, `pacman`, `dnf`, `zypper`, `xbps`).
2. Installs `qemu-user-static` / `qemu-user` emulators and `binfmt-support`.
3. Loads the `binfmt_misc` kernel module and mounts `/proc/sys/fs/binfmt_misc`.
4. Registers foreign architecture binaries so foreign chroots execute seamlessly.

---

## Quick Verification

Before running a real build, verify that your python environment and configurations are healthy:

```bash
python3 cli.py --check
```

Outputs:
```text
🔍 Validating configuration for target architecture 'x86_64'...
✅ Configuration is VALID!
Summary:
  - Target Architecture: x86_64
  - Desktop Profile:     base
  - Total Packages:      136
  - Enabled Services:    dbus, NetworkManager, polkitd, bluetoothd, cupsd, avahi-daemon, sshd, chronyd, alsa, acpid, elogind, wpa_supplicant
```
