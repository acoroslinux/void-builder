"""Locate indexed packages produced by the local xbps-src build."""
from pathlib import Path
import os
import shutil
import subprocess
from typing import List, Optional

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.lib import map_xbps_arch


def calamares_repositories(arch: str, binpkgs: Optional[Path] = None) -> List[str]:
    """Return repositories containing Calamares for the requested architecture."""
    roots = [binpkgs] if binpkgs is not None else [
        resolve_from_project("custom_packages"),
        resolve_from_project("workdir/void-packages/hostdir/binpkgs"),
    ]
    canonical_arch = map_xbps_arch(arch)
    repositories = []
    for root in roots:
        candidates = sorted({p.parent for p in root.rglob(f"calamares-[0-9]*.{canonical_arch}.xbps")})
        for path in candidates:
            resolved = str(path.resolve())
            if (path / f"{canonical_arch}-repodata").is_file() and resolved not in repositories:
                repositories.append(resolved)
    return repositories


def persist_calamares_repository(arch: str, binpkgs: Path, rindex: Path) -> Path:
    """Publish locally built packages outside the disposable build workspace."""
    sources = calamares_repositories(arch, binpkgs)
    if not sources:
        raise RuntimeError(f"No indexed Calamares package found for {arch} in {binpkgs}")
    destination = resolve_from_project("custom_packages")
    destination.mkdir(parents=True, exist_ok=True)
    canonical_arch = map_xbps_arch(arch)
    archives = set()
    for source in sources:
        for package_arch in (canonical_arch, "noarch"):
            for package in Path(source).glob(f"*.{package_arch}.xbps"):
                target = destination / package.name
                if package.resolve() != target.resolve():
                    shutil.copy2(package, target)
                archives.add(str(target))
    env = os.environ.copy()
    env["XBPS_ARCH"] = canonical_arch
    subprocess.run([str(rindex), "-a", *sorted(archives)], env=env, check=True)
    if not calamares_repositories(arch, destination):
        raise RuntimeError(f"Persistent Calamares repository was not indexed at {destination}")
    return destination
