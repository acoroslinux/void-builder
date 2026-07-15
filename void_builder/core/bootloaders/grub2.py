import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("Grub2Bootloader")


class Grub2BootloaderError(Exception):
    pass


class Grub2Bootloader:
    def __init__(self, config: Any, root_device_id: str, iso_uuid: str = "", kernel_version: str = "linux") -> None:
        self.config = config
        self.root_device_id = root_device_id
        self.iso_uuid = iso_uuid
        self.kernel_version = kernel_version

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        if not self.config:
            return default

        try:
            # Helper function to get nested value
            def get_nested(cfg, path):
                parts = path.split(".")
                current = cfg
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    elif hasattr(current, "get"):
                        current = current.get(part)
                    else:
                        return None
                return current

            # Try key directly (might be dot-path or top-level)
            val = get_nested(self.config, key)
            if val is not None:
                return val

            # Try iso.<key>
            if not key.startswith("iso."):
                val = get_nested(self.config, f"iso.{key}")
                if val is not None:
                    return val

            # Try customizations.<key>
            if not key.startswith("customizations."):
                val = get_nested(self.config, f"customizations.{key}")
                if val is not None:
                    return val

            # Try system.<key>
            if not key.startswith("system."):
                val = get_nested(self.config, f"system.{key}")
                if val is not None:
                    return val

            return default
        except Exception:
            return default

    def _generate_grub_entries(self) -> str:
        keymap = self._cfg_get("keymap", "us")
        locale = self._cfg_get("locale", "en_US.UTF-8")
        boot_cmdline = self._cfg_get("boot_cmdline", "")
        boot_title = self._cfg_get("boot_title", "Void Linux")
        kver = getattr(self, "kernel_version", "linux")

        arch = self._cfg_get("platform_specific.architecture", "x86_64")
        is_aarch64 = arch.lower().startswith("aarch64")
        kernel_file = "vmlinux" if is_aarch64 else "vmlinuz"
        iso_label = self._cfg_get("system.iso_label", "VOID_LIVE")

        base_append = (
            f"root=live:CDLABEL={iso_label} ro init=/sbin/init "
            f"rd.luks=0 rd.md=0 rd.dm=0 loglevel=3 gpt add_efi_memmap "
            f"vconsole.unicode=1 vconsole.keymap={keymap} "
            f"locale.LANG={locale} splash quiet rd.plymouth=1 vt.global_cursor_default=0 {boot_cmdline}"
        ).strip()

        # Helper to generate a single menuentry
        def write_entry(title_suffix: str, entry_id: str, extra_cmdline: str = "") -> str:
            full_title = f"{boot_title} {kver} {title_suffix}({arch})"
            cmd = f"{base_append} {extra_cmdline}".strip()
            ent = f'menuentry "{full_title}" --id "{entry_id}" {{\n'
            ent += '    set gfxpayload="keep"\n'
            ent += f'    linux /boot/{kernel_file} {cmd}\n'
            ent += f'    initrd /boot/initrd\n'
            ent += '}\n\n'
            return ent

        entries = ""
        # Main entries
        entries += write_entry("", "linux")
        entries += write_entry("(RAM)", "linuxram", "rd.live.ram")
        entries += write_entry("(graphics disabled)", "linuxnogfx", "nomodeset")
        entries += write_entry("with speech", "linuxa11y", "live.accessibility live.autologin")
        entries += write_entry("with speech (RAM)", "linuxa11yram", "live.accessibility live.autologin rd.live.ram")
        entries += write_entry("with speech (graphics disabled)", "linuxa11ynogfx", "live.accessibility live.autologin nomodeset")

        # Platform-specific submenus
        platforms_config = self._cfg_get("platforms_config", {})
        if is_aarch64 and platforms_config:
            for platform, plat_info in platforms_config.items():
                p_name = plat_info.get("name", platform)
                p_cmdline = plat_info.get("cmdline", "")
                p_dtb = plat_info.get("dtb", "")
                
                dtb_line = f"        devicetree /boot/dtbs/{p_dtb}\n" if p_dtb else ""
                
                entries += f'\nsubmenu "{boot_title} for {p_name} >" --id platform-{platform} {{\n'
                
                def write_plat_entry(title_suffix: str, entry_id: str, extra_cmdline: str = "") -> str:
                    full_title = f"{boot_title} {kver} {title_suffix}({arch})"
                    cmd = f"{base_append} {p_cmdline} {extra_cmdline}".strip()
                    ent = f'    menuentry "{full_title}" --id "{entry_id}" {{\n'
                    ent += '        set gfxpayload="keep"\n'
                    ent += f'        linux /boot/{kernel_file} {cmd}\n'
                    ent += f'        initrd /boot/initrd\n'
                    ent += dtb_line
                    ent += '    }\n'
                    return ent
                
                entries += write_plat_entry(f"for {p_name} ", f"linux-{platform}")
                entries += write_plat_entry(f"for {p_name} (RAM) ", f"linuxram-{platform}", "rd.live.ram")
                entries += write_plat_entry(f"for {p_name} (graphics disabled) ", f"linuxnogfx-{platform}", "nomodeset")
                entries += write_plat_entry(f"for {p_name} with speech ", f"linuxa11y-{platform}", "live.accessibility live.autologin")
                entries += '}\n'

        # Memtest entry (only for x86 architectures)
        if not is_aarch64:
            entries += '\n'
            entries += 'if [ "${grub_platform}" == "efi" ]; then\n'
            entries += '    menuentry "Run Memtest86+ (RAM test)" --id memtest {\n'
            entries += '        set gfxpayload="keep"\n'
            entries += '        linux /boot/memtest.efi\n'
            entries += '    }\n'
            entries += 'else\n'
            entries += '    menuentry "Run Memtest86+ (RAM test)" --id memtest {\n'
            entries += '        set gfxpayload="keep"\n'
            entries += '        linux /boot/memtest.bin\n'
            entries += '    }\n'
            entries += 'fi\n'

        # UEFI firmware and power entries
        entries += '\n'
        entries += 'if [ "${grub_platform}" == "efi" ]; then\n'
        entries += "    menuentry 'UEFI Firmware Settings' --hotkey f --id uefifw {\n"
        entries += "        fwsetup\n"
        entries += "    }\n"
        entries += 'fi\n\n'

        entries += 'menuentry "System restart" --hotkey b --id restart {\n'
        entries += '    echo "System rebooting..."\n'
        entries += '    reboot\n'
        entries += '}\n\n'

        entries += 'menuentry "System shutdown" --hotkey p --id poweroff {\n'
        entries += '    echo "System shutting down..."\n'
        entries += '    halt\n'
        entries += '}\n'

        return entries

    def prepare_files(self, workdir: Path) -> bool:
        """Prepare GRUB configuration files."""
        logger.info("[GRUB2] Preparing EFI boot files...")
        
        grub_dir = workdir / "boot" / "grub"
        grub_dir.mkdir(parents=True, exist_ok=True)
        mklive_dir = resolve_from_project("configs/assets")

        pre_file = mklive_dir / "grub" / "grub_void.cfg.pre"
        post_file = mklive_dir / "grub" / "grub_void.cfg.post"

        cfg_content = ""
        if pre_file.exists():
            cfg_content = pre_file.read_text(encoding="utf-8")
            cfg_content = cfg_content.replace("@@SPLASHIMAGE@@", "splash.png")

        # Add entries
        cfg_content += self._generate_grub_entries()

        if post_file.exists():
            cfg_content += post_file.read_text(encoding="utf-8")

        (grub_dir / "grub_void.cfg").write_text(cfg_content, encoding="utf-8")

        # Copy main grub.cfg
        main_cfg = mklive_dir / "grub" / "grub.cfg"
        if main_cfg.exists():
            shutil.copy2(main_cfg, grub_dir / "grub.cfg")

        # Copy splash image if any
        splash_image_path = self._cfg_get("splash_image", "")
        splash_src = Path(splash_image_path) if splash_image_path else mklive_dir / "data" / "splash.png"
        if splash_src.exists():
            shutil.copy2(splash_src, grub_dir / "splash.png")

        logger.info("[GRUB2] GRUB EFI configured")
        return True

    def generate_boot_image(self, workdir: Path, chroot_path: Path = None) -> bool:
        """Generate efiboot.img using grub-mkstandalone inside chroot (or simulation)."""
        logger.info("[GRUB2] Generating UEFI boot image (efiboot.img)...")

        efi_img_path = workdir / "boot" / "grub" / "efiboot.img"
        efi_img_path.parent.mkdir(parents=True, exist_ok=True)

        has_real_chroot = bool(
            chroot_path
            and Path(chroot_path).exists()
            and (
                (Path(chroot_path) / "usr" / "bin" / "grub-mkstandalone").exists()
                or (Path(chroot_path) / "usr" / "sbin" / "grub-mkstandalone").exists()
            )
        )

        if not has_real_chroot:
            logger.info("[GRUB2] [MOCK] No real chroot — writing placeholder efiboot.img")
            efi_img_path.write_bytes(b"\x00" * (32 * 1024 * 1024))
            return True

        chroot = Path(chroot_path)
        
        # Copy grub.cfg to chroot so grub-mkstandalone can embed it
        chroot_grub_dir = chroot / "boot" / "grub"
        chroot_grub_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workdir / "boot" / "grub" / "grub.cfg", chroot_grub_dir / "grub.cfg")

        arch = self._cfg_get("platform_specific.architecture", "x86_64")
        arch_lower = arch.lower()

        builds = []
        if arch_lower.startswith(("i686", "x86_64")):
            builds.append(("i386-efi", "BOOTIA32.EFI"))
            builds.append(("x86_64-efi", "BOOTX64.EFI"))
        elif arch_lower.startswith(("aarch64", "arm64")):
            builds.append(("arm64-efi", "BOOTAA64.EFI"))

        chroot_cmd = ["chroot"]
        import os
        if os.geteuid() != 0:
            chroot_cmd = ["sudo", "chroot"]

        efi_img_chroot = "/tmp/efiboot.img"
        efi_img_host = chroot / "tmp" / "efiboot.img"

        # Create exact 32MB FAT image as void-mklive does
        with open(efi_img_host, "wb") as f:
            f.write(b"\x00" * (32 * 1024 * 1024))

        fat_cmds = [
            f"mkfs.fat -F12 -S 512 -n grub_uefi {efi_img_chroot}",
            f"mmd -i {efi_img_chroot} ::/EFI ::/EFI/BOOT",
        ]

        for grub_arch, efi_name in builds:
            logger.info(f"[GRUB2] Building EFI loader for {grub_arch} ({efi_name})...")
            cmd_grub = [
                *chroot_cmd, str(chroot), "bash", "-c",
                f"grub-mkstandalone "
                f"--directory=\"/usr/lib/grub/{grub_arch}\" "
                f"--format=\"{grub_arch}\" "
                f"--output=\"/tmp/{efi_name}\" "
                f"\"boot/grub/grub.cfg\""
            ]
            
            res = subprocess.run(cmd_grub, capture_output=True, text=True, timeout=180)
            if res.returncode != 0:
                logger.warning(f"[GRUB2] Skipping {grub_arch} due to build failure (missing libs or unsupported).")
                continue

            fat_cmds.append(f"mcopy -i {efi_img_chroot} /tmp/{efi_name} ::/EFI/BOOT/{efi_name}")

        logger.info(f"[GRUB2] Populating efiboot.img via mkfs.fat/mcopy...")
        cmd_fat = [*chroot_cmd, str(chroot), "bash", "-c", " && ".join(fat_cmds)]
        res = subprocess.run(cmd_fat, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            raise Grub2BootloaderError(f"FAT image creation failed: {res.stderr}")

        shutil.copy2(efi_img_host, efi_img_path)
        logger.info(f"[GRUB2] efiboot.img created successfully: {efi_img_path}")

        efi_img_host.unlink(missing_ok=True)
        return True

    def validate(self, workdir: Path) -> bool:
        return (workdir / "boot" / "grub" / "grub.cfg").exists()
