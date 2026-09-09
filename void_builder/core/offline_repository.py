"""Build an independently usable XBPS repository inside the image rootfs."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from void_builder.utils.lib import map_xbps_arch


class OfflineRepositoryError(RuntimeError):
    pass


def build_offline_repository(toolchain, arch, packages, repositories, rootfs, workdir):
    destination = Path(rootfs) / 'repo'
    destination.mkdir(parents=True, exist_ok=True)
    if getattr(toolchain, 'mode', 'real') == 'mock':
        (destination / 'MOCK.txt').write_text('Offline repository simulation; no packages downloaded.\n')
        return destination
    if not packages:
        raise OfflineRepositoryError('No packages selected for the offline repository')
    if not repositories:
        raise OfflineRepositoryError('No source repositories available for offline packages')

    arch = map_xbps_arch(arch)
    env = os.environ.copy()
    env['XBPS_ARCH'] = arch
    installer = Path(toolchain.xbps_install_static)
    indexer = installer.with_name('xbps-rindex.static')

    def run(command):
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        if result.returncode:
            raise OfflineRepositoryError(f"Offline repository command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")

    # Resolve against an empty package database, so installed rootfs packages do
    # not suppress the download of dependencies required by an offline install.
    with tempfile.TemporaryDirectory(prefix='offline-', dir=workdir) as temp:
        resolver = Path(temp) / 'root'
        resolver.mkdir()
        toolchain._setup_keys(resolver)
        cache = Path(temp) / 'packages'
        cache.mkdir()
        # XBPS can use local archives in place without putting them in its cache.
        for repo in repositories:
            parsed = urlparse(repo)
            if parsed.scheme not in ('', 'file'):
                continue
            source = Path(unquote(parsed.path))
            for package_arch in (arch, 'noarch'):
                for package in source.glob(f'*.{package_arch}.xbps'):
                    target = cache / package.name
                    if not target.exists():
                        shutil.copy2(package, target)

        cmd = [str(installer), '-S', '-D', '-y', '-i', '-r', str(resolver), '-c', str(cache)]
        for repo in repositories:
            cmd.extend(['-R', repo])
        run(cmd + list(dict.fromkeys(packages)))
        archives = sorted(cache.glob('*.xbps'))
        if not archives:
            raise OfflineRepositoryError('XBPS did not produce any offline package archives')
        run([str(indexer), '-a', *map(str, archives)])
        if not (cache / f'{arch}-repodata').is_file():
            raise OfflineRepositoryError(f'Offline index missing for {arch}')
        # Check the complete dependency closure using only the new local index.
        run([str(installer), '-n', '-y', '-i', '-r', str(resolver), '-R', str(cache), *packages])
        for old in destination.glob('*.xbps'):
            old.unlink()
        for old in destination.glob('*-repodata'):
            old.unlink()
        shutil.copytree(cache, destination, dirs_exist_ok=True)

    config = Path(rootfs) / 'etc/xbps.d/00-offline-repository.conf'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('repository=/repo\n')
    return destination
