from pathlib import Path
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
    return engine, tmp_path / 'ext3fs.img'


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
