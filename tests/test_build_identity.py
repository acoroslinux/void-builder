import json
from pathlib import Path

import pytest

from cli import _resolve_output_name
from void_builder.core.config_loader import ConfigAssembler, ConfigValidationError
from void_builder.core.path_utils import resolve_from_project


@pytest.mark.parametrize('preset,desktop', [
    ('desktop-kde', 'kde'), ('desktop-gnome', 'gnome'),
    ('desktop-xfce', 'xfce'), ('developer', 'xfce'),
    ('gaming', 'xfce'), ('rescue-sysadmin', 'xfce'), ('minimal', 'base'),
])
def test_preset_artifact_identity(preset, desktop):
    cfg = ConfigAssembler('configs').assemble('x86_64', preset=preset)
    assert _resolve_output_name('x86_64', desktop=cfg.get('desktop'), kernel=cfg.get('kernel')) == f'void-x86_64-linux-{desktop}.iso'


def test_kernel_override_is_in_package_plan():
    cfg = ConfigAssembler('configs').assemble('x86_64', preset='developer', target_kernel='linux6.6')
    assert cfg.get('kernel') == 'linux6.6'
    assert cfg.get('platform_specific.packages') == ['linux6.6']
    assert _resolve_output_name('x86_64', desktop=cfg.get('desktop'), kernel=cfg.get('kernel')) == 'void-x86_64-linux6.6-xfce.iso'


@pytest.mark.parametrize('arch,kernel', [('rpi-aarch64', 'rpi-kernel'), ('pinebookpro', 'pinebookpro-kernel'), ('asahi', 'linux-asahi')])
def test_platform_kernel_identity(arch, kernel):
    assert ConfigAssembler('configs').assemble(arch).get('kernel') == kernel


def test_hostname_defaults_and_overrides():
    assembler = ConfigAssembler('configs')
    assert assembler.assemble('x86_64').get('customizations.hostname') == 'void-live'
    assert assembler.assemble('x86_64', target_desktop='xfce').get('customizations.hostname') == 'void-xfce'
    assert assembler.assemble('x86_64', preset='developer').get('customizations.hostname') == 'void-dev'
    assert assembler.assemble('x86_64', preset='developer', hostname='my-pc').get('customizations.hostname') == 'my-pc'
    with pytest.raises(ConfigValidationError, match='Hostname'):
        assembler.assemble('x86_64', hostname='invalid hostname')


def test_bad_json_is_rejected(tmp_path):
    (tmp_path / 'global_build.json').write_text('{bad json')
    with pytest.raises(ConfigValidationError, match='global_build.json'):
        ConfigAssembler(str(tmp_path)).assemble('x86_64')


def test_all_bundled_profiles_parse_and_presets_validate():
    root = resolve_from_project('configs')
    for path in root.rglob('*.json'):
        assert isinstance(json.loads(path.read_text()), dict), path
    for path in (root / 'presets').glob('*.json'):
        report = ConfigAssembler(str(root)).validate('x86_64', preset=path.stem)
        assert report['valid'], report['errors']


def test_custom_names_and_formats():
    assert _resolve_output_name('x86_64', output='my-release.iso') == 'my-release.iso'
    assert _resolve_output_name('aarch64', desktop='sway', kernel='linux-lts', distro='My Distro', platform=['x13s'], output_format='img', compress_image=True, compression='zstd') == 'my-distro-aarch64-linux-lts-sway-x13s.img.zst'


def test_cli_passes_resolved_name_to_build(monkeypatch):
    import cli
    from unittest.mock import MagicMock

    orchestrator = MagicMock()
    monkeypatch.setattr(cli, 'BuildOrchestrator', MagicMock(return_value=orchestrator))
    monkeypatch.setattr('sys.argv', ['cli.py', '--preset', 'desktop-kde', '--kernel', 'linux6.6'])
    cli.main()
    orchestrator.run_build.assert_called_once_with('void-x86_64-linux6.6-kde.iso', output_format='iso')
