from pathlib import Path
import subprocess

import yaml


SCRIPT = Path('configs/custom_files/scripts/void-installed-setup.sh')


def test_calamares_command_does_not_expand_shell_variables():
    config = yaml.safe_load(Path('configs/custom_files/calamares/modules/shellprocess-voidsetup.conf').read_text())
    assert config['dontChroot'] is False
    assert config['script'] == [{'command': '/bin/sh /usr/local/bin/void-installed-setup.sh'}]
    subprocess.run(['sh', '-n', str(SCRIPT)], check=True)


def test_target_setup_expands_own_variables_and_removes_live_rules(tmp_path):
    for directory in ('etc/sv/dbus', 'etc/sudoers.d', 'usr/bin', 'usr/local/bin'):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / 'etc/hostname').write_text('installed-test\n')
    for name in ('90-live-session', '99-live-user', '10-wheel'):
        (tmp_path / 'etc/sudoers.d' / name).write_text('live rule')
    # Stub expensive target tools; run shell expansion and file setup for real.
    for name in ('usr/bin/xbps-reconfigure', 'usr/bin/python3', 'usr/local/bin/void-fix-auth-permissions.sh'):
        tool = tmp_path / name
        tool.write_text('#!/bin/sh\nexit 0\n')
        tool.chmod(0o755)
    command = SCRIPT.read_text().replace('/etc/', str(tmp_path / 'etc') + '/')
    command = command.replace('/usr/', str(tmp_path / 'usr') + '/')
    subprocess.run(['/bin/sh', '-c', command], check=True)
    assert 'installed-test.localdomain installed-test' in (tmp_path / 'etc/hosts').read_text()
    assert (tmp_path / 'etc/runit/runsvdir/default/dbus').is_symlink()
    assert not (tmp_path / 'etc/runit/runsvdir/default/tlp').exists()
    assert not (tmp_path / 'etc/sudoers.d/90-live-session').exists()
    assert (tmp_path / 'etc/sudoers.d/10-installed-wheel').read_text() == '%wheel ALL=(ALL:ALL) ALL\n'
