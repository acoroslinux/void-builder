from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from void_builder.core.config_loader import Config
from void_builder.core.iso_engine import VoidEngine, ISOBuilderError


@pytest.fixture
def loop_build(tmp_path, monkeypatch):
    engine = VoidEngine('x86_64', Config({}), SimpleNamespace(mode='real'))
    engine.workdir = tmp_path
    engine.chroot_path = tmp_path / 'rootfs'
    engine.chroot_path.mkdir()
    monkeypatch.setattr('os.geteuid', lambda: 0)
    monkeypatch.setattr('shutil.which', lambda _: None)
    return engine, tmp_path / 'rootfs.img'


def test_void_mklive_loop_sequence(loop_build, monkeypatch):
    engine, image = loop_build
    commands = []
    def run(cmd, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr('subprocess.run', run)
    engine._populate_ext3_image(image)
    assert [cmd[0] for cmd in commands] == ['mkfs.ext3', 'mount', 'cp', 'umount']
    assert commands[0] == ['mkfs.ext3', '-F', '-m', '1', str(image)]
    assert commands[1][1:3] == ['-o', 'loop']
    assert commands[2][1:3] == ['-a', f'{engine.chroot_path}/.']
    assert commands[3][1] == '-f'
    assert not Path(commands[1][-1]).exists()


@pytest.mark.parametrize('failure', ['mount', 'cp', 'umount'])
def test_loop_failures_stop_and_clean_safely(loop_build, monkeypatch, failure):
    engine, image = loop_build
    commands = []
    def run(cmd, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=32 if cmd[0] == failure else 0,
                               stdout='', stderr=f'{failure} failed')
    monkeypatch.setattr('subprocess.run', run)
    with pytest.raises(ISOBuilderError, match=f'{failure} failed'):
        engine._populate_ext3_image(image)
    mountpoint = Path(next(cmd[-1] for cmd in commands if cmd[0] == 'mount'))
    if failure == 'mount':
        assert not any(cmd[0] in ('cp', 'umount') for cmd in commands)
        assert not mountpoint.exists()
    elif failure == 'cp':
        assert commands[-1][0] == 'umount'
        assert not mountpoint.exists()
    else:
        assert mountpoint.exists()  # Never recursively delete a still-mounted tree.


@pytest.mark.skipif(not shutil.which('mksquashfs') or not shutil.which('unsquashfs'),
                    reason='SquashFS tools required')
@pytest.mark.parametrize('existing_image', [False, True])
def test_squashfs_contains_dracut_rootfs_path(tmp_path, monkeypatch, existing_image):
    engine = VoidEngine('x86_64', Config({}), SimpleNamespace(mode='real'))
    engine.workdir = tmp_path
    engine.chroot_path = tmp_path / 'rootfs'
    engine.chroot_path.mkdir()
    engine.iso_staging = tmp_path / 'iso-staging'
    squashfs = engine.iso_staging / 'LiveOS' / 'squashfs.img'
    if existing_image:
        squashfs.parent.mkdir(parents=True)
        squashfs.write_bytes(b'stale image from an earlier build')
        squashfs.chmod(0o444)

    # Exercise real archive creation; loop population is tested separately.
    payload = b'current root filesystem payload'
    monkeypatch.setattr(engine, '_populate_ext3_image', lambda image: image.write_bytes(payload))
    monkeypatch.setattr('os.cpu_count', lambda: 1)
    engine._create_squashfs()

    extracted = subprocess.run(
        ['unsquashfs', '-cat', str(squashfs), 'LiveOS/rootfs.img'],
        check=True, capture_output=True,
    )
    assert extracted.stdout == payload
    listing = subprocess.run(
        ['unsquashfs', '-ll', str(squashfs)], check=True, capture_output=True, text=True,
    ).stdout
    assert 'LiveOS/rootfs.img' in listing
    assert 'ext3fs.img' not in listing
