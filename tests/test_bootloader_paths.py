from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from void_builder.core.bootloaders.grub2 import Grub2Bootloader, Grub2BootloaderError
from void_builder.core.bootloaders.syslinux import SyslinuxBootloader, SyslinuxBootloaderError


def write(path, data=b'fixture'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def toolchain_at(tmp_path):
    # Deliberately unrelated to ISO staging: no parent-path inference is valid.
    root = tmp_path / 'custom workdir' / 'build_host'
    return SimpleNamespace(host_dir=root / 'void-host', target_dir=root / 'void-target', mode='real')


@pytest.mark.parametrize('arch,grub_arch,efi_name', [
    ('x86_64', 'x86_64-efi', 'BOOTX64.EFI'),
    ('i686', 'i386-efi', 'BOOTIA32.EFI'),
    ('aarch64', 'arm64-efi', 'BOOTAA64.EFI'),
])
def test_efi_uses_explicit_toolchain_without_grub_in_rootfs(tmp_path, monkeypatch, arch, grub_arch, efi_name):
    tc = toolchain_at(tmp_path)
    for name in ('grub-mkstandalone', 'mkfs.fat', 'mmd', 'mcopy'):
        write(tc.host_dir / 'usr/sbin' / name).chmod(0o755)
    write(tc.target_dir / 'usr/lib/grub' / grub_arch / 'modinfo.sh')
    write(tc.host_dir / 'usr/share/grub/unicode.pf2')
    staging = tmp_path / 'separate staging'
    write(staging / 'boot/grub/grub.cfg')
    rootfs = tmp_path / 'airootfs'
    rootfs.mkdir()
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        for arg in cmd:
            if arg.startswith('--output='):
                write(Path(arg.split('=', 1)[1]), b'EFI executable')
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr('void_builder.core.bootloaders.grub2.subprocess.run', run)
    grub = Grub2Bootloader({'platform_specific': {'architecture': arch}}, 'VOID')
    assert grub.generate_boot_image(staging, rootfs, toolchain=tc)
    mk = next(cmd for cmd, _ in calls if '--format=' + grub_arch in cmd)
    assert mk[0] == str(tc.host_dir / 'usr/sbin/grub-mkstandalone')
    assert '--directory=' + str(tc.target_dir / 'usr/lib/grub' / grub_arch) in mk
    assert any(cmd[-1] == '::/EFI/BOOT/' + efi_name for cmd, _ in calls)
    assert not any('chroot' in cmd for cmd, _ in calls)
    assert (staging / 'boot/grub/fonts/unicode.pf2').is_file()


def test_missing_real_grub_fails_instead_of_simulating(tmp_path, monkeypatch):
    tc = toolchain_at(tmp_path)
    monkeypatch.setattr('void_builder.core.bootloaders.grub2.shutil.which', lambda *a, **k: None)
    grub = Grub2Bootloader({}, 'VOID')
    with pytest.raises(Grub2BootloaderError, match='Missing FAT'):
        grub.generate_boot_image(tmp_path / 'iso', tmp_path / 'empty-rootfs', toolchain=tc)
    assert not (tmp_path / 'iso/boot/grub/efiboot.img').exists()


def test_failed_required_efi_cannot_reuse_stale_loader(tmp_path, monkeypatch):
    tc = toolchain_at(tmp_path)
    write(tc.host_dir / 'usr/bin/grub-mkstandalone')
    write(tc.target_dir / 'usr/lib/grub/x86_64-efi/modinfo.sh')
    write(tmp_path / 'iso/boot/grub/BOOTX64.EFI', b'stale')
    monkeypatch.setattr('void_builder.core.bootloaders.grub2.shutil.which', lambda name, **k: name)
    monkeypatch.setattr('void_builder.core.bootloaders.grub2.subprocess.run', lambda cmd, **k: SimpleNamespace(returncode=1 if any(arg.startswith('--format=') for arg in cmd) else 0, stdout='', stderr='failure'))
    with pytest.raises(Grub2BootloaderError, match='BOOTX64'):
        Grub2Bootloader({}, 'VOID').generate_boot_image(tmp_path / 'iso', toolchain=tc)
    assert not (tmp_path / 'iso/boot/grub/BOOTX64.EFI').exists()
    assert not (tmp_path / 'iso/boot/grub/efiboot.img').exists()


BIOS_FILES = ['isolinux.bin', 'ldlinux.c32', 'libcom32.c32', 'vesamenu.c32',
              'libutil.c32', 'chain.c32', 'reboot.c32', 'poweroff.c32', 'isohdpfx.bin']


@pytest.mark.parametrize('suffix', ['', 'bios'])
def test_syslinux_uses_target_tree_and_stages_matching_mbr(tmp_path, suffix):
    tc = toolchain_at(tmp_path)
    for name in BIOS_FILES:
        write(tc.target_dir / 'usr/lib/syslinux' / suffix / name, b'target')
        write(tmp_path / 'rootfs/usr/lib/syslinux' / name, b'rootfs')
    SyslinuxBootloader({}).generate_boot_image(tmp_path / 'iso', tmp_path / 'rootfs', toolchain=tc)
    for name in BIOS_FILES:
        assert (tmp_path / 'iso/boot/isolinux' / name).read_bytes() == b'target'


def test_partial_syslinux_set_rejected(tmp_path):
    tc = toolchain_at(tmp_path)
    write(tc.target_dir / 'usr/lib/syslinux/isolinux.bin')
    with pytest.raises(SyslinuxBootloaderError, match='Complete Syslinux'):
        SyslinuxBootloader({}).generate_boot_image(tmp_path / 'iso', None, toolchain=tc)


def test_explicit_mock_never_runs_real_tools(tmp_path, monkeypatch):
    run = Mock(side_effect=AssertionError('real command in mock mode'))
    monkeypatch.setattr('void_builder.core.bootloaders.grub2.subprocess.run', run)
    Grub2Bootloader({}, 'VOID').generate_boot_image(tmp_path, mode='mock')
    SyslinuxBootloader({}).generate_boot_image(tmp_path, None, mode='mock')
    run.assert_not_called()


def test_arm64_menu_matches_staged_kernel(tmp_path):
    grub = Grub2Bootloader({'platform_specific': {'architecture': 'aarch64'}}, 'VOID')
    grub.prepare_files(tmp_path)
    cfg = (tmp_path / 'boot/grub/grub.cfg').read_text()
    assert 'linux /boot/vmlinux ' in cfg
    assert '/boot/vmlinuz' not in cfg
    assert '@@KERNEL_FILE@@' not in cfg


def test_host_environment_pairs_libc_with_its_iconv_modules(tmp_path, monkeypatch):
    (tmp_path / 'usr/lib/gconv').mkdir(parents=True)
    monkeypatch.setenv('GCONV_PATH', '/unrelated/host/modules')
    env = Grub2Bootloader._host_environment(tmp_path)
    assert env['GCONV_PATH'] == str(tmp_path / 'usr/lib/gconv')
    assert env['LD_LIBRARY_PATH'].split(':')[0] == str(tmp_path / 'usr/lib')


def test_fat_command_failure_reports_stderr(monkeypatch):
    monkeypatch.setattr('void_builder.core.bootloaders.grub2.subprocess.run',
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='Error converting to codepage 850'))
    with pytest.raises(Grub2BootloaderError, match='Error converting to codepage 850'):
        Grub2Bootloader._run_host_command(['mmd', '-i', 'efi.img', '::/EFI'], {})


