from pathlib import Path
from types import SimpleNamespace

import pytest

from void_builder.core.config_loader import ConfigAssembler
from void_builder.core.iso_engine import VoidEngine


RESCUE = {'gparted', 'testdisk', 'ddrescue', 'smartmontools', 'nvme-cli',
          'hdparm', 'inxi', 'dmidecode', 'lshw', 'tcpdump', 'iperf3'}


@pytest.mark.parametrize('preset', [p.stem for p in Path('configs/presets').glob('*.json')])
def test_preset_rescue_packages_and_configuration_are_opt_in(preset):
    cfg = ConfigAssembler('configs').assemble('x86_64', preset=preset)
    packages = set(VoidEngine('x86_64', cfg, SimpleNamespace())._package_plan()['official'])
    copies = cfg.get('customizations.copy_files', [])
    rescue_copies = [entry for entry in copies if 'rescue-sysadmin' in entry['source']]
    if preset == 'rescue-sysadmin':
        assert RESCUE <= packages
        assert len(rescue_copies) == 2
    else:
        assert not (RESCUE & packages)
        assert not rescue_copies
    if preset == 'minimal':
        assert cfg.get('package_profiles') == ['base']
        assert not {'cupsd', 'bluetoothd', 'lightdm', 'sddm'} & set(cfg.get('customizations.services'))
    if preset == 'rescue-sysadmin':
        assert 'printing' not in cfg.get('package_profiles')
        assert 'cupsd' not in cfg.get('customizations.services')


def test_plain_xfce_and_reused_assembler_do_not_inherit_rescue():
    assembler = ConfigAssembler('configs')
    assembler.assemble('x86_64', preset='rescue-sysadmin')
    cfg = assembler.assemble('x86_64', target_desktop='xfce')
    packages = set(VoidEngine('x86_64', cfg, SimpleNamespace())._package_plan()['official'])
    assert not (RESCUE & packages)
    assert not cfg.get('customizations.copy_files')
    assert not Path('configs/custom_files/autostart/create-rescue-icons.desktop').exists()
    assert not Path('configs/custom_files/scripts/add-rescue-desktop-icons.sh').exists()
    assert not Path('configs/custom_files/skel/.xinitrc').exists()
    assert Path('configs/custom_files/desktops/xfce/etc/skel/.xinitrc').exists()


def test_explicit_extra_profile_still_works():
    cfg = ConfigAssembler('configs').assemble('x86_64', preset='desktop-xfce', package_profiles=['dev-tools'])
    assert 'dev-tools' in cfg.get('package_profiles')
    assert 'base-devel' in cfg.get('package_sources.official')
