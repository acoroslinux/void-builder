import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from void_builder.core.customizer import SecurityPermissionsAction


def security_root(tmp_path):
    def run(command):
        command = command.replace('/etc/', str(tmp_path / 'etc') + '/')
        command = command.replace('/usr/', str(tmp_path / 'usr') + '/')
        command = command.replace('chown 0:0', f'chown {os.getuid()}:{os.getgid()}')
        subprocess.run(['/bin/sh', '-c', command], check=True, capture_output=True)
    return SimpleNamespace(mode='real', run_command=run)


def test_permissions_preserve_traversal_and_private_pam_data(tmp_path):
    expected = {'etc/passwd': 0o644, 'etc/group': 0o644, 'etc/shadow': 0o600,
                'etc/gshadow': 0o600, 'etc/shadow-': 0o600,
                'etc/pam.d/login': 0o644, 'etc/pam.d/nested/service': 0o644,
                'etc/security/limits.d/custom.conf': 0o644,
                'etc/security/opasswd': 0o600, 'etc/sudoers': 0o440,
                'etc/sudoers.d/live': 0o440, 'usr/bin/passwd': 0o4755,
                'usr/lib/polkit-1/polkit-agent-helper-1': 0o4755}
    for name in expected:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
        file.chmod(0o666)
    secret = tmp_path / 'etc/security/private-key'
    secret.touch()
    secret.chmod(0o600)
    SecurityPermissionsAction().execute(security_root(tmp_path), tmp_path)
    for name, mode in expected.items():
        assert stat.S_IMODE((tmp_path / name).stat().st_mode) == mode
    assert stat.S_IMODE((tmp_path / 'etc/security/limits.d').stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / 'etc/pam.d/nested').stat().st_mode) == 0o755
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600


def test_missing_shadow_stops_security_action(tmp_path):
    (tmp_path / 'etc').mkdir()
    (tmp_path / 'etc/passwd').touch()
    (tmp_path / 'etc/group').touch()
    with pytest.raises(subprocess.CalledProcessError):
        SecurityPermissionsAction().execute(security_root(tmp_path), tmp_path)


def test_lightdm_separates_password_and_autologin_pam(tmp_path, monkeypatch):
    from void_builder.core.customizer import LoginManagerAction
    monkeypatch.setattr('os.geteuid', lambda: 0)
    monkeypatch.setattr('os.chown', lambda *args: None)
    manager = SimpleNamespace(mode='real', chroot_path=tmp_path)
    LoginManagerAction('lightdm', 'xfce', 'live').execute(manager, tmp_path)
    content = (tmp_path / 'etc/lightdm/lightdm.conf.d/live.conf').read_text()
    assert 'pam-service=lightdm\n' in content
    assert 'pam-autologin-service=lightdm-autologin\n' in content
