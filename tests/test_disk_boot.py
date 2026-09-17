from pathlib import Path
from unittest.mock import patch

import pytest

from void_builder.core.disk_engine import DiskEngine


@pytest.fixture
def engine(tmp_path):
    root = tmp_path / "root"
    for directory in ("boot", "etc", "usr/lib/grub/x86_64-efi"):
        (root / directory).mkdir(parents=True)
    work = tmp_path / "workdir" / "build"
    work.mkdir(parents=True)
    return DiskEngine(work, root, "boot-test", {}, "real")


def add_pair(engine, version):
    boot = engine.target_root / "boot"
    (boot / f"vmlinuz-{version}").write_bytes(b"kernel")
    (boot / f"initramfs-{version}.img").write_bytes(b"initramfs")


def test_standalone_loads_partition_drivers_before_search(engine):
    add_pair(engine, "6.18.52_1")
    with patch("void_builder.core.disk_engine.subprocess.run") as run, \
            patch.object(engine, "_calculate_image_size", return_value=100):
        engine.build_disk_image()

    cfg = (engine.target_root / "boot/grub/grub.cfg").read_text()
    for module in ("part_gpt", "part_msdos", "ext2"):
        assert cfg.index(f"insmod {module}") < cfg.index("search --")
    assert "linux /boot/vmlinuz-6.18.52_1 root=LABEL=void_root rw" in cfg
    assert "initrd /boot/initramfs-6.18.52_1.img" in cfg
    standalone = next(call.args[0] for call in run.call_args_list
                      if Path(call.args[0][0]).name == "grub-mkstandalone")
    modules = next(arg.split("=", 1)[1].split() for arg in standalone
                   if arg.startswith("--modules="))
    assert {"part_gpt", "part_msdos", "ext2", "search_label", "linux"} <= set(modules)
    assert f"boot/grub/grub.cfg={engine.target_root}/boot/grub/grub.cfg" in standalone
    assert (engine.target_root / "boot/efi").is_dir()
    # Disk finalization must not re-enter an already unmounted chroot.
    assert not any(call.args[0][0] == "chroot" for call in run.call_args_list)


def test_selects_matching_version_despite_stale_aliases(engine):
    add_pair(engine, "6.18.9_1")
    add_pair(engine, "6.18.10_1")
    boot = engine.target_root / "boot"
    (boot / "vmlinuz").symlink_to("vmlinuz-6.18.9_1")
    (boot / "initrd").symlink_to("missing-initramfs")
    kernel, initrd = engine._select_boot_files()
    assert kernel.name == "vmlinuz-6.18.10_1"
    assert initrd.name == "initramfs-6.18.10_1.img"


@pytest.mark.parametrize("files", [
    {},
    {"vmlinuz-6.18.52_1": b"kernel", "initramfs-6.18.51_1.img": b"initramfs"},
    {"vmlinuz-6.18.52_1": b"", "initramfs-6.18.52_1.img": b"initramfs"},
    {"vmlinuz-6.18.52_1": b"kernel", "initramfs-6.18.52_1.img": b""},
])
def test_missing_empty_or_mismatched_boot_files_abort_before_packaging(engine, files):
    for name, data in files.items():
        (engine.target_root / "boot" / name).write_bytes(data)
    with patch("void_builder.core.disk_engine.subprocess.run") as run:
        with pytest.raises(RuntimeError, match="No matching nonempty kernel/initramfs"):
            engine.build_disk_image()
    run.assert_not_called()


def test_unversioned_custom_kernel(engine):
    (engine.target_root / "boot/Image").write_bytes(b"kernel")
    (engine.target_root / "boot/initrd").write_bytes(b"initramfs")
    kernel, initrd = engine._select_boot_files()
    assert (kernel.name, initrd.name) == ("Image", "initrd")


def test_advanced_menu_keeps_each_kernel_with_its_initramfs(engine):
    add_pair(engine, "6.18.9_1")
    add_pair(engine, "6.18.10_1")
    # Incomplete upgrades must not create broken menu entries.
    (engine.target_root / "boot/vmlinuz-6.18.11_1").write_bytes(b"kernel")
    cfg, _ = engine._prepare_grub_config()
    menu = cfg.read_text()
    assert "set default=void-linux\n" in menu
    assert "set timeout_style=menu\n" in menu
    main, advanced = menu.split("submenu 'Advanced options for Void Linux'", 1)
    assert "linux /boot/vmlinuz-6.18.10_1 root=LABEL=void_root rw\n" in main
    assert "linux /boot/vmlinuz-6.18.10_1 root=LABEL=void_root rw nomodeset\n" in main
    assert "6.18.11_1" not in menu
    assert advanced.index("Linux 6.18.10_1") < advanced.index("Linux 6.18.9_1")
    for version in ("6.18.10_1", "6.18.9_1"):
        for suffix, args in (("", ""), (" (recovery mode)", " single")):
            entry = advanced.split(f"menuentry 'Void Linux, with Linux {version}{suffix}'", 1)[1].split("}", 1)[0]
            assert "search --no-floppy --label void_root --set=root" in entry
            assert f"linux /boot/vmlinuz-{version} root=LABEL=void_root rw{args}\n" in entry
            assert f"initrd /boot/initramfs-{version}.img" in entry
    assert "root=live:" not in menu
    assert "systemd.unit=" not in menu


def test_firmware_entry_is_guarded_and_power_actions_load_modules(engine):
    add_pair(engine, "6.18.52_1")
    cfg, _ = engine._prepare_grub_config()
    menu = cfg.read_text()
    assert 'if [ "$grub_platform" = efi ]; then\n  insmod efifwsetup\n  if fwsetup --is-supported; then' in menu
    assert "menuentry 'UEFI Firmware Settings'" in menu
    assert "  insmod reboot\n  reboot\n" in menu
    assert "  insmod halt\n  halt\n" in menu


def test_custom_kernel_also_gets_normal_and_recovery_entries(engine):
    (engine.target_root / "boot/Image").write_bytes(b"kernel")
    (engine.target_root / "boot/initrd").write_bytes(b"initramfs")
    cfg, _ = engine._prepare_grub_config()
    menu = cfg.read_text()
    assert "with Linux custom kernel (recovery mode)" in menu
    assert "linux /boot/Image root=LABEL=void_root rw single\n" in menu
