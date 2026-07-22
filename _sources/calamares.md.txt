# Calamares Installer Integration

Void-Builder includes native pipeline support for building and injecting the **Calamares Graphical Installer** into live ISO images.

---

## Architecture of Calamares Pipeline

The template files for Calamares are stored under `custom_packages/calamares/`.

When building with Calamares integration:
1. `void-packages` repository is cloned or prepared under `workdir/void-packages`.
2. The local template from `custom_packages/calamares` is copied into `void-packages/srcpkgs/calamares`.
3. `xbps-src` compiles `calamares` for the target architecture.
4. The generated `.xbps` binary package is stored in `custom_packages/`.
5. `xbps-rindex` indexes `custom_packages/` as a local XBPS repository.
6. The ISO build pipeline injects `custom_packages` at priority 0 so `xbps-install` installs the freshly compiled Calamares package into the live ISO environment.

---

## Build Commands

### Option A: Build Calamares Package Only

To compile the Calamares package for `x86_64` without generating an ISO:

```bash
python3 cli.py --build-calamares
```

### Option B: Build ISO with Calamares Included

To compile Calamares first and automatically build an ISO containing the installer:

```bash
sudo python3 cli.py x86_64 -d xfce --with-calamares --mode real
```
