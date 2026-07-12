import os
from void_builder.modules.chroot import ChrootModule

class UsersModule(ChrootModule):
    def __init__(self, config):
        super().__init__(config)
        self.users = self.config.get('users', [])
        self.root_password = self.config.get('root_password', None)

    def run(self):
        if self.root_password:
            print("Setting root password...")
            # Using chpasswd to set password non-interactively
            cmd = f"echo 'root:{self.root_password}' | chpasswd -c SHA512"
            try:
                self.run_in_chroot(cmd)
                print("Root password set successfully.")
            except Exception as e:
                print(f"Failed to set root password: {e}")

        if not self.users:
            print("No additional users to create.")
            return

        for user in self.users:
            username = user.get('name')
            if not username:
                continue
                
            print(f"Creating user: {username}")
            
            # Check if user exists
            try:
                self.run_in_chroot(f"id {username}")
                print(f"User {username} already exists.")
            except Exception:
                # Create user
                groups = user.get('groups', [])
                groups_str = f"-G {','.join(groups)}" if groups else ""
                shell = user.get('shell', '/bin/bash')
                
                cmd = f"useradd -m -s {shell} {groups_str} {username}"
                try:
                    self.run_in_chroot(cmd)
                    print(f"Created user {username}")
                except Exception as e:
                    print(f"Failed to create user {username}: {e}")
                    continue
            
            # Set password if provided
            password = user.get('password')
            if password:
                cmd = f"echo '{username}:{password}' | chpasswd -c SHA512"
                try:
                    self.run_in_chroot(cmd)
                    print(f"Set password for {username}")
                except Exception as e:
                    print(f"Failed to set password for {username}: {e}")
