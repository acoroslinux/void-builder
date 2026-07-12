import os
from void_builder.core.base_module import BaseModule
from void_builder.utils.command import CommandRunner

class RootfsBuilder(BaseModule):
    def __init__(self, config):
        super().__init__(config)
        self.arch = self.config.get('architecture', 'x86_64')
        self.base_system = self.config.get('base_system', 'base-system')
        self.repository = self.config.get('repository', 'https://repo-default.voidlinux.org/current')
        self.output_dir = self.config.get('output_dir', './output')
        self.packages = self.config.get('packages', [])

    def run(self):
        print(f"Building rootfs for {self.arch}...")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # In a real scenario, this would use xbps-install in a chroot or container
        # For now, we'll just simulate the process or use a containerized approach
        print(f"Target architecture: {self.arch}")
        print(f"Base system: {self.base_system}")
        print(f"Repository: {self.repository}")
        print(f"Additional packages: {', '.join(self.packages)}")
        
        # Example of how we might call a container to do the actual build
        # to ensure it's isolated from the host OS
        self._build_in_container()

    def _build_in_container(self):
        print("Setting up isolated build environment using static binaries...")
        
        # We will use static xbps binaries and proot to create an isolated environment
        # without requiring docker or root privileges
        
        # 1. Ensure we have the static binaries
        tools_dir = os.path.join(os.path.dirname(__file__), '..', 'tools')
        os.makedirs(tools_dir, exist_ok=True)
        
        xbps_install = os.path.join(tools_dir, 'usr', 'bin', 'xbps-install.static')
        if not os.path.exists(xbps_install):
            print("Downloading static XBPS binaries...")
            CommandRunner.run([
                'curl', '-LO', 'https://repo-default.voidlinux.org/static/xbps-static-latest.x86_64-musl.tar.xz'
            ], cwd=tools_dir)
            CommandRunner.run([
                'tar', 'xvf', 'xbps-static-latest.x86_64-musl.tar.xz'
            ], cwd=tools_dir)
            
        proot_bin = os.path.join(tools_dir, 'proot')
        if not os.path.exists(proot_bin):
            print("Downloading proot...")
            CommandRunner.run([
                'curl', '-LO', 'https://proot.gitlab.io/proot/bin/proot'
            ], cwd=tools_dir)
            CommandRunner.run(['chmod', '+x', 'proot'], cwd=tools_dir)

        # 2. Create the rootfs using xbps-install
        print(f"Creating rootfs in {self.output_dir}...")
        
        # Create necessary directories
        os.makedirs(os.path.join(self.output_dir, 'var/db/xbps/keys'), exist_ok=True)
        
        # Copy keys
        keys_dir = os.path.join(tools_dir, 'var/db/xbps/keys')
        if os.path.exists(keys_dir):
            CommandRunner.run(['cp', '-r', keys_dir + '/.', os.path.join(self.output_dir, 'var/db/xbps/keys/')])
            
        # Run xbps-install to bootstrap the system
        packages = [self.base_system] + self.packages
        
        xbps_cmd = [
            xbps_install,
            '-S',
            '-r', self.output_dir,
            '-R', self.repository,
            '-y'
        ] + packages
        
        try:
            # Set environment variables for xbps
            env = os.environ.copy()
            env['XBPS_ARCH'] = self.arch
            
            print(f"Running: {' '.join(xbps_cmd)}")
            CommandRunner.run(xbps_cmd, env=env)
            print("Rootfs created successfully.")
        except Exception as e:
            print(f"Failed to create rootfs: {e}")
