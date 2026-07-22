# Getting Started & Total Build Isolation

Welcome to the setup and getting started guide for **Void-Builder**. This document details the zero-dependency, self-contained build architecture of Void-Builder, system requirements, and step-by-step build walkthroughs.

---

## 1. Zero Host Dependency & Total Isolation Architecture

Unlike traditional ISO building tools that require installing numerous host system packages (such as `xbps-install`, `qemu-user-static`, or `dracut` on the host machine), **Void-Builder implements complete build isolation**:

### How Total Isolation Works:
1. **Self-Contained Static Binaries**: On initial run, `ToolchainManager` automatically downloads isolated static binaries (`xbps-install.static` and `proot`) directly into the local `void_builder/tools/` directory.
2. **No Host Package Installation Needed**: You do **NOT** need to install any building tools, package managers, or chroot utilities via `apt`, `pacman`, `dnf`, `zypper`, or `xbps-install` on your host OS.
3. **Isolated Chroot Execution (`proot`)**: Chroot management and cross-architecture command executions are handled in user-space via `proot` and isolated pseudo-filesystem mounts.
4. **Host Distribution Agnostic**: Void-Builder runs identically on Void Linux, Debian, Ubuntu, Arch Linux, Fedora, openSUSE, Alpine, or any other Linux distribution with Python 3.10+ installed.

---

## 2. Requirements

### Host Requirements
- **Python**: Python 3.10 or higher.
- **Disk Space**: 10 GB free space on a local Linux filesystem (EXT4, Btrfs, XFS).
- **RAM**: 4 GB minimum.

---

## 3. Automatic Static Toolchain Resolution

When `ToolchainManager.setup()` executes, it automatically manages the toolchain:

```text
void_builder/tools/
├── proot                              # User-space chroot/emulation binary
└── usr/
    └── bin/
        ├── xbps-install.static        # Static XBPS installer binary
        ├── xbps-rindex.static         # Static XBPS repository indexer
        └── xbps-query.static          # Static XBPS query tool
```

If these static tools are missing or if `--update-toolchain` is specified, Void-Builder fetches the latest verified static releases directly from official mirrors into `void_builder/tools/`.

---

## 4. Cross-Architecture Host Helper (Optional)

When cross-building for foreign CPU architectures (e.g. building an `aarch64` or `rpi` image on an `x86_64` host), the helper script `setup_host_build_env.sh` can optionally configure kernel `binfmt_misc` user-mode emulators:

```bash
sudo ./setup_host_build_env.sh
```

---

## 5. Verification & First Build Walkthrough

### Step 1: Configuration Validation
Audit all JSON configuration profiles and dynamic package rules without building:

```bash
python3 cli.py --check
```

Outputs:
```text
🔍 Validating configuration for target architecture 'x86_64'...
2026-07-22 11:40:00 - ConfigLoader - INFO - Starting configuration assembly for x86_64...
2026-07-22 11:40:00 - ConfigLoader - INFO - Applied dynamic package rules from package_rules.json successfully.
2026-07-22 11:40:00 - ConfigLoader - INFO - Configuration assembly completed successfully.
✅ Configuration is VALID!
Summary:
  - Target Architecture: x86_64
  - Desktop Profile:     base
  - Total Packages:      136
  - Enabled Services:    dbus, NetworkManager, polkitd, bluetoothd, cupsd, avahi-daemon, sshd, chronyd, alsa, acpid, elogind, wpa_supplicant
```

### Step 2: Non-Root Simulation (Mock Mode)
Simulate building an x86_64 ISO with XFCE desktop environment:

```bash
python3 cli.py x86_64 -d xfce --mode mock
```

This verifies the build tree, packages list, and bootloader configuration without needing root privileges.

### Step 3: Production Real ISO Build
Execute a production build:

```bash
sudo python3 cli.py x86_64 -d xfce --mode real
```
