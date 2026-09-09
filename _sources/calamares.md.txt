# Calamares Installer Integration

Void-Builder includes native pipeline support for building and injecting the **Calamares Graphical Installer** into live ISO images.

---

## Architecture of Calamares Pipeline

The template files for Calamares are stored under `custom_packages/calamares/`.

When building with Calamares integration:
1. `void-packages` repository is cloned or prepared under `workdir/void-packages`.
2. The local template from `custom_packages/calamares` is copied into `void-packages/srcpkgs/calamares`.
3. `xbps-src` compiles `calamares` for the target architecture.
4. The generated `.xbps` package and repository index remain under
   `workdir/void-packages/hostdir/binpkgs` (possibly in a subdirectory).
5. Subsequent ISO builds requesting `calamares` automatically discover this
   repository, checking for a package and index matching the target architecture.
6. Explicit `--repository` selections take priority, followed by configured custom
   repositories, the discovered Calamares repository, and official repositories.

The build workspace `workdir/<architecture>` is cleaned independently of
`workdir/void-packages`, so normal build cleanup preserves the compiled package.
Deleting `workdir/void-packages` removes it.

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

### Reuse an already compiled package

Select the installer profile in your usual build command:

```bash
sudo python3 cli.py x86_64 -d xfce --package-profile installer --mode real
```

To use a package repository stored elsewhere, pass its indexed directory explicitly:

```bash
sudo python3 cli.py x86_64 -d xfce --package-profile installer --mode real \
  --repository /path/to/binpkgs
```

`--with-calamares` runs the compilation step first; it is unnecessary when the
matching indexed package already exists in the default build directory.

## Offline repository

Add `--with-offline-repo` to include an indexed XBPS repository at `/repo` inside
the live system (and in disk images or exported rootfs tarballs). By default it
contains the build package selection and its dependencies. Use
`--offline-repo-packages git,vim` to request a smaller set with its dependencies.
The build downloads against an empty package database, includes locally compiled
packages, indexes the archives, and checks dependency resolution using only that
index before packaging the image. Download or indexing failures stop the build.
`/etc/xbps.d/00-offline-repository.conf` enables `/repo` in the generated system.

Example reusing the compiled installer:

```bash
sudo python3 cli.py x86_64 -d xfce --mode real \
  --package-profile installer --with-offline-repo
```
