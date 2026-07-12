"""
services.py - Service management module for void_builder.

Enables runit services by creating symlinks from /etc/sv/<service>
to /etc/runit/runsvdir/default/<service>, matching Void Linux convention.
"""

import os

from void_builder.modules.chroot import ChrootModule
from void_builder.utils.lib import info_msg, warn_msg, error_msg, ensure_dir


class ServicesModule(ChrootModule):
    """Manages runit service enablement inside the rootfs."""

    def __init__(self, config):
        super().__init__(config)
        self.services = self.config.get("services", [])

    def run(self):
        if not self.services:
            info_msg("No services to enable.")
            return

        svc_list = ", ".join(self.services)
        info_msg(f"Enabling {len(self.services)} services: {svc_list}")

        runsvdir = os.path.join(self.output_dir, "etc", "runit", "runsvdir", "default")
        ensure_dir(runsvdir)

        enabled = 0
        for service in self.services:
            sv_dir = os.path.join(self.output_dir, "etc", "sv", service)
            if not os.path.isdir(sv_dir):
                warn_msg(f"Service {service} not found in /etc/sv/, skipping")
                continue

            link_path = os.path.join(runsvdir, service)
            target = f"/etc/sv/{service}"

            # Remove existing link if present
            if os.path.islink(link_path) or os.path.exists(link_path):
                os.remove(link_path)

            os.symlink(target, link_path)
            info_msg(f"  Enabled: {service}")
            enabled += 1

        info_msg(f"Enabled {enabled}/{len(self.services)} services")

