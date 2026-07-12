import click
import sys
import os

# Add the parent directory to sys.path to allow importing void_builder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from void_builder.config.manager import ConfigManager

@click.command()
@click.option('--config', '-c', required=True, help='Path to the specific build configuration file (YAML or JSON)')
@click.option('--common-dir', '-C', default=None, help='Path to the directory containing common configuration files')
def main(config, common_dir):
    """Void Linux Image Builder"""
    click.echo(f"Loading configuration from {config}...")
    try:
        cfg_manager = ConfigManager(config, common_dir)
        click.echo("Configuration loaded and merged successfully.")
        
        from void_builder.modules.rootfs import RootfsBuilder
        from void_builder.modules.services import ServicesModule
        from void_builder.modules.users import UsersModule
        from void_builder.modules.initramfs import InitramfsModule
        from void_builder.modules.iso import IsoModule
        from void_builder.modules.bootloader import BootloaderModule
        from void_builder.modules.cleanup import CleanupModule
        
        # Initialize and run modules based on config
        rootfs_builder = RootfsBuilder(cfg_manager)
        rootfs_builder.run()
        
        services_module = ServicesModule(cfg_manager)
        services_module.run()
        
        users_module = UsersModule(cfg_manager)
        users_module.run()
        
        initramfs_module = InitramfsModule(cfg_manager)
        initramfs_module.run()
        
        bootloader_module = BootloaderModule(cfg_manager)
        bootloader_module.run()
        
        iso_module = IsoModule(cfg_manager)
        iso_module.run()
        
        cleanup_module = CleanupModule(cfg_manager)
        cleanup_module.run()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

if __name__ == '__main__':
    main()
