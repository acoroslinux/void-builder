import os
from void_builder.modules.chroot import ChrootModule

class ServicesModule(ChrootModule):
    def __init__(self, config):
        super().__init__(config)
        self.services = self.config.get('services', [])

    def run(self):
        if not self.services:
            print("No services to enable.")
            return

        print(f"Enabling services: {', '.join(self.services)}")
        
        for service in self.services:
            # In Void Linux (runit), enabling a service means creating a symlink
            # from /etc/sv/<service> to /etc/runit/runsvdir/default/<service>
            # or /var/service/<service>
            
            # Check if service exists
            check_cmd = f"test -d /etc/sv/{service}"
            try:
                self.run_in_chroot(check_cmd)
            except Exception:
                print(f"Warning: Service {service} not found in /etc/sv/")
                continue
                
            # Create symlink
            link_cmd = f"ln -sf /etc/sv/{service} /etc/runit/runsvdir/default/{service}"
            try:
                self.run_in_chroot(link_cmd)
                print(f"Enabled service: {service}")
            except Exception as e:
                print(f"Failed to enable service {service}: {e}")
