from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from void_builder.core.chroot_manager import ChrootManager, ChrootError
from void_builder.core.config_loader import Config
from void_builder.core.iso_engine import ISOBuilder, VoidEngine


@pytest.mark.parametrize('output_format', ['iso', 'tarball'])
def test_unmount_after_chroot_work_before_export(tmp_path, monkeypatch, output_format):
    events = []
    manager = Mock()
    manager.umount.side_effect = lambda: events.append('unmount')
    tc = SimpleNamespace(mode='mock', chroot_manager=manager)
    builder = ISOBuilder('x86_64', Config({'with_offline_repo': True}), tc)
    engine = builder.engine
    engine.setup_workdir = Mock(return_value=tmp_path)
    engine.setup_chroot = Mock()
    engine.chroot_path = tmp_path / 'rootfs'
    engine.install_packages = lambda: events.append('install')
    engine.post_install_configure = lambda: events.append('configure')
    engine.build_bootloaders = lambda _: events.append('bootloaders')
    engine._package_plan = lambda: {'official': ['bash']}
    monkeypatch.setattr('void_builder.core.offline_repository.build_offline_repository', lambda *a: events.append('offline'))
    def export(*a, **kw):
        events.append('export')
        return str(tmp_path / 'artifact')
    engine.export_tarball = export
    engine.finalize_isofile = export
    builder.build(str(tmp_path / 'artifact'), output_format=output_format,
                  chroot_hook=lambda: events.append('hooks'))
    assert events == ['install', 'configure', 'hooks', 'offline', 'bootloaders', 'unmount', 'export']


def test_configuration_does_not_unmount_early(tmp_path, monkeypatch):
    manager = Mock()
    engine = VoidEngine('x86_64', Config({}), SimpleNamespace(chroot_manager=manager))
    engine.chroot_path = tmp_path
    monkeypatch.setattr('void_builder.core.iso_engine.SystemConfigurator', Mock())
    monkeypatch.setattr('void_builder.utils.lib.clean_qemu_user_binary', Mock())
    engine.post_install_configure()
    manager.umount.assert_not_called()


def test_failed_unmount_keeps_mounted_state(tmp_path, monkeypatch):
    manager = ChrootManager(tmp_path, Mock(), mode='real')
    manager._mounted = True
    monkeypatch.setattr('os.geteuid', lambda: 0)
    monkeypatch.setattr('void_builder.utils.lib.umount_pseudofs', lambda _: False)
    with pytest.raises(ChrootError, match='Failed to unmount'):
        manager.umount()
    assert manager._mounted
