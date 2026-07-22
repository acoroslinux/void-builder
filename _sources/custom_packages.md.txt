# Custom Packages & Local XBPS Repositories

This document explains how to include custom local `.xbps` binary packages into Void-Builder images.

---

## The `custom_packages/` Directory

Void-Builder automatically monitors the `custom_packages/` directory at the project root:

```text
/repos/frs/projects/pep-void/void-builder/custom_packages/
├── calamares/               # Source template for Calamares package
├── my-package-1.0_1.x86_64.xbps
└── my-tool-2.1_1.x86_64.xbps
```

---

## Automatic Repository Indexing

When `VoidEngine.install_packages()` runs:

1. Checks if `custom_packages/` contains any `.xbps` package files.
2. If found, automatically executes `xbps-rindex -a custom_packages/*.xbps` to build `x86_64-repodata` (or target architecture index).
3. Prepends `custom_packages/` to the repository priority list at position `0`.
4. Allows `xbps-install` to resolve and install your custom packages during chroot provisioning.

---

## Creating Custom Packages with `xbps-src`

If you are developing custom applications or modified Void packages:

1. Clone `void-packages`:
   ```bash
   git clone https://github.com/void-linux/void-packages.git
   cd void-packages
   ./xbps-src binary-bootstrap
   ```

2. Create package template in `srcpkgs/<my-package>/template`.
3. Compile package:
   ```bash
   ./xbps-src pkg <my-package>
   ```

4. Copy compiled `.xbps` file into `custom_packages/`:
   ```bash
   cp hostdir/binpkgs/<my-package>-*.xbps /path/to/void-builder/custom_packages/
   ```

5. Run build:
   ```bash
   sudo python3 cli.py x86_64 -p my-package --mode real
   ```
