import os
import re
import shutil
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from void_builder.core.config_loader import Config
from void_builder.core.iso_engine import VoidEngine, ISOBuilderError


def test_ext3_population_preserves_contents_and_metadata(tmp_path):
    debugfs = shutil.which('debugfs') or '/usr/sbin/debugfs'
    if not Path(debugfs).is_file() or not Path('/usr/sbin/mkfs.ext3').is_file():
        pytest.skip('e2fsprogs unavailable')
    root = tmp_path / 'rootfs'
    (root / 'etc').mkdir(parents=True)
    file = root / 'etc/example'
    file.write_text('rootfs payload\n')
    file.chmod(0o640)
    os.link(file, root / 'etc/hardlink')
    (root / 'etc/symlink').symlink_to('example')
    (root / 'etc/shadow').write_text('fixture')
    (root / '.hidden').write_text('hidden file')
    os.setxattr(file, 'user.test', b'kept')
    image = tmp_path / 'ext3fs.img'
    with image.open('wb') as stream:
        stream.truncate(32 * 1024 * 1024)
    engine = VoidEngine('x86_64', Config({}), SimpleNamespace(mode='real'))
    engine.chroot_path = root
    engine._populate_ext3_image(image)

    def inspect(request):
        return subprocess.run([debugfs, '-R', request, str(image)], check=True, capture_output=True, text=True).stdout

    assert 'rootfs payload' in inspect('cat /etc/example')
    assert 'hidden file' in inspect('cat /.hidden')
    stat = inspect('stat /etc/example')
    assert '0640' in stat
    assert re.search(r'Inode: (\d+)', stat).group(1) == re.search(r'Inode: (\d+)', inspect('stat /etc/hardlink')).group(1)
    assert 'example' in inspect('stat /etc/symlink')
    assert '0600' in inspect('stat /etc/shadow')
    assert 'kept' in inspect('ea_list /etc/example')
    assert 'has_journal' in inspect('stats')


def test_population_error_is_reported(tmp_path, monkeypatch):
    engine = VoidEngine('x86_64', Config({}), SimpleNamespace(mode='real'))
    engine.chroot_path = tmp_path
    monkeypatch.setattr('shutil.which', lambda _: '/fake/mkfs.ext3')
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='Not enough space'))
    with pytest.raises(ISOBuilderError, match='Not enough space'):
        engine._populate_ext3_image(tmp_path / 'ext3fs.img')
