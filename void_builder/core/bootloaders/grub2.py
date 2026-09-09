import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

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

    def _get_template_placeholders(self) -> Dict[str, str]:
        keymap = self._cfg_get("keymap", "us")
        locale = self._cfg_get("locale", "en_US.UTF-8")
        boot_cmdline = self._cfg_get("boot_cmdline", "")
        boot_title = self._cfg_get("boot_title", "Void Linux")
        desktop = str(self._cfg_get("desktop", "")).upper()
        arch = self._cfg_get("platform_specific.architecture", "x86_64")
        iso_label = self._cfg_get("system.iso_label", "VOID_MODERN")
        live_user = self._cfg_get("live_user")
        if not live_user:
            users = self._cfg_get("customizations.users", [])
            for u in users:
                if hasattr(u, "_data"):
                    u = u._data
                if isinstance(u, dict) and u.get("name") not in ("root", ""):
                    live_user = u.get("name")
                    break
        live_user = live_user or "void"

        return {
            "@@VOL_ID@@": iso_label,
            "@@ISO_LABEL@@": iso_label,
            "@@BOOT_TITLE@@": boot_title,
            "@@DISTRO_NAME@@": boot_title,
            "@@DESKTOP@@": desktop,
            "@@ARCH@@": arch,
            "@@KERNEL_FILE@@": "vmlinux" if arch.lower().startswith("aarch64") else "vmlinuz",
            "@@KERNEL_PARAMS@@": boot_cmdline,
            "@@BOOT_CMDLINE@@": boot_cmdline,
            "@@KEYMAP@@": keymap,
            "@@LOCALE@@": locale,
            "@@LIVE_USER@@": live_user,
            "@@SPLASHIMAGE@@": "splash.png"
        }

    def _generate_grub_entries(self) -> str:
        keymap = self._cfg_get("keymap", "us")
        locale = self._cfg_get("locale", "en_US.UTF-8")
        boot_cmdline = self._cfg_get("boot_cmdline", "")
        boot_title = self._cfg_get("boot_title", "Void Linux")
        kver = getattr(self, "kernel_version", "linux")

        arch = self._cfg_get("platform_specific.architecture", "x86_64")
        is_aarch64 = arch.lower().startswith("aarch64")
        kernel_file = "vmlinux" if is_aarch64 else "vmlinuz"
        iso_label = self._cfg_get("system.iso_label", "VOID_MODERN")

        base_append = (
            f"root=live:CDLABEL={iso_label} ro init=/sbin/init "
            f"rd.luks=0 rd.md=0 rd.dm=0 loglevel=4 gpt add_efi_memmap "
            f"vconsole.unicode=1 vconsole.keymap={keymap} "
            f"locale.LANG={locale} {boot_cmdline}"
        ).strip()

        # Helper to generate a single menuentry
        def write_entry(title_suffix: str, entry_id: str, extra_cmdline: str = "") -> str:
            suffix_str = f" {title_suffix}" if title_suffix else ""
            full_title = f"{boot_title} {kver}{suffix_str} ({arch})"
            cmd = f"{base_append} {extra_cmdline}".strip()
            ent = f'menuentry "{full_title}" --id "{entry_id}" {{\n'
            ent += '    set gfxpayload="keep"\n'
            ent += f'    linux (${{voidlive}})/boot/{kernel_file} {cmd}\n'
            ent += f'    initrd (${{voidlive}})/boot/initrd\n'
            ent += '}\n\n'
            return ent

        entries = ""
        # Main entries
        entries += write_entry("", "linux")
        entries += write_entry("(RAM)", "linuxram", "rd.live.ram")
        entries += write_entry("(graphics disabled)", "linuxnogfx", "nomodeset")
        entries += write_entry("(Debug Mode)", "linuxdebug", "rd.debug loglevel=7")
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
                
                dtb_line = f"        devicetree (${{voidlive}})/boot/dtbs/{p_dtb}\n" if p_dtb else ""
                
                entries += f'\nsubmenu "{boot_title} for {p_name} >" --id platform-{platform} {{\n'
                
                def write_plat_entry(title_suffix: str, entry_id: str, extra_cmdline: str = "") -> str:
                    suffix_str = f" {title_suffix}" if title_suffix else ""
                    full_title = f"{boot_title} {kver}{suffix_str} ({arch})"
                    cmd = f"{base_append} {p_cmdline} {extra_cmdline}".strip()
                    ent = f'    menuentry "{full_title}" --id "{entry_id}" {{\n'
                    ent += '        set gfxpayload="keep"\n'
                    ent += f'        linux (${{voidlive}})/boot/{kernel_file} {cmd}\n'
                    ent += f'        initrd (${{voidlive}})/boot/initrd\n'
                    ent += dtb_line
                    ent += '    }\n'
                    return ent
                
                entries += write_plat_entry(f"for {p_name}", f"linux-{platform}")
                entries += write_plat_entry(f"for {p_name} (RAM)", f"linuxram-{platform}", "rd.live.ram")
                entries += write_plat_entry(f"for {p_name} (graphics disabled)", f"linuxnogfx-{platform}", "nomodeset")
                entries += write_plat_entry(f"for {p_name} with speech", f"linuxa11y-{platform}", "live.accessibility live.autologin")
                entries += '}\n'

        # Memtest entry (only for x86 architectures)
        if not is_aarch64:
            entries += '\n'
            entries += 'if [ "${grub_platform}" = "efi" ]; then\n'
            entries += '    menuentry "Run Memtest86+ (RAM test)" --id memtest {\n'
            entries += '        set gfxpayload="keep"\n'
            entries += '        linux (${voidlive})/boot/memtest.efi\n'
            entries += '    }\n'
            entries += 'else\n'
            entries += '    menuentry "Run Memtest86+ (RAM test)" --id memtest {\n'
            entries += '        set gfxpayload="keep"\n'
            entries += '        linux (${voidlive})/boot/memtest.bin\n'
            entries += '    }\n'
            entries += 'fi\n'

        # UEFI firmware and power entries
        entries += '\n'
        entries += 'if [ "${grub_platform}" = "efi" ]; then\n'
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

        # Copy custom GRUB theme to Live ISO
        custom_theme_src = resolve_from_project("configs/custom_files/grub")
        if custom_theme_src.exists():
            dest_themes = grub_dir / "themes"
            dest_themes.mkdir(parents=True, exist_ok=True)
            shutil.copytree(custom_theme_src, dest_themes, dirs_exist_ok=True)

        # Check and render templates from configs/boot/templates
        config_template = resolve_from_project("configs/boot/templates/config.cfg.in")
        loopback_template = resolve_from_project("configs/boot/templates/loopback.cfg.in")
        grub_template = resolve_from_project("configs/boot/templates/grub.cfg.in")
        placeholders = self._get_template_placeholders()

        if config_template.exists():
            config_text = config_template.read_text(encoding="utf-8")
            for k, v in placeholders.items():
                config_text = config_text.replace(k, str(v))
            (grub_dir / "config.cfg").write_text(config_text, encoding="utf-8")

        if loopback_template.exists():
            loopback_text = loopback_template.read_text(encoding="utf-8")
            for k, v in placeholders.items():
                loopback_text = loopback_text.replace(k, str(v))
            (grub_dir / "loopback.cfg").write_text(loopback_text, encoding="utf-8")

        # If main grub.cfg is still missing, render from template or use grub_void.cfg
        if not (grub_dir / "grub.cfg").exists():
            if grub_template.exists():
                grub_text = grub_template.read_text(encoding="utf-8")
                for k, v in placeholders.items():
                    grub_text = grub_text.replace(k, str(v))
                (grub_dir / "grub.cfg").write_text(grub_text, encoding="utf-8")
            elif (grub_dir / "grub_void.cfg").exists():
                shutil.copy2(grub_dir / "grub_void.cfg", grub_dir / "grub.cfg")

        logger.info("[GRUB2] GRUB EFI configured")
        return True

    @staticmethod
    def _host_environment(toolchain_host: Path) -> Dict[str, str]:
        env = os.environ.copy()
        lib_dir = toolchain_host / "usr/lib"
        env["PATH"] = f"{toolchain_host / 'usr/bin'}:{toolchain_host / 'usr/sbin'}:{env.get('PATH', '')}"
        env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
        # glibc's iconv modules must come from the same isolated libc. Otherwise
        # mtools fails to load CP850 when the host has a different glibc layout.
        if (lib_dir / "gconv").is_dir():
            env["GCONV_PATH"] = str(lib_dir / "gconv")
        return env

    @staticmethod
    def _run_host_command(command, env):
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        if result.returncode:
            raise Grub2BootloaderError(
                f"EFI command failed (exit {result.returncode}): {' '.join(command)}\n"
                f"{result.stdout or ''}\n{result.stderr or ''}"
            )
        return result

    def generate_boot_image(self, workdir: Path, chroot_path: Optional[Path] = None, *, toolchain: Any = None, mode: str = "real") -> bool:
        """Generate EFI using this build's native tools and target GRUB modules."""
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

        if mode == "mock":
            logger.info("[GRUB2] [MOCK] Writing placeholder efiboot.img")
            efi_img_path.write_bytes(b"\x00" * (32 * 1024 * 1024))
            return True

        chroot = Path(chroot_path) if chroot_path else None
        
        # Copy grub.cfg to chroot so grub-mkstandalone can embed it
        if has_real_chroot:
            chroot_grub_dir = chroot / "boot" / "grub"
            chroot_grub_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workdir / "boot" / "grub" / "grub.cfg", chroot_grub_dir / "grub.cfg")

        # Copy unicode.pf2 to enable graphics
        fonts_dir = workdir / "boot" / "grub" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        
        chroot_font = chroot / "usr" / "share" / "grub" / "unicode.pf2" if chroot else None
        host_font = Path("/usr/share/grub/unicode.pf2")
        
        toolchain_font = Path(toolchain.host_dir) / "usr/share/grub/unicode.pf2" if getattr(toolchain, "host_dir", None) else None
        if toolchain_font and toolchain_font.is_file():
            shutil.copy2(toolchain_font, fonts_dir / "unicode.pf2")
        elif chroot_font and chroot_font.exists():
            shutil.copy2(chroot_font, fonts_dir / "unicode.pf2")
            logger.info("[GRUB2] Copied unicode.pf2 from chroot to enable graphical boot")
        elif host_font.exists():
            shutil.copy2(host_font, fonts_dir / "unicode.pf2")
            logger.info("[GRUB2] Copied unicode.pf2 from host to enable graphical boot")
        else:
            logger.warning("[GRUB2] WARNING: unicode.pf2 not found! GRUB splash screen will NOT load.")

        arch = self._cfg_get("platform_specific.architecture", "x86_64")
        arch_lower = arch.lower()

        builds = []
        if arch_lower.startswith(("i686", "x86_64")):
            builds.append(("i386-efi", "BOOTIA32.EFI"))
            builds.append(("x86_64-efi", "BOOTX64.EFI"))
        elif arch_lower.startswith(("aarch64", "arm64")):
            builds.append(("arm64-efi", "BOOTAA64.EFI"))

        if not builds:
            raise Grub2BootloaderError(f"Unsupported EFI architecture: {arch}")
        required_efi = "BOOTX64.EFI" if arch_lower.startswith("x86_64") else builds[0][1]
        built_loaders = set()

        chroot_cmd = ["chroot"]
        import os
        if os.geteuid() != 0:
            chroot_cmd = ["sudo", "chroot"]

        # 1. Create 32MB FAT image directly on target path
        with open(efi_img_path, "wb") as f:
            f.write(b"\x00" * (32 * 1024 * 1024))

        # The caller supplies the resolved build directories (including /tmp fallback).
        # Never search the legacy project-level build_host or infer it from ISO staging.
        toolchain_host = getattr(toolchain, "host_dir", None)
        toolchain_target = getattr(toolchain, "target_dir", None)
        if toolchain_host is None or toolchain_target is None:
            raise Grub2BootloaderError("Real EFI generation requires the current build toolchain")
        toolchain_host = Path(toolchain_host)
        toolchain_target = Path(toolchain_target)
        host_env = self._host_environment(toolchain_host)
        has_host_mtools = all(
            shutil.which(tool, path=host_env["PATH"])
            for tool in ("mkfs.fat", "mmd", "mcopy")
        )

        if has_host_mtools:
            self._run_host_command(["mkfs.fat", "-F16", "-S", "512", "-n", "GRUB_UEFI", str(efi_img_path)], host_env)
            self._run_host_command(["mmd", "-i", str(efi_img_path), "::/EFI", "::/EFI/BOOT"], host_env)

            for grub_arch, efi_name in builds:
                logger.info(f"[GRUB2] Building EFI loader for {grub_arch} ({efi_name})...")
                efi_out = workdir / "boot" / "grub" / efi_name
                # Use void-target for modules and void-host for the binary, exactly like void-mklive
                grub_mod_dir = toolchain_target / "usr" / "lib" / "grub" / grub_arch
                host_grub_mk = next(
                    (toolchain_host / "usr" / folder / "grub-mkstandalone"
                     for folder in ("bin", "sbin")
                     if (toolchain_host / "usr" / folder / "grub-mkstandalone").is_file()),
                    toolchain_host / "usr" / "bin" / "grub-mkstandalone",
                )

                efi_out.unlink(missing_ok=True)
                built = False

                if host_grub_mk.exists() and grub_mod_dir.exists():
                    cmd_host = [
                        str(host_grub_mk),
                        f"--directory={grub_mod_dir}",
                        f"--format={grub_arch}",
                        f"--output={efi_out}",
                        f"boot/grub/grub.cfg={workdir / 'boot' / 'grub' / 'grub.cfg'}"
                    ]
                    res = subprocess.run(cmd_host, env=host_env, capture_output=True, text=True, timeout=180)
                    if res.returncode == 0 and efi_out.exists():
                        built = True

                if not built and has_real_chroot:
                    from void_builder.utils.lib import copy_qemu_user_binary
                    copy_qemu_user_binary(arch, chroot)
                    (chroot / "tmp").mkdir(parents=True, exist_ok=True)
                    (chroot / "tmp" / efi_name).unlink(missing_ok=True)
                    cmd_chroot = [
                        *chroot_cmd, str(chroot), "sh", "-c",
                        f"grub-mkstandalone --directory=/usr/lib/grub/{grub_arch} --format={grub_arch} --output=/tmp/{efi_name} boot/grub/grub.cfg"
                    ]
                    res = subprocess.run(cmd_chroot, capture_output=True, text=True, timeout=180)
                    if res.returncode == 0 and (chroot / "tmp" / efi_name).exists():
                        shutil.copy2(chroot / "tmp" / efi_name, efi_out)
                        (chroot / "tmp" / efi_name).unlink(missing_ok=True)
                        built = True

                if built and efi_out.exists():
                    self._run_host_command(["mcopy", "-i", str(efi_img_path), str(efi_out), f"::/EFI/BOOT/{efi_name}"], host_env)
                    built_loaders.add(efi_name)
                    logger.info(f"[GRUB2] Successfully built and embedded {efi_name} into efiboot.img")
                else:
                    logger.warning(f"[GRUB2] Skipping {grub_arch} due to build failure (missing libs or unsupported).")

            if required_efi not in built_loaders:
                efi_img_path.unlink(missing_ok=True)
                raise Grub2BootloaderError(f"Failed to generate required EFI loader {required_efi} using {toolchain_target}")
            logger.info(f"[GRUB2] efiboot.img created successfully: {efi_img_path}")
            return True

        if not has_real_chroot:
            efi_img_path.unlink(missing_ok=True)
            raise Grub2BootloaderError(f"Missing FAT image tools in {toolchain_host} or host PATH")

        # Fallback to in-chroot generation if host tools missing
        (chroot / "tmp").mkdir(parents=True, exist_ok=True)
        efi_img_chroot = "/tmp/efiboot.img"
        efi_img_host = chroot / "tmp" / "efiboot.img"
        with open(efi_img_host, "wb") as f:
            f.write(b"\x00" * (32 * 1024 * 1024))

        from void_builder.utils.lib import copy_qemu_user_binary
        copy_qemu_user_binary(arch, chroot)

        fat_cmds = [
            f"mkfs.fat -F16 -S 512 -n grub_uefi {efi_img_chroot}",
            f"mmd -i {efi_img_chroot} ::/EFI ::/EFI/BOOT",
        ]

        for grub_arch, efi_name in builds:
            logger.info(f"[GRUB2] Building EFI loader for {grub_arch} ({efi_name})...")
            (chroot / "tmp" / efi_name).unlink(missing_ok=True)
            cmd_grub = [
                *chroot_cmd, str(chroot), "sh", "-c",
                f"grub-mkstandalone "
                f"--directory=\"/usr/lib/grub/{grub_arch}\" "
                f"--format=\"{grub_arch}\" "
                f"--output=\"/tmp/{efi_name}\" "
                f"\"boot/grub/grub.cfg\""
            ]
            res = subprocess.run(cmd_grub, capture_output=True, text=True, timeout=180)
            if res.returncode != 0 or not (chroot / "tmp" / efi_name).is_file():
                logger.warning(f"[GRUB2] Skipping {grub_arch} due to build failure (missing libs or unsupported).")
                continue

            built_loaders.add(efi_name)
            fat_cmds.append(f"mcopy -i {efi_img_chroot} /tmp/{efi_name} ::/EFI/BOOT/{efi_name}")

        if required_efi not in built_loaders:
            efi_img_path.unlink(missing_ok=True)
            raise Grub2BootloaderError(f"Failed to generate required EFI loader {required_efi}")

        logger.info(f"[GRUB2] Populating efiboot.img via mkfs.fat/mcopy...")
        cmd_fat = [*chroot_cmd, str(chroot), "sh", "-c", " && ".join(fat_cmds)]
        res = subprocess.run(cmd_fat, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            raise Grub2BootloaderError(f"FAT image creation failed: {res.stderr}")

        shutil.copy2(efi_img_host, efi_img_path)
        logger.info(f"[GRUB2] efiboot.img created successfully: {efi_img_path}")

        efi_img_host.unlink(missing_ok=True)
        return True

    def validate(self, workdir: Path) -> bool:
        return (workdir / "boot" / "grub" / "grub.cfg").exists()
