import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from void_builder.core.offline_repository import build_offline_repository, OfflineRepositoryError
from void_builder.core.path_utils import resolve_from_project


@pytest.mark.parametrize('on_iso', [False, True])
def test_real_xbps_offline_repository_with_local_dependency(tmp_path, on_iso):
    tools = resolve_from_project('void_builder/tools/usr/bin')
    if not (tools / 'xbps-create.static').is_file():
        pytest.skip('Bundled XBPS tools unavailable')
    source = tmp_path / 'source'
    source.mkdir()
    payload = tmp_path / 'payload'
    payload.mkdir()
    (payload / 'data').write_text('fixture')
    env = dict(os.environ, XBPS_ARCH='x86_64')
    for name, deps in [('fixture-unrelated-1.0_1', []), ('fixture-dependency-1.0_1', []), ('fixture-installer-1.0_1', ['-D', 'fixture-dependency>=1.0_1'])]:
        for entry in payload.iterdir():
            entry.unlink()
        (payload / name).write_text('fixture')
        subprocess.run([str(tools / 'xbps-create.static'), '-A', 'x86_64', '-n', name,
                        '-s', 'Offline test package', *deps, str(payload)], cwd=source, env=env, check=True, capture_output=True)
    subprocess.run([str(tools / 'xbps-rindex.static'), '-a', *map(str, source.glob('*.xbps'))], env=env, check=True, capture_output=True)
    tc = SimpleNamespace(mode='real', xbps_install_static=tools / 'xbps-install.static', _setup_keys=lambda root: (root / 'var/db/xbps/keys').mkdir(parents=True))
    staging = tmp_path / 'iso-staging' if on_iso else None
    if on_iso:
        old_repo = tmp_path / 'rootfs/repo'
        old_repo.mkdir(parents=True)
        (old_repo / 'stale.xbps').touch()
        config = tmp_path / 'rootfs/etc/xbps.d/00-offline-repository.conf'
        config.parent.mkdir(parents=True)
        config.write_text('repository=/repo\n')
    destination = build_offline_repository(tc, 'x86_64', ['fixture-installer'], [str(source)], tmp_path / 'rootfs', tmp_path, staging)
    assert (destination / 'x86_64-repodata').is_file()
    assert len(list(destination.glob('*.xbps'))) == 2
    expected = '/run/initramfs/live/repo' if on_iso else '/repo'
    assert (tmp_path / 'rootfs/etc/xbps.d/00-offline-repository.conf').read_text() == f'repository={expected}\n'
    assert (destination / 'selected-packages.txt').read_text() == 'fixture-installer\n'
    assert len((destination / 'packages.txt').read_text().splitlines()) == 2
    if on_iso:
        assert destination == staging / 'repo'
        assert not (tmp_path / 'rootfs/repo').exists()


def test_download_failure_stops_build(tmp_path, monkeypatch):
    tc = SimpleNamespace(mode='real', xbps_install_static=Path('/fake/xbps-install.static'), _setup_keys=Mock())
    monkeypatch.setattr('void_builder.core.offline_repository.subprocess.run', Mock(return_value=SimpleNamespace(returncode=2, stdout='', stderr='Package missing')))
    with pytest.raises(OfflineRepositoryError, match='Package missing'):
        build_offline_repository(tc, 'x86_64', ['missing'], ['https://example.invalid'], tmp_path / 'rootfs', tmp_path)
    assert not (tmp_path / 'rootfs/etc/xbps.d/00-offline-repository.conf').exists()


def test_sync_failure_stops_before_dry_run(tmp_path, monkeypatch):
    tc = SimpleNamespace(mode='real', xbps_install_static=Path('/fake/xbps-install.static'), _setup_keys=Mock())
    run = Mock(return_value=SimpleNamespace(returncode=1, stdout='', stderr='Index download failed'))
    monkeypatch.setattr('void_builder.core.offline_repository.subprocess.run', run)
    with pytest.raises(OfflineRepositoryError, match='Index download failed'):
        build_offline_repository(tc, 'x86_64', ['testdisk'], ['https://example.invalid'], tmp_path / 'rootfs', tmp_path)
    run.assert_called_once()
    command = run.call_args.args[0]
    assert '-S' in command
    assert '-n' not in command
    assert 'testdisk' not in command


@pytest.mark.parametrize('output_format', ['iso', 'tarball'])
@pytest.mark.parametrize('enabled', [False, True])
def test_pipeline_embeds_offline_repository_before_finalization(tmp_path, output_format, enabled):
    from void_builder.core.config_loader import ConfigAssembler
    from void_builder.core.chroot_manager import ChrootManager
    from void_builder.core.iso_engine import ISOBuilder
    cfg = ConfigAssembler('configs').assemble('x86_64')
    cfg._data['with_offline_repo'] = enabled
    cfg._data['offline_repo_packages'] = ['testdisk']
    tc = SimpleNamespace(mode='mock', host_dir=tmp_path, xbps_install_static=tmp_path / 'xbps-install.static')
    tc.chroot_manager = ChrootManager(tmp_path / 'work/airootfs', tc, mode='mock', config=cfg)
    builder = ISOBuilder('x86_64', cfg, tc)
    result = builder.build(str(tmp_path / ('result.iso' if output_format == 'iso' else 'result.tar.xz')),
                           workdir=str(tmp_path / 'work'), output_format=output_format)
    assert Path(result).exists()
    parent = builder.engine.iso_staging if output_format == 'iso' else builder.engine.chroot_path
    assert (parent / 'repo/MOCK.txt').exists() == enabled
    if output_format == 'iso':
        assert not (builder.engine.chroot_path / 'repo').exists()


@pytest.mark.parametrize('arguments', [[], ['--offline-repo-packages', 'testdisk']])
def test_cli_does_not_enable_offline_repository_implicitly(monkeypatch, arguments):
    import cli
    factory = Mock()
    monkeypatch.setattr(cli, 'BuildOrchestrator', factory)
    monkeypatch.setattr('sys.argv', ['cli.py', *arguments])
    cli.main()
    assert factory.call_args.kwargs['with_offline_repo'] is False


def test_offline_selection_is_independent_and_overridable(tmp_path, monkeypatch):
    from void_builder.core.offline_repository import offline_package_selection
    selection = tmp_path / 'packages.txt'
    selection.write_text('# Optional tools\ntestdisk\nddrescue # recovery\ntestdisk\n')
    monkeypatch.setattr('void_builder.core.offline_repository.resolve_from_project', lambda _: selection)
    assert offline_package_selection({}) == ['testdisk', 'ddrescue']
    assert offline_package_selection({'offline_repo_packages': ['ethtool']}) == ['ethtool']
