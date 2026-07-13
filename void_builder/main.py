"""
main.py - Void Linux Image Builder entry point.

Orchestrates the build pipeline:
  1. RootfsBuilder    - Bootstrap the root filesystem
  2. ServicesModule   - Enable runit services
  3. UsersModule      - Create users and set passwords
  4. InitramfsModule  - Generate initramfs with dracut
  5. BootloaderModule - Set up GRUB and ISOLINUX
  6. IsoModule        - Create squashfs and ISO image
  7. CleanupModule    - Remove temporary directories
"""

import click
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from void_builder.config.manager import ConfigManager
from void_builder.utils.lib import info_msg, error_msg


@click.command()
@click.option("--config", "-c", required=True,
              help="Path to the build configuration file (YAML or JSON)")
@click.option("--common-dir", "-C", default=None,
              help="Path to common configuration directory")
def main(config, common_dir):
    """Void Linux Image Builder"""
    info_msg("=" * 60)
    info_msg("Void Linux Image Builder")
    info_msg("=" * 60)

    click.echo(f"Loading configuration from {config}...")

    try:
        cfg_manager = ConfigManager(config, common_dir)
        info_msg("Configuration loaded successfully")

        # Ensure static binaries (xbps, proot) are available before any module runs
        from void_builder.utils.lib import ensure_static_xbps, ensure_proot
        ensure_static_xbps()
        ensure_proot()

        # Import modules
        from void_builder.modules.rootfs import RootfsBuilder
        from void_builder.modules.services import ServicesModule
        from void_builder.modules.users import UsersModule
        from void_builder.modules.initramfs import InitramfsModule
        from void_builder.modules.bootloader import BootloaderModule
        from void_builder.modules.iso import IsoModule
        from void_builder.modules.cleanup import CleanupModule

        # Define the build pipeline
        pipeline = [
            ("RootfsBuilder",    RootfsBuilder),
            ("ServicesModule",   ServicesModule),
            ("UsersModule",      UsersModule),
            ("InitramfsModule",  InitramfsModule),
            ("BootloaderModule", BootloaderModule),
            ("IsoModule",        IsoModule),
            ("CleanupModule",    CleanupModule),
        ]

        # Execute pipeline
        for name, module_class in pipeline:
            info_msg("")
            info_msg(f"─" * 60)
            info_msg(f"Running: {name}")
            info_msg(f"─" * 60)

            try:
                module = module_class(cfg_manager)
                module.run()
            except Exception as e:
                error_msg(f"{name} failed: {e}")
                raise

        info_msg("")
        info_msg("=" * 60)
        info_msg("Build completed successfully!")
        info_msg("=" * 60)

    except Exception as e:
        error_msg(f"Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

