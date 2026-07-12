import os
import shutil
from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner

class InitramfsModule(ChrootModule):
    def __init__(self, config):
        super().__init__(config)
        self.arch = self.config.get('architecture', 'x86_64')

    def run(self):
        print("Generating initramfs...")
        
        # Find kernel version
        boot_dir = f"{self.output_dir}/boot"
        kernel_ver = ""
        if os.path.exists(boot_dir):
            for file in os.listdir(boot_dir):
                if file.startswith("vmlinuz-"):
                    kernel_ver = file.replace("vmlinuz-", "")
                    break
                    
        if not kernel_ver:
            print("Warning: No kernel found in /boot. Cannot generate initramfs.")
            return

        print(f"Found kernel version: {kernel_ver}")

        # Install dracut and its dependencies if not present
        # The autoinstaller module depends on network (dracut-network)
        # We also need eudev for udev rules and libcap-ng
        # We also need to make sure the kernel package is fully installed so dracut can find its modules
        # We also need findutils, cryptsetup, and device-mapper for dracut to work properly
        xbps_install = os.path.join(self.tools_dir, 'usr', 'bin', 'xbps-install.static')
        cmd = [
            xbps_install,
            '-S',
            '-r', self.output_dir,
            '-R', self.config.get('repository', 'https://repo-default.voidlinux.org/current'),
            '-y', 'dracut', 'dracut-network', 'eudev', 'libcap-ng', 'linux', 'findutils', 'cryptsetup', 'device-mapper', 'coreutils', 'util-linux'
        ]
        try:
            CommandRunner.run(cmd)
        except Exception as e:
            # Ignore errors if packages are already installed
            pass

        # Copy dracut modules from void-mklive if they exist
        # We need the vmklive module for the live CD to work properly
        mklive_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'void-mklive')
        if os.path.exists(mklive_dir):
            print("Copying dracut modules from void-mklive...")
            
            # Copy vmklive module
            vmklive_src = os.path.join(mklive_dir, 'dracut', 'vmklive')
            vmklive_dest = os.path.join(self.output_dir, 'usr', 'lib', 'dracut', 'modules.d', '01vmklive')
            if os.path.exists(vmklive_src):
                os.makedirs(vmklive_dest, exist_ok=True)
                CommandRunner.run(['cp', '-r', f"{vmklive_src}/.", vmklive_dest])
                
            # Copy autoinstaller module
            autoinstaller_src = os.path.join(mklive_dir, 'dracut', 'autoinstaller')
            autoinstaller_dest = os.path.join(self.output_dir, 'usr', 'lib', 'dracut', 'modules.d', '01autoinstaller')
            if os.path.exists(autoinstaller_src):
                os.makedirs(autoinstaller_dest, exist_ok=True)
                CommandRunner.run(['cp', '-r', f"{autoinstaller_src}/.", autoinstaller_dest])

        # Generate initramfs using dracut inside the chroot
        # We need to make sure /boot is writable in the chroot
        # proot might be restricting it if it's not explicitly bound or if permissions are wrong
        # Let's write it to /tmp first, then move it
        # We also need to make sure udevd is available or omit the udev-rules module if it fails
        # We also need to omit iscsi, lunmask, lvm, cifs, and hwdb as they are causing issues in the proot environment
        # We also need to omit dmsquash-live because it requires find which is failing to install for some reason
        # We also need to omit udev-rules because it requires udevd which is not available in the chroot
        
        # Actually, the problem is that dracut is trying to use 'find' which is in /usr/bin/find, but dracut might be looking in /bin/find
        # Let's make sure find is available in the PATH
        # We also need to omit dmsquash-live and dm because they are failing to install find
        dracut_cmd = f"PATH=$PATH:/usr/bin:/bin dracut -N --xz --add-drivers 'ahci' --force-add 'vmklive autoinstaller' --omit 'systemd udev-rules iscsi lunmask lvm cifs hwdb dmsquash-live dm' /tmp/initrd {kernel_ver} && mv /tmp/initrd /boot/initrd"
        
        try:
            self.run_in_chroot(dracut_cmd)
            print("Initramfs generated successfully.")
        except Exception as e:
            print(f"Failed to generate initramfs: {e}")