def test_real_mtools_with_isolated_glibc(tmp_path):
    import platform
    import subprocess
    from void_builder.core.path_utils import resolve_from_project

    if platform.machine() != 'x86_64':
        pytest.skip('Cached toolchain fixture is x86_64')
    cache = resolve_from_project('cache/xbps/x86_64')
    host = tmp_path / 'void-host'
    host.mkdir()
    for name in ('mtools', 'dosfstools', 'glibc'):
        package = next(cache.glob(f'{name}-[0-9]*.x86_64.xbps'), None)
        if package is None:
            pytest.skip('Cached native tools unavailable')
        subprocess.run(['tar', '-xf', str(package), '-C', str(host)], check=True, capture_output=True)
    env = Grub2Bootloader._host_environment(host)
    img = tmp_path / 'efi.img'
    with img.open('wb') as stream:
        stream.truncate(32 * 1024 * 1024)
    run = Grub2Bootloader._run_host_command
    run(['mkfs.fat', '-F16', '-S', '512', '-n', 'GRUB_UEFI', str(img)], env)
    run(['mmd', '-i', str(img), '::/EFI', '::/EFI/BOOT'], env)
    payload = tmp_path / 'BOOTX64.EFI'
    payload.write_bytes(b'EFI test payload')
    run(['mcopy', '-i', str(img), str(payload), '::/EFI/BOOT/BOOTX64.EFI'], env)
    result = run(['mtype', '-i', str(img), '::/EFI/BOOT/BOOTX64.EFI'], env)
    assert result.stdout == 'EFI test payload'
