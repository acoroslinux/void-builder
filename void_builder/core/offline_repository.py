"""Build an independently usable XBPS repository on the installation media."""
import os
import threading
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from void_builder.utils.lib import map_xbps_arch
from void_builder.utils.logger import setup_logger
from void_builder.core.path_utils import resolve_from_project

logger = setup_logger("OfflineRepository")


class OfflineRepositoryError(RuntimeError):
    pass


def offline_package_selection(config):
    """Keep optional offline packages independent from the live package plan."""
    explicit = config.get('offline_repo_packages')
    if explicit:
        return list(dict.fromkeys(explicit))
    path = resolve_from_project('configs/offline-packages.txt')
    return list(dict.fromkeys(
        line.split('#', 1)[0].strip() for line in path.read_text().splitlines()
        if line.split('#', 1)[0].strip()
    ))


def build_offline_repository(toolchain, arch, packages, repositories, rootfs, workdir, iso_staging=None):
    logger.info(f"[Offline] Preparing repository: {len(packages)} selected packages plus dependencies")
    destination = Path(iso_staging if iso_staging is not None else rootfs) / 'repo'
    destination.mkdir(parents=True, exist_ok=True)
    packages = list(dict.fromkeys(packages))
    destination.joinpath('selected-packages.txt').write_text('\n'.join(packages) + '\n')
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
        started = time.monotonic()
        finished = threading.Event()

        def report_progress():
            while not finished.wait(30):
                logger.info(f"[Offline] XBPS still running ({time.monotonic() - started:.0f}s elapsed)")

        reporter = threading.Thread(target=report_progress, daemon=True)
        reporter.start()
        try:
            result = subprocess.run(command, env=env, text=True, capture_output=True)
        finally:
            finished.set()
            reporter.join()
        logger.info(f"[Offline] XBPS finished in {time.monotonic() - started:.1f}s (exit {result.returncode})")
        if result.returncode:
            raise OfflineRepositoryError(f"Offline repository command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
        return result.stdout

    # Resolve against an empty package database, so installed rootfs packages do
    # not suppress the download of dependencies required by an offline install.
    with tempfile.TemporaryDirectory(prefix='offline-', dir=workdir) as temp:
        resolver = Path(temp) / 'root'
        resolver.mkdir()
        toolchain._setup_keys(resolver)
        cache = Path(temp) / 'packages'
        cache.mkdir()
        cmd = [str(installer), '-y', '-i', '-r', str(resolver), '-c', str(cache)]
        for repo in repositories:
            cmd.extend(['-R', repo])
        # Resolve first so unrelated archives in custom repositories are not
        # bundled merely because they share the same source directory.
        # Dry-run does not persist remote indexes, even with -S. Populate the
        # fresh resolver first, then reuse those indexes for plan and download.
        logger.info("[Offline] Synchronizing repository indexes...")
        run(cmd + ['-S'])
        plan = run(cmd + ['-n', *packages])
        required_archives = set()
        for line in plan.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1] in ('install', 'update', 'reinstall', 'downgrade'):
                required_archives.add(f'{fields[0]}.{fields[2]}.xbps')
        if not required_archives:
            raise OfflineRepositoryError('XBPS returned an empty offline package plan')
        # XBPS can use local archives in place without putting them in its cache.
        for repo in repositories:
            parsed = urlparse(repo)
            if parsed.scheme not in ('', 'file'):
                continue
            source = Path(unquote(parsed.path))
            for package_arch in (arch, 'noarch'):
                for package in source.glob(f'*.{package_arch}.xbps'):
                    if package.name not in required_archives:
                        continue
                    target = cache / package.name
                    if not target.exists():
                        shutil.copy2(package, target)

        logger.info("[Offline] Downloading packages and verifying integrity...")
        run(cmd + ['-D', *packages])
        archives = sorted(cache.glob('*.xbps'))
        if not archives:
            raise OfflineRepositoryError('XBPS did not produce any offline package archives')
        logger.info(f"[Offline] Indexing {len(archives)} package archives...")
        run([str(indexer), '-a', *map(str, archives)])
        if not (cache / f'{arch}-repodata').is_file():
            raise OfflineRepositoryError(f'Offline index missing for {arch}')
        # Check the complete dependency closure using only the new local index.
        logger.info("[Offline] Checking dependency resolution using only the local repository...")
        run([str(installer), '-n', '-y', '-i', '-r', str(resolver), '-R', str(cache), *packages])
        for old in destination.glob('*.xbps'):
            old.unlink()
        for old in destination.glob('*-repodata'):
            old.unlink()
        logger.info(f"[Offline] Copying package archives into {destination}...")
        shutil.copytree(cache, destination, dirs_exist_ok=True)
        destination.joinpath('packages.txt').write_text('\n'.join(p.name for p in archives) + '\n')

    config = Path(rootfs) / 'etc/xbps.d/00-offline-repository.conf'
    # Migrate the repository generated by older builds when reusing a rootfs.
    old_repo = Path(rootfs) / 'repo'
    if (iso_staging is not None and config.is_file()
            and config.read_text().strip() == 'repository=/repo'
            and old_repo.is_dir() and not old_repo.is_symlink()):
        shutil.rmtree(old_repo)
    config.parent.mkdir(parents=True, exist_ok=True)
    live_repository = '/run/initramfs/live/repo' if iso_staging is not None else '/repo'
    config.write_text(f'repository={live_repository}\n')
    logger.info(f"[Offline] Repository ready: {destination}")
    return destination
