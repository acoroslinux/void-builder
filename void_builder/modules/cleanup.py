"""
cleanup.py - Cleanup module for void_builder.

Removes temporary build directories after ISO generation.
"""

import os
import shutil

from void_builder.core.base_module import BaseModule
from void_builder.utils.lib import info_msg, warn_msg


class CleanupModule(BaseModule):
    """Cleans up temporary build directories."""

    def __init__(self, config):
        super().__init__(config)
        self.output_dir = self.config.get("output_dir", "./output")
        self.iso_dir = f"{self.output_dir}_iso"
        self.cleanup = self.config.get("cleanup", True)

    def run(self):
        if not self.cleanup:
            info_msg("Cleanup disabled in config. Skipping.")
            return

        info_msg("Cleaning up temporary directories...")

        for d in [self.output_dir, self.iso_dir]:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                    info_msg(f"Removed {d}")
                except Exception as e:
                    warn_msg(f"Failed to remove {d}: {e}")

        info_msg("Cleanup complete")

