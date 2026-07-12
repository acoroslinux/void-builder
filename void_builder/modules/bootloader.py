import os
import shutil
from void_builder.modules.chroot import ChrootModule
from void_builder.utils.command import CommandRunner

class BootloaderModule(ChrootModule):
    def __init__(self, config):
        super().__init__(config)
        self.iso_dir = f"{self.output_dir}_iso"
        self.arch = self.config.get('architecture', 'x86_64')
        self.boot_title = self.config.get('boot_title', 'Void Linux Custom ISO')
        self.keymap = self.config.get('keymap', 'us')
        self.locale = self.config.get('locale', 'en_US.UTF-8')
        self.boot_cmdline = self.config.get('boot_cmdline', '')

    def run(self):
        print("Setting up bootloader...")
        
        # Install grub and syslinux in the rootfs if not present
        xbps_install = os.path.join(self.tools_dir, 'usr', 'bin', 'xbps-install.static')
        
        # Determine grub packages based on architecture
        grub_pkgs = ['grub']
        if self.arch.startswith('x86_64') or self.arch.startswith('i686'):
            grub_pkgs.extend(['grub-i386-efi', 'grub-x86_64-efi', 'syslinux'])
        elif self.arch.startswith('aarch64'):
            grub_pkgs.extend(['grub-arm64-efi'])
            
        cmd = [
            xbps_install,
            '-S',
            '-r', self.output_dir,
            '-R', self.config.get('repository', 'https://repo-default.voidlinux.org/current'),
            '-y'
        ] + grub_pkgs
        
        try:
            CommandRunner.run(cmd)
        except Exception as e:
            print(f"Failed to install bootloader packages: {e}")
            return

        # Create boot directories
        os.makedirs(f"{self.iso_dir}/boot/grub", exist_ok=True)
        os.makedirs(f"{self.iso_dir}/boot/isolinux", exist_ok=True)

        # Find kernel version
        boot_dir = f"{self.output_dir}/boot"
        kernel_ver = ""
        for file in os.listdir(boot_dir):
            if file.startswith("vmlinuz-"):
                kernel_ver = file.replace("vmlinuz-", "")
                break
                
        if not kernel_ver:
            print("Warning: No kernel found in /boot")
            kernel_ver = "unknown"

        # Setup ISOLINUX (for BIOS/Legacy boot on x86)
        if self.arch.startswith('x86_64') or self.arch.startswith('i686'):
            syslinux_dir = f"{self.output_dir}/usr/lib/syslinux"
            if os.path.exists(syslinux_dir):
                for f in ['isolinux.bin', 'ldlinux.c32', 'libcom32.c32', 'vesamenu.c32', 'libutil.c32', 'chain.c32']:
                    src = f"{syslinux_dir}/{f}"
                    if os.path.exists(src):
                        shutil.copy(src, f"{self.iso_dir}/boot/isolinux/")

            # Create isolinux.cfg
            isolinux_cfg = f"""UI vesamenu.c32
PROMPT 0
TIMEOUT 150
ONTIMEOUT linux

MENU TABMSG Press ENTER to boot or TAB to edit a menu entry
MENU AUTOBOOT BIOS default device boot in # second{{,s}}...
MENU WIDTH 78
MENU MARGIN 1
MENU ROWS 12
MENU VSHIFT 2
MENU TIMEOUTROW 13
MENU TABMSGROW 2
MENU CMDLINEROW 16
MENU HELPMSGROW 20
MENU HELPMSGENDROW 34

MENU COLOR title        * #FF5255FF *
MENU COLOR border       * #00000000 #00000000 none
MENU COLOR sel          * #ffffffff #FF5255FF *

LABEL linux
    MENU LABEL Boot {self.boot_title} {kernel_ver} {self.arch}
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd root=live:CDLABEL=VOID_LIVE ro init=/sbin/init rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} {self.boot_cmdline}

LABEL linuxram
    MENU LABEL Boot {self.boot_title} {kernel_ver} {self.arch} (RAM)
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd root=live:CDLABEL=VOID_LIVE ro init=/sbin/init rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} rd.live.ram {self.boot_cmdline}

LABEL linuxnogfx
    MENU LABEL Boot {self.boot_title} {kernel_ver} {self.arch} (graphics disabled)
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd root=live:CDLABEL=VOID_LIVE ro init=/sbin/init rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} nomodeset {self.boot_cmdline}

LABEL linuxa11y
    MENU LABEL Boot {self.boot_title} {kernel_ver} {self.arch} with ^speech
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd root=live:CDLABEL=VOID_LIVE ro init=/sbin/init rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} live.accessibility live.autologin {self.boot_cmdline}

LABEL c
    MENU LABEL Boot first HD found by BIOS
    COM32 chain.c32
    APPEND hd0

LABEL reboot
    MENU LABEL Re^boot
    COM32 reboot.c32

LABEL poweroff
    MENU LABEL ^Power Off
    COM32 poweroff.c32
"""
            with open(f"{self.iso_dir}/boot/isolinux/isolinux.cfg", "w") as f:
                f.write(isolinux_cfg)

        # Setup GRUB (for UEFI boot)
        # Create grub.cfg (the entry point)
        grub_cfg = """insmod usbms
insmod usb_keyboard
insmod part_gpt
insmod part_msdos
insmod fat
insmod iso9660
insmod udf
insmod ext2
insmod reiserfs
insmod ntfs
insmod hfsplus
insmod linux
insmod chain
search --file --no-floppy --set=voidlive "/boot/grub/grub_void.cfg"
source "(${voidlive})/boot/grub/grub_void.cfg"
"""
        with open(f"{self.iso_dir}/boot/grub/grub.cfg", "w") as f:
            f.write(grub_cfg)

        # Create grub_void.cfg (the actual menu)
        grub_void_cfg = f"""export voidlive

set pager="1"
set locale_dir="(${{voidlive}})/boot/grub/locale"

if [ -e "${{prefix}}/${{grub_cpu}}-${{grub_platform}}/all_video.mod" ]; then
    insmod all_video
else
    insmod efi_gop
    insmod efi_uga
    insmod video_bochs
    insmod video_cirrus
fi

insmod font

if loadfont "(${{voidlive}})/boot/grub/fonts/unicode.pf2" ; then
    insmod gfxterm
    set gfxmode="auto"

    terminal_input console
    terminal_output gfxterm

    insmod png
    # background_image "(${{voidlive}})/boot/isolinux/splash.png"
fi

# Set default menu entry
default=linux
timeout=15
timeout_style=menu

# GRUB init tune for accessibility
play 600 988 1 1319 4

if [ cpuid -l ]; then
    menuentry "{self.boot_title} {kernel_ver} {self.arch}" --id linux {{
        set gfxpayload="keep"
        linux ($voidlive)/boot/vmlinuz \\
            root=live:CDLABEL=VOID_LIVE ro init=/sbin/init \\
            rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 gpt add_efi_memmap \\
            vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} {self.boot_cmdline}
        initrd ($voidlive)/boot/initrd
    }}

    menuentry "{self.boot_title} {kernel_ver} {self.arch} (RAM)" --id linuxram {{
        set gfxpayload="keep"
        linux ($voidlive)/boot/vmlinuz \\
            root=live:CDLABEL=VOID_LIVE ro init=/sbin/init \\
            rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 gpt add_efi_memmap \\
            vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} rd.live.ram {self.boot_cmdline}
        initrd ($voidlive)/boot/initrd
    }}

    menuentry "{self.boot_title} {kernel_ver} {self.arch} (graphics disabled)" --id linuxnogfx {{
        set gfxpayload="keep"
        linux ($voidlive)/boot/vmlinuz \\
            root=live:CDLABEL=VOID_LIVE ro init=/sbin/init \\
            rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 gpt add_efi_memmap \\
            vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} nomodeset {self.boot_cmdline}
        initrd ($voidlive)/boot/initrd
    }}

    menuentry "{self.boot_title} {kernel_ver} {self.arch} with speech" --id linuxa11y --hotkey s {{
        set gfxpayload="keep"
        linux ($voidlive)/boot/vmlinuz \\
            root=live:CDLABEL=VOID_LIVE ro init=/sbin/init \\
            rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 gpt add_efi_memmap \\
            vconsole.unicode=1 vconsole.keymap={self.keymap} locale.LANG={self.locale} live.accessibility live.autologin {self.boot_cmdline}
        initrd ($voidlive)/boot/initrd
    }}
fi

if [ "${{grub_platform}}" == "efi" ]; then
    menuentry 'UEFI Firmware Settings' --hotkey f --id uefifw {{
        fwsetup
    }}
fi

menuentry "System restart" --hotkey b --id restart {{
    echo "System rebooting..."
    reboot
}}

menuentry "System shutdown" --hotkey p --id poweroff {{
    echo "System shutting down..."
    halt
}}
"""
        with open(f"{self.iso_dir}/boot/grub/grub_void.cfg", "w") as f:
            f.write(grub_void_cfg)

        # Copy GRUB fonts
        os.makedirs(f"{self.iso_dir}/boot/grub/fonts", exist_ok=True)
        grub_font = f"{self.output_dir}/usr/share/grub/unicode.pf2"
        if os.path.exists(grub_font):
            shutil.copy(grub_font, f"{self.iso_dir}/boot/grub/fonts/")

        # Generate GRUB EFI images
        if self.arch.startswith('x86_64') or self.arch.startswith('i686'):
            os.makedirs(f"{self.iso_dir}/boot/efi", exist_ok=True)
            
            # We need to run grub-mkstandalone inside the chroot to generate the EFI binaries
            # This is how void-mklive does it
            
            # For x86_64-efi
            grub_mkstandalone_cmd = [
                "grub-mkstandalone",
                "--directory=/usr/lib/grub/x86_64-efi",
                "--format=x86_64-efi",
                "--output=/mnt/iso/boot/efi/bootx64.efi",
                "boot/grub/grub.cfg"
            ]
            
            # For i386-efi
            grub_mkstandalone_cmd_32 = [
                "grub-mkstandalone",
                "--directory=/usr/lib/grub/i386-efi",
                "--format=i386-efi",
                "--output=/mnt/iso/boot/efi/bootia32.efi",
                "boot/grub/grub.cfg"
            ]
            
            # Run via proot
            # We need to make sure grub.cfg is accessible from the root of the chroot
            # so grub-mkstandalone can find it. We'll copy it temporarily.
            CommandRunner.run(['mkdir', '-p', f"{self.output_dir}/boot/grub"])
            CommandRunner.run(['cp', f"{self.iso_dir}/boot/grub/grub.cfg", f"{self.output_dir}/boot/grub/grub.cfg"])
            
            proot_cmd = [
                self.proot_bin, '-r', self.output_dir, '-0', '-w', '/',
                '-b', f"{os.path.abspath(self.iso_dir)}:/mnt/iso",
                '/bin/sh', '-c', ' '.join(grub_mkstandalone_cmd)
            ]
            
            proot_cmd_32 = [
                self.proot_bin, '-r', self.output_dir, '-0', '-w', '/',
                '-b', f"{os.path.abspath(self.iso_dir)}:/mnt/iso",
                '/bin/sh', '-c', ' '.join(grub_mkstandalone_cmd_32)
            ]
            
            try:
                CommandRunner.run(proot_cmd)
                CommandRunner.run(proot_cmd_32)
                
                # Clean up the temporary grub.cfg
                CommandRunner.run(['rm', '-rf', f"{self.output_dir}/boot/grub"])
                
                # Create the EFI boot image (efiboot.img) for xorriso
                # This is a FAT filesystem containing the EFI binaries
                efiboot_img = f"{self.iso_dir}/boot/grub/efiboot.img"
                
                # Create a 32MB empty file (void-mklive uses 32M)
                CommandRunner.run(['truncate', '-s', '32M', efiboot_img])
                
                # Format as FAT12
                # We need mkfs.fat, let's install dosfstools in rootfs if needed
                # Use static xbps-install to avoid DNS issues in proot
                cmd = [
                    xbps_install,
                    '-S',
                    '-r', self.output_dir,
                    '-R', self.config.get('repository', 'https://repo-default.voidlinux.org/current'),
                    '-y', 'dosfstools', 'mtools'
                ]
                CommandRunner.run(cmd)
                
                # Format and copy files using mtools inside chroot
                setup_efi_cmd = f"""
                mkfs.fat -F 12 -S 512 -n "grub_uefi" /mnt/iso/boot/grub/efiboot.img
                mmd -i /mnt/iso/boot/grub/efiboot.img ::/EFI
                mmd -i /mnt/iso/boot/grub/efiboot.img ::/EFI/BOOT
                mcopy -i /mnt/iso/boot/grub/efiboot.img /mnt/iso/boot/efi/bootx64.efi ::/EFI/BOOT/BOOTX64.EFI
                mcopy -i /mnt/iso/boot/grub/efiboot.img /mnt/iso/boot/efi/bootia32.efi ::/EFI/BOOT/BOOTIA32.EFI
                """
                
                proot_efi_cmd = [
                    self.proot_bin, '-r', self.output_dir, '-0',
                    '-b', f"{os.path.abspath(self.iso_dir)}:/mnt/iso",
                    '/bin/sh', '-c', setup_efi_cmd
                ]
                CommandRunner.run(proot_efi_cmd)
                
            except Exception as e:
                print(f"Failed to setup EFI boot: {e}")
                # Create a dummy efiboot.img so xorriso doesn't fail if this step fails
                efiboot_img = f"{self.iso_dir}/boot/grub/efiboot.img"
                if not os.path.exists(efiboot_img):
                    CommandRunner.run(['dd', 'if=/dev/zero', f'of={efiboot_img}', 'bs=1M', 'count=4'])

        # Copy kernel and initramfs
        for file in os.listdir(boot_dir):
            if file.startswith("vmlinuz"):
                shutil.copy(f"{boot_dir}/{file}", f"{self.iso_dir}/boot/vmlinuz")
            elif file.startswith("initramfs"):
                shutil.copy(f"{boot_dir}/{file}", f"{self.iso_dir}/boot/initrd")

        print("Bootloader setup complete.")
