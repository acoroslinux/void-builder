"""Locate indexed packages produced by the local xbps-src build."""
from pathlib import Path
from typing import List, Optional

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.lib import map_xbps_arch


def calamares_repositories(arch: str, binpkgs: Optional[Path] = None) -> List[str]:
    """Return repositories containing Calamares for the requested architecture."""
    root = binpkgs if binpkgs is not None else resolve_from_project("workdir/void-packages/hostdir/binpkgs")
    canonical_arch = map_xbps_arch(arch)
    candidates = sorted({p.parent for p in root.rglob(f"calamares-[0-9]*.{canonical_arch}.xbps")})
    return [str(path.resolve()) for path in candidates if (path / f"{canonical_arch}-repodata").is_file()]
