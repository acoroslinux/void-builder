from pathlib import Path
import importlib.util
import os
import subprocess
from unittest.mock import Mock
import pytest


@pytest.mark.parametrize('cmdline,enabled', [
    ('root=/dev/sda1', False),
    ('root=UUID=installed quiet', False),
    ('rd.live.image=0 root=/dev/sda1', False),
    ('rd.live.image root=live:CDLABEL=VOID', True),
    ('root=live:CDLABEL=VOID_MODERN ro rd.overlay=1', True),
    ('root=live:CDLABEL=VOID_MODERN rd.live.ram', True),
])
def test_only_live_boot_grants_live_sudo(tmp_path, cmdline, enabled):
    cmdfile = tmp_path / 'cmdline'
    cmdfile.write_text(cmdline)
    script = Path('configs/custom_files/live-privileges/90-live-privileges.sh').read_text()
    script = script.replace('/etc/sudoers.d', str(tmp_path / 'sudoers.d')).replace('/proc/cmdline', str(cmdfile))
    script = script.replace('chown 0:0', f'chown {os.getuid()}:{os.getgid()}')
    script = 'id() { return 0; }\n' + script
    target = tmp_path / 'sudoers.d/90-live-session'
    target.parent.mkdir()
    target.write_text('stale rule')
    subprocess.run(['/bin/sh', '-c', script], check=True)
    assert target.exists() == enabled
    if enabled:
        assert target.read_text() == 'live ALL=(ALL:ALL) NOPASSWD: ALL\n'


def test_sudo_and_polkit_recognize_actual_boot_templates():
    import re
    sudo = Path('configs/custom_files/live-privileges/90-live-privileges.sh').read_text()
    polkit = Path('configs/custom_files/polkit-1/rules.d/49-nopasswd-calamares.rules').read_text()
    pattern = sudo.split("grep -Eq '", 1)[1].split("'", 1)[0]
    assert f'"{pattern}"' in polkit
    assert 'subject.user !== "live"' in polkit
    for template in ('grub.cfg.in', 'isolinux.cfg.in'):
        lines = Path('configs/boot/templates', template).read_text().splitlines()
        boot_lines = [line for line in lines if 'root=live:' in line]
        assert boot_lines
        assert all(re.search(pattern, line) for line in boot_lines)


def locale_module():
    spec = importlib.util.spec_from_file_location('void_locales', 'configs/custom_files/scripts/void-apply-locales.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selected_language_and_regional_formats_are_both_generated(tmp_path):
    default = tmp_path / 'etc/default'
    default.mkdir(parents=True)
    config = tmp_path / 'etc/locale.conf'
    config.write_text('LANG="pt_PT.UTF-8"\nLC_TIME=en_GB.UTF-8\n')
    supported = default / 'libc-locales'
    supported.write_text('#pt_PT.UTF-8 UTF-8\n#en_GB.UTF-8 UTF-8\n#de_DE.UTF-8 UTF-8\n')
    run = Mock()
    locale_module().apply_locales(tmp_path, run)
    assert supported.read_text().startswith('pt_PT.UTF-8 UTF-8\nen_GB.UTF-8 UTF-8\n')
    assert config.read_text() == (default / 'locale').read_text()
    run.assert_called_once_with(['xbps-reconfigure', '-f', 'glibc-locales'], check=True)


def test_unknown_locale_fails_instead_of_silent_fallback(tmp_path):
    default = tmp_path / 'etc/default'
    default.mkdir(parents=True)
    (tmp_path / 'etc/locale.conf').write_text('LANG=missing.UTF-8\n')
    (default / 'libc-locales').write_text('#pt_PT.UTF-8 UTF-8\n')
    with pytest.raises(ValueError, match='Unsupported locales'):
        locale_module().apply_locales(tmp_path, Mock())
