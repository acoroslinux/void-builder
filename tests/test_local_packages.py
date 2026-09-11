from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import shutil

import pytest

from void_builder.core.chroot_manager import ChrootManager
from void_builder.core.local_packages import calamares_repositories, persist_calamares_repository


def repository(root, arch='x86_64'):
    root.mkdir(parents=True)
    (root / f'calamares-3.4.2_1.{arch}.xbps').touch()
    (root / f'{arch}-repodata').touch()
    return str(root.resolve())


def test_finds_native_and_nested_matching_repositories(tmp_path):
    native = repository(tmp_path / 'binpkgs')
    arm = repository(tmp_path / 'binpkgs/aarch64', 'aarch64')
    assert calamares_repositories('x86_64', tmp_path / 'binpkgs') == [native]
    assert calamares_repositories('rpi-aarch64', tmp_path / 'binpkgs') == [arm]
    assert calamares_repositories('x86_64-musl', tmp_path / 'binpkgs') == []


def test_unindexed_package_is_not_advertised(tmp_path):
    (tmp_path / 'calamares-3.4.2_1.x86_64.xbps').touch()
    assert calamares_repositories('x86_64', tmp_path) == []


def test_persistent_repository_survives_workspace_removal(tmp_path, monkeypatch):
    source = tmp_path / 'workdir/void-packages/hostdir/binpkgs'
    repository(source)
    (source / 'calamares-3.4.2_1.x86_64.xbps').write_bytes(b'compiled package')
    (source / 'dependency-1.0_1.noarch.xbps').touch()
    (source / 'other-1.0_1.aarch64.xbps').touch()
    destination = tmp_path / 'custom_packages'
    monkeypatch.setattr('void_builder.core.local_packages.resolve_from_project', lambda path: tmp_path / path)
    def index(cmd, **kwargs):
        assert kwargs['env']['XBPS_ARCH'] == 'x86_64'
        assert cmd[:2] == ['/tools/xbps-rindex.static', '-a']
        assert all(str(destination) in path for path in cmd[2:])
        (destination / 'x86_64-repodata').touch()
    monkeypatch.setattr('void_builder.core.local_packages.subprocess.run', index)
    assert persist_calamares_repository('x86_64', source, Path('/tools/xbps-rindex.static')) == destination
    shutil.rmtree(tmp_path / 'workdir')
    assert calamares_repositories('x86_64') == [str(destination)]
    assert (destination / 'calamares-3.4.2_1.x86_64.xbps').read_bytes() == b'compiled package'
    assert (destination / 'dependency-1.0_1.noarch.xbps').exists()
    assert not (destination / 'other-1.0_1.aarch64.xbps').exists()


def test_persistent_repository_requires_successful_index(tmp_path, monkeypatch):
    source = tmp_path / 'binpkgs'
    repository(source)
    monkeypatch.setattr('void_builder.core.local_packages.resolve_from_project', lambda _: tmp_path / 'custom_packages')
    monkeypatch.setattr('void_builder.core.local_packages.subprocess.run', Mock())
    with pytest.raises(RuntimeError, match='not indexed'):
        persist_calamares_repository('x86_64', source, Path('/tools/xbps-rindex.static'))


@pytest.mark.parametrize('packages', [['calamares'], ['bash']])
def test_xbps_receives_local_repository_only_when_needed(tmp_path, monkeypatch, packages):
    local = repository(tmp_path / 'binpkgs')
    monkeypatch.setattr('void_builder.core.local_packages.resolve_from_project', lambda _: tmp_path / 'binpkgs')
    monkeypatch.setattr('void_builder.utils.lib.is_target_native', lambda _: True)
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr('void_builder.core.chroot_manager.subprocess.run', run)
    official = 'https://repo-default.voidlinux.org/current'
    explicit = str(tmp_path / 'explicit-repo')
    config = {'system': {'xbps_cache': str(tmp_path / 'cache')},
              'custom_repositories': [explicit], 'repositories': [official]}
    tc = SimpleNamespace(xbps_install_static=Path('/fake/xbps-install.static'), _setup_keys=Mock(), retries=1)
    manager = ChrootManager(tmp_path / 'rootfs', tc, mode='real', config=config)
    manager.install_packages({'official': packages}, repos=[official])
    cmd = run.call_args.args[0]
    repos = [cmd[idx + 1] for idx, arg in enumerate(cmd) if arg == '-R']
    assert repos == ([explicit, local, official] if 'calamares' in packages else [explicit, official])


def test_cli_forwards_offline_flags(monkeypatch):
    import cli
    orchestrator = Mock()
    factory = Mock(return_value=orchestrator)
    monkeypatch.setattr(cli, 'BuildOrchestrator', factory)
    monkeypatch.setattr('sys.argv', ['cli.py', '--with-offline-repo', '--offline-repo-packages', 'git, vim,,'])
    cli.main()
    assert factory.call_args.kwargs['with_offline_repo'] is True
    assert factory.call_args.kwargs['offline_repo_packages'] == ['git', 'vim']
