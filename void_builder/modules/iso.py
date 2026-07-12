import os
from void_builder.modules.chroot import ChrootModule

class IsoModule(ChrootModule):
    def __init__(self, config):
        super().__init__(config)
        self.iso_name = self.config.get('name', 'void-custom')
        self.iso_version = self.config.get('version', '1.0')
        self.arch = self.config.get('architecture', 'x86_64')
        self.output_dir = self.config.get('output_dir', './output')
        self.iso_output = self.config.get('iso_output', f"{self.iso_name}-{self.iso_version}-{self.arch}.iso")

    def run(self):
        print(f"Building ISO: {self.iso_output}")
        
        # We need to install xorriso and squashfs-tools in the host or use the ones in the rootfs
        # Since we want to be isolated, we'll use the ones in the rootfs!
        
        # 1. Create squashfs of the rootfs
        squashfs_file = f"{self.output_dir}/rootfs.squashfs"
        if os.path.exists(squashfs_file):
            os.remove(squashfs_file)
            
        print("Creating squashfs image...")
        # We run mksquashfs from inside the rootfs, but we need to exclude the squashfs file itself
        # and we need to mount the host directory to write the output
        
        # Actually, it's easier to run mksquashfs from the host if available, 
        # but to keep it isolated, we can use proot to run the rootfs's mksquashfs
        # on the rootfs directory itself.
        
        # Let's create a temporary directory for the ISO contents
        iso_dir = f"{self.output_dir}_iso"
        os.makedirs(f"{iso_dir}/LiveOS", exist_ok=True)
        
        # Run mksquashfs using the binary inside the rootfs
        mksquashfs_bin = f"{self.output_dir}/usr/bin/mksquashfs"
        if not os.path.exists(mksquashfs_bin):
            print("mksquashfs not found in rootfs. Installing squashfs-tools...")
            # We need to use the static xbps-install to install it, as DNS might not work in proot
            xbps_install = os.path.join(self.tools_dir, 'usr', 'bin', 'xbps-install.static')
            cmd = [
                xbps_install,
                '-S',
                '-r', self.output_dir,
                '-R', self.config.get('repository', 'https://repo-default.voidlinux.org/current'),
                '-y', 'squashfs-tools'
            ]
            try:
                from void_builder.utils.command import CommandRunner
                CommandRunner.run(cmd)
            except Exception as e:
                print(f"Failed to install squashfs-tools: {e}")
                return
            
        # We use proot to run mksquashfs from the rootfs, but operating on the host paths
        # This is a bit tricky, so we'll just use the binary directly if it's compatible,
        # or use proot with bind mounts.
        
        cmd = [
            self.proot_bin,
            '-r', self.output_dir,
            '-0',
            '-b', f"{os.path.abspath(self.output_dir)}:/mnt/rootfs",
            '-b', f"{os.path.abspath(iso_dir)}:/mnt/iso",
            '/usr/bin/mksquashfs', '/mnt/rootfs', '/mnt/iso/LiveOS/rootfs.squashfs',
            '-comp', 'xz', '-b', '1M', '-noappend'
        ]
        
        try:
            from void_builder.utils.command import CommandRunner
            print(f"Running: {' '.join(cmd)}")
            CommandRunner.run(cmd)
            print("Squashfs created successfully.")
        except Exception as e:
            print(f"Failed to create squashfs: {e}")
            return
            
        # 2. Create the ISO using xorriso
        print("Generating ISO image...")
        
        # Install xorriso in the rootfs if not present
        xorriso_bin = f"{self.output_dir}/usr/bin/xorriso"
        if not os.path.exists(xorriso_bin):
            print("xorriso not found in rootfs. Installing xorriso...")
            xbps_install = os.path.join(self.tools_dir, 'usr', 'bin', 'xbps-install.static')
            cmd = [
                xbps_install,
                '-S',
                '-r', self.output_dir,
                '-R', self.config.get('repository', 'https://repo-default.voidlinux.org/current'),
                '-y', 'xorriso'
            ]
            try:
                CommandRunner.run(cmd)
            except Exception as e:
                print(f"Failed to install xorriso: {e}")
                return

        # Run xorriso
        iso_cmd = [
            self.proot_bin,
            '-r', self.output_dir,
            '-0',
            '-b', f"{os.path.abspath(iso_dir)}:/mnt/iso",
            '-b', f"{os.path.abspath(os.path.dirname(self.iso_output))}:/mnt/out",
            '/usr/bin/xorriso',
            '-as', 'mkisofs',
            '-iso-level', '3',
            '-rock',
            '-joliet',
            '-joliet-long',
            '-max-iso9660-filenames',
            '-omit-period',
            '-omit-version-number',
            '-relaxed-filenames',
            '-allow-lowercase',
            '-volid', 'VOID_LIVE',
            '-eltorito-boot', 'boot/isolinux/isolinux.bin',
            '-eltorito-catalog', 'boot/isolinux/boot.cat',
            '-no-emul-boot',
            '-boot-load-size', '4',
            '-boot-info-table',
            '-eltorito-alt-boot',
            '-e', 'boot/grub/efiboot.img',
            '-no-emul-boot',
            '-isohybrid-gpt-basdat',
            '-isohybrid-apm-hfsplus',
            '-output', f"/mnt/out/{os.path.basename(self.iso_output)}",
            '/mnt/iso'
        ]
        
        try:
            print(f"Running: {' '.join(iso_cmd)}")
            CommandRunner.run(iso_cmd)
            print(f"ISO created successfully at {self.iso_output}")
        except Exception as e:
            print(f"Failed to create ISO: {e}")
