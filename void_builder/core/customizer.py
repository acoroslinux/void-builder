import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from void_builder.core.chroot_manager import ChrootError, ChrootManager
from void_builder.core.path_utils import project_root, resolve_from_base, resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("SystemConfigurator")


class ConfigError(Exception):
    """Exception raised for system configuration errors."""

    pass


class SystemAction:
    """Base class for a configuration action."""

    def execute(self, chroot: ChrootManager, source_base: Path):
        raise NotImplementedError()


class OverlayAction(SystemAction):
    """Copy a full overlay directory onto the chroot (like airootfs)."""

    def __init__(self, overlay_dir: str):
        self.overlay_dir = overlay_dir

    def execute(self, chroot: ChrootManager, source_base: Path):
        overlay_path = resolve_from_base(source_base, self.overlay_dir)
        if not overlay_path.exists():
            logger.warning(
                f"[Overlay] Overlay directory not found: {overlay_path}"
            )
            return

        logger.info(f"[Overlay] Applying overlay from {overlay_path} to rootfs...")
        if chroot.mode == "real":
            chroot_path = chroot.chroot_path
            try:
                import subprocess
                import os

                cmd = ["cp", "-aT", str(overlay_path), str(chroot_path)]
                if os.geteuid() != 0:
                    cmd = ["sudo"] + cmd

                subprocess.run(cmd, check=True)
                
                # Fix ownership of copied system directories to be owned by root (0:0)
                chroot.run_command("chown -R 0:0 /etc 2>/dev/null || true")
                chroot.run_command("chown -R 0:0 /usr 2>/dev/null || true")
                chroot.run_command("chown -R 0:0 /boot 2>/dev/null || true")
                chroot.run_command("chown -R 0:0 /opt 2>/dev/null || true")
                
                # Fix directory permissions to 755 (rwxr-xr-x)
                chroot.run_command("find /etc /usr /boot /opt -type d -exec chmod 755 {} + 2>/dev/null || true")
                
                # Ensure sudo has the correct setuid permissions
                chroot.run_command("chmod 4755 /usr/bin/sudo 2>/dev/null || true")
            except Exception as e:
                logger.error(f"[Overlay] Failed to copy overlay: {e}")
        else:
            logger.info(f"    [Mock] Simulated overlay: cp -aT {overlay_path} /")


class FileAction(SystemAction):
    """Copy one file from a source path to a destination inside the chroot."""

    def __init__(self, src: str, dest: str, mode: Optional[str] = None):
        self.src = src
        self.dest = dest
        self.mode = mode

    def execute(self, chroot: ChrootManager, source_base: Path):
        src_full = resolve_from_base(source_base, self.src)
        dest_full = Path(self.dest)

        if not src_full.exists():
            logger.error(f"[Config] Source not found: {src_full}")
            return

        logger.info(f"  [File] {self.src} -> {self.dest}")

        if chroot.mode == "real":
            chroot.run_command(f"mkdir -p {dest_full.parent}")
            host_dest = chroot.chroot_path / self.dest.lstrip("/")
            
            import os
            import subprocess
            if os.geteuid() != 0:
                subprocess.run(["sudo", "mkdir", "-p", str(host_dest.parent)], check=True)
                subprocess.run(["sudo", "cp", "-a", str(src_full), str(host_dest)], check=True)
            else:
                host_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_full, host_dest)

            # Ensure the copied file is owned by root if inside system paths
            if self.dest.startswith(("/etc/", "/usr/", "/boot/")):
                chroot.run_command(f"chown 0:0 {self.dest}")

            if self.mode:
                chroot.run_command(f"chmod {self.mode} {self.dest}")

            # Mirror to existing users home directories if destination is in /etc/skel/
            if self.dest.startswith("/etc/skel/"):
                relative_path = self.dest[len("/etc/skel/"):]
                chroot_home = chroot.chroot_path / "home"
                if chroot_home.exists():
                    for user_dir in chroot_home.iterdir():
                        if user_dir.is_dir() and user_dir.name not in ["lost+found"]:
                            user_dest = user_dir / relative_path
                            if os.geteuid() != 0:
                                subprocess.run(["sudo", "mkdir", "-p", str(user_dest.parent)], check=True)
                                subprocess.run(["sudo", "cp", "-a", str(src_full), str(user_dest)], check=True)
                            else:
                                user_dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_full, user_dest)
                            
                            first_subpart = relative_path.split("/")[0]
                            chroot.run_command(f"chown -R {user_dir.name}:{user_dir.name} /home/{user_dir.name}/{first_subpart}")
                            if self.mode:
                                chroot.run_command(f"chmod {self.mode} /home/{user_dir.name}/{relative_path}")
        else:
            logger.info(f"    [Mock] Copy file: {self.src} -> {self.dest}")


class UserAction(SystemAction):
    """Create users and apply their related settings."""

    def __init__(self, user_config: Dict[str, Any]):
        self.user_config = user_config

    def execute(self, chroot: ChrootManager, source_base: Path):
        name = self.user_config.get("name")
        if not name:
            return

        groups = self.user_config.get("groups", [])
        password = self.user_config.get("password", "")

        logger.info(f"  [User] Creating user: {name}")

        if chroot.mode == "real":
            for group in groups:
                chroot.run_command(f"getent group {group} >/dev/null 2>&1 || groupadd {group}")

            groups_str = ",".join(groups)

            chroot.run_command(f"id -u {name} >/dev/null 2>&1 || useradd -m -s /bin/bash {name}")
            if groups_str:
                chroot.run_command(f"usermod -G {groups_str} {name}")

            chroot.run_command(f"mkdir -p /home/{name}")
            chroot.run_command(f"chown -R {name}:{name} /home/{name}")

            if password:
                chroot.run_command(f"echo '{name}:{password}' | chpasswd -c SHA512")

            if "wheel" in groups:
                chroot.run_command(
                    "mkdir -p /etc/sudoers.d && echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-wheel"
                )
        else:
            logger.info(f"    [Mock] Create user: {name} (groups: {groups})")


class ServiceAction(SystemAction):
    """Enable runit services."""

    def __init__(self, services: List[str]):
        self.services = services

    def execute(self, chroot: ChrootManager, source_base: Path):
        for srv in self.services:
            logger.info(f"  [Service] Enable {srv}")
            if chroot.mode == "real":
                runsvdir_default = chroot.chroot_path / "etc" / "runit" / "runsvdir" / "default"
                if not runsvdir_default.exists():
                    try:
                        import os
                        if os.geteuid() != 0:
                            import subprocess
                            subprocess.run(["sudo", "mkdir", "-p", str(runsvdir_default)], check=True)
                        else:
                            runsvdir_default.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logger.warning(f"  [Service] Could not create runsvdir directory: {e}")
                
                sv_dir = chroot.chroot_path / "etc" / "sv" / srv
                target_link = runsvdir_default / srv
                
                if sv_dir.exists():
                    try:
                        import os
                        import subprocess
                        
                        source_in_chroot = f"/etc/sv/{srv}"
                        
                        if os.geteuid() != 0:
                            subprocess.run(["sudo", "ln", "-sfn", source_in_chroot, str(target_link)], check=True)
                        else:
                            if target_link.is_symlink() or target_link.exists():
                                target_link.unlink()
                            os.symlink(source_in_chroot, target_link)
                            
                        logger.info(f"  [Service] Symbolic link for service '{srv}' created successfully.")
                    except Exception as e:
                        logger.warning(f"  [Service] Could not symlink service {srv}: {e}")
                else:
                    logger.warning(f"  [Service] Service '{srv}' directory does not exist at {sv_dir}. Is it installed?")
            else:
                logger.info(f"    [Mock] ln -sf /etc/sv/{srv} /etc/runit/runsvdir/default/{srv}")


class CommandAction(SystemAction):
    """Execute generic system command."""

    def __init__(self, cmd: str):
        self.cmd = cmd

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info(f"  [Command] Run: {self.cmd}")
        if chroot.mode == "real":
            try:
                chroot.run_command(self.cmd)
            except Exception as e:
                logger.error(f"  [Command] Command failed: {e}")
                raise
        else:
            logger.info(f"    [Mock] Run command: {self.cmd}")


class DracutAction(SystemAction):
    """Configure initramfs generation through dracut."""

    def __init__(self, initramfs_config: Dict[str, Any]):
        self.compression = initramfs_config.get("compression", "xz")
        self.extra_modules = initramfs_config.get("dracut_modules", [])

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info("  [Dracut] Running dracut for initramfs...")
        if chroot.mode == "real":
            import shutil
            mklive_dir = project_root() / "configs" / "assets"
            dracut_modules_dir = chroot.chroot_path / "usr" / "lib" / "dracut" / "modules.d"
            dracut_modules_dir.mkdir(parents=True, exist_ok=True)

            for module_name, dest_name in [("vmklive", "01vmklive")]:
                src = mklive_dir / "dracut" / module_name
                dest = dracut_modules_dir / dest_name
                if src.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    import os
                    import subprocess
                    if os.geteuid() != 0:
                        subprocess.run(["sudo", "cp", "-a", str(src), str(dest)], check=True)
                    else:
                        shutil.copytree(src, dest)
                    logger.info(f"  [Dracut] Installed module: {module_name}")
                else:
                    logger.warning(f"  [Dracut] Module {module_name} not found at {src}")

            modules_dir = chroot.chroot_path / "usr" / "lib" / "modules"
            if not modules_dir.is_dir():
                logger.error("  [Dracut] No kernel modules directory found!")
                return
            versions_dirs = [d for d in modules_dir.iterdir() if d.is_dir()]
            if not versions_dirs:
                logger.error("  [Dracut] No kernel found in /usr/lib/modules!")
                return
            # Sort by modified time (newest first) to match mklive.sh's `ls -t` behavior
            versions_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            kernel_version = versions_dirs[0].name
            logger.info(f"  [Dracut] Detected kernel version: {kernel_version} (most recently modified)")

            comp_flags = {
                "xz": "--xz",
                "gzip": "--gzip",
                "lz4": "--lz4",
                "bzip2": "--bzip2",
                "zstd": "--zstd",
            }
            comp = comp_flags.get(self.compression, "--xz")

            force_add = ["vmklive", "dmsquash-live"] + self.extra_modules
            omit = ["systemd"]

            cmd = ["dracut", "-N", comp]
            cmd.extend(["--add-drivers", "overlay"])
            for mod in force_add:
                cmd.extend(["--force-add", mod])
            for mod in omit:
                cmd.extend(["--omit", mod])
            cmd.extend(["--force", "/boot/initrd", kernel_version])

            cmd_str = " ".join(cmd)
            logger.info(f"  [Dracut] Command: {cmd_str}")
            
            chroot.run_command(cmd_str)
            logger.info("  [Dracut] Initramfs generated successfully")
        else:
            logger.info("    [Mock] dracut -N --xz --force-add vmklive --omit systemd ... /boot/initrd")


class LocaleAction(SystemAction):
    """Configure locales, timezone, hostname, and keymap on Void Linux."""

    def __init__(self, config: Dict[str, Any]):
        self.hostname = config.get("hostname", "void-live")
        self.timezone = config.get("timezone", "UTC")
        self.locale = config.get("locale", "en_US.UTF-8")
        self.keymap = config.get("keymap", "us")

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info(
            f"  [Locale] Hostname: {self.hostname}, Timezone: {self.timezone}, Locale: {self.locale}"
        )
        if chroot.mode == "real":
            chroot.run_command(f"echo {self.hostname} > /etc/hostname")
            chroot.run_command(
                f"ln -sf /usr/share/zoneinfo/{self.timezone} /etc/localtime"
            )

            lf_path = chroot.chroot_path / "etc" / "default" / "libc-locales"
            if lf_path.exists():
                try:
                    content = lf_path.read_text(encoding="utf-8")
                    import re
                    content = re.sub(rf"#({re.escape(self.locale)}.*)", r"\1", content)
                    lf_path.write_text(content, encoding="utf-8")
                    logger.info(f"  [Locale] Enabled {self.locale} in /etc/default/libc-locales")
                except Exception as e:
                    logger.warning(f"  [Locale] Failed to patch libc-locales: {e}")
            
            try:
                chroot.run_command("xbps-reconfigure -f glibc-locales", check=False)
            except Exception as e:
                logger.warning(f"  [Locale] glibc-locales reconfiguration failed: {e}")

            rc_conf = chroot.chroot_path / "etc" / "rc.conf"
            rc_conf.parent.mkdir(parents=True, exist_ok=True)
            try:
                content = ""
                if rc_conf.exists():
                    content = rc_conf.read_text(encoding="utf-8")
                
                import re
                if re.search(r"(?m)^\s*KEYMAP\s*=", content):
                    content = re.sub(r"(?m)^\s*KEYMAP\s*=.*$", f'KEYMAP="{self.keymap}"', content)
                else:
                    content += f'\nKEYMAP="{self.keymap}"\n'
                
                rc_conf.write_text(content, encoding="utf-8")
                logger.info(f"  [Locale] Set KEYMAP={self.keymap} in /etc/rc.conf")
            except Exception as e:
                logger.warning(f"  [Locale] Failed to write rc.conf: {e}")
        else:
            logger.info("    [Mock] Apply locale/timezone/hostname/keymap")




class PipewireAction(SystemAction):
    """Configures pipewire links and system autostarts."""

    def __init__(self, architecture: str):
        self.architecture = architecture

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info("  [Pipewire] Setting up pipewire configuration and autostarts...")
        
        is_asahi = self.architecture.startswith("asahi")
        
        if chroot.mode == "real":
            chroot.run_command("mkdir -p /etc/xdg/autostart")
            chroot.run_command("ln -sf /usr/share/applications/pipewire.desktop /etc/xdg/autostart/")
            
            chroot.run_command("mkdir -p /etc/pipewire/pipewire.conf.d")
            chroot.run_command("ln -sf /usr/share/examples/wireplumber/10-wireplumber.conf /etc/pipewire/pipewire.conf.d/")
            chroot.run_command("ln -sf /usr/share/examples/pipewire/20-pipewire-pulse.conf /etc/pipewire/pipewire.conf.d/")
            
            chroot.run_command("mkdir -p /etc/alsa/conf.d")
            chroot.run_command("ln -sf /usr/share/alsa/alsa.conf.d/50-pipewire.conf /etc/alsa/conf.d/")
            chroot.run_command("ln -sf /usr/share/alsa/alsa.conf.d/99-pipewire-default.conf /etc/alsa/conf.d/")
            
            if is_asahi:
                logger.info("  [Pipewire] Enabling speakersafetyd service for Asahi platform")
                chroot.run_command("mkdir -p /etc/runit/runsvdir/default")
                chroot.run_command("ln -sf /etc/sv/speakersafetyd /etc/runit/runsvdir/default/")
        else:
            logger.info("    [Mock] Configure pipewire autostart and configuration symlinks")
            if is_asahi:
                logger.info("    [Mock] Enable speakersafetyd service for Asahi platform")


class LoginManagerAction(SystemAction):
    """Configures dynamic login session and autologin for various display managers (LightDM, SDDM, GDM, LXDM)."""

    def __init__(self, display_manager: str, session_name: str, username: str = "void"):
        self.display_manager = display_manager
        self.session_name = session_name
        self.username = username

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info(f"  [LoginManager] Configuring {self.display_manager} session to '{self.session_name}' for user '{self.username}'")
        
        if chroot.mode == "real":
            import os
            import subprocess
            import tempfile
            
            def write_chroot_file(path_str: str, content: str, mode: int = 0o644):
                dest_file = chroot.chroot_path / path_str.lstrip("/")
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as temp_f:
                    temp_f.write(content)
                    temp_path = temp_f.name
                
                try:
                    cmd_copy = ["cp", temp_path, str(dest_file)]
                    cmd_chmod = ["chmod", oct(mode)[2:], str(dest_file)]
                    cmd_chown = ["chown", "0:0", str(dest_file)]
                    if os.geteuid() != 0:
                        subprocess.run(["sudo"] + cmd_copy, check=True)
                        subprocess.run(["sudo"] + cmd_chmod, check=True)
                        subprocess.run(["sudo"] + cmd_chown, check=True)
                    else:
                        shutil.copy2(temp_path, dest_file)
                        dest_file.chmod(mode)
                        os.chown(str(dest_file), 0, 0)
                finally:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

            # 1. LIGHTDM Configuration
            if self.display_manager == "lightdm":
                write_chroot_file("etc/lightdm/.session", self.session_name + "\n")
                
                greeter_content = (
                    "[greeter]\n"
                    "indicators = ~host;~spacer;~clock;~spacer;~layout;~session;~a11y;~power\n"
                )
                write_chroot_file("etc/lightdm/lightdm-gtk-greeter.conf", greeter_content)
                
            # 2. SDDM Configuration
            elif self.display_manager == "sddm":
                sddm_session = self.session_name
                if sddm_session == "kde" or sddm_session == "plasma":
                    sddm_session = "plasma.desktop"
                elif sddm_session == "lxqt":
                    sddm_session = "lxqt.desktop"
                elif not sddm_session.endswith(".desktop"):
                    sddm_session = f"{sddm_session}.desktop"
                    
                sddm_content = (
                    "[Autologin]\n"
                    f"User={self.username}\n"
                    f"Session={sddm_session}\n"
                )
                write_chroot_file("etc/sddm.conf", sddm_content)
                write_chroot_file("etc/sddm.conf.d/autologin.conf", sddm_content)
                
            # 3. GDM Configuration
            elif self.display_manager in ("gdm", "gdm3"):
                gdm_content = (
                    "[daemon]\n"
                    "AutomaticLoginEnable=true\n"
                    f"AutomaticLogin={self.username}\n"
                )
                write_chroot_file("etc/gdm/custom.conf", gdm_content)
                
                account_content = (
                    "[User]\n"
                    f"Session={self.session_name}\n"
                    "SystemAccount=false\n"
                )
                write_chroot_file(f"var/lib/AccountsService/users/{self.username}", account_content)
                
            # 4. LXDM Configuration
            elif self.display_manager == "lxdm":
                session_bin = f"/usr/bin/{self.session_name}"
                if self.session_name == "xfce":
                    session_bin = "/usr/bin/startxfce4"
                elif self.session_name == "lxde":
                    session_bin = "/usr/bin/startlxde"
                elif self.session_name == "lxqt":
                    session_bin = "/usr/bin/startlxqt"
                elif self.session_name == "enlightenment":
                    session_bin = "/usr/bin/enlightenment_start"
                    
                lxdm_content = (
                    "[base]\n"
                    f"autologin={self.username}\n"
                    f"session={session_bin}\n"
                )
                write_chroot_file("etc/lxdm/lxdm.conf", lxdm_content)

        else:
            logger.info(f"    [Mock] {self.display_manager} autologin configured: user={self.username}, session={self.session_name}")


class FlatpakAction(SystemAction):
    """Configures the official Flathub repository if flatpak is installed."""

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info("  [Flatpak] Checking flatpak configuration...")
        if chroot.mode == "real":
            # Check if flatpak binary exists in chroot
            flatpak_bin = chroot.chroot_path / "usr" / "bin" / "flatpak"
            if flatpak_bin.exists():
                logger.info("  [Flatpak] Flatpak detected. Adding Flathub remote...")
                try:
                    chroot.run_command("flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo", check=False)
                except Exception as e:
                    logger.warning(f"  [Flatpak] Failed to configure Flathub: {e}")
            else:
                logger.debug("  [Flatpak] Flatpak not installed, skipping configuration.")
        else:
            logger.info("    [Mock] flatpak remote-add --if-not-exists flathub ...")


class PlymouthAction(SystemAction):
    """Configures the default Plymouth theme."""

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info("  [Plymouth] Configuring default boot theme...")
        if chroot.mode == "real":
            import shutil
            from void_builder.core.path_utils import resolve_from_project
            
            # Check for our custom theme
            custom_theme_src = resolve_from_project("custom_files/usr/share/plymouth/themes/void-modern")
            theme_name = "bgrt"
            if custom_theme_src.exists():
                dest = chroot.chroot_path / "usr/share/plymouth/themes/void-modern"
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copytree(custom_theme_src, dest, dirs_exist_ok=True)
                theme_name = "void-modern"
                logger.info("  [Plymouth] Custom 'void-modern' theme deployed!")
            
            plymouth_dir = chroot.chroot_path / "etc" / "plymouth"
            
            if plymouth_dir.exists():
                logger.info(f"  [Plymouth] Setting theme to '{theme_name}'.")
                try:
                    chroot.run_command(f"sh -c 'echo \"[Daemon]\nTheme={theme_name}\nShowDelay=0\n\" > /etc/plymouth/plymouthd.conf'", check=False)
                except Exception as e:
                    logger.warning(f"  [Plymouth] Failed to set default theme: {e}")
            else:
                logger.debug("  [Plymouth] Plymouth is not installed. Skipping.")
        else:
            logger.info("    [Mock] Set Plymouth theme")


class StructuredCopyAction(SystemAction):
    """Configures structured copy of files from custom_files to rootfs."""

    def __init__(self, customizations_path: str, copy_files_list: List[Dict[str, str]], architecture: str):
        self.customizations_path = Path(customizations_path)
        self.copy_files_list = copy_files_list
        self.architecture = architecture

    def execute(self, chroot: ChrootManager, source_base: Path):
        logger.info(f"  [StructuredCopy] Copying {len(self.copy_files_list)} structured files to rootfs...")
        
        is_arm = self.architecture.startswith(("aarch64", "arm"))
        
        # Resolve python version in chroot if {python_version} is present in destinations
        py_ver = "3.12"
        if chroot.mode == "real":
            python_dirs = list(chroot.chroot_path.glob("usr/lib/python3.*"))
            if python_dirs:
                py_ver = python_dirs[0].name.replace("python", "")
        
        for entry in self.copy_files_list:
            src_rel = entry.get("source")
            dest_rel = entry.get("destination")
            if not src_rel or not dest_rel:
                continue

            # Apply conditional architecture filters as described in the comments
            # grub/themes, pep_installer, and pep_installer_integration are ignored on ARM
            if is_arm:
                if "grub/themes" in src_rel or "pep_installer" in src_rel or "pep_installer_integration" in src_rel:
                    logger.info(f"  [StructuredCopy] Skipping {src_rel} (not copied on ARM architecture)")
                    continue

            # Format destinations that contain python_version
            dest_rel = dest_rel.format(python_version=py_ver)
            
            src_path = source_base / self.customizations_path / src_rel
            dest_path = chroot.chroot_path / dest_rel.lstrip("/")
            
            logger.info(f"  [StructuredCopy] Copying: {src_rel} -> {dest_rel}")
            
            if chroot.mode == "real":
                if not src_path.exists():
                    logger.warning(f"  [StructuredCopy] Source path does not exist: {src_path}")
                    continue
                
                import os
                import subprocess
                
                # Ensure destination parent directory exists
                dest_dir = dest_path if src_path.is_dir() and not dest_rel.endswith(src_path.name) else dest_path.parent
                dest_dir_in_chroot = Path("/") / dest_dir.relative_to(chroot.chroot_path)
                
                chroot.run_command(f"mkdir -p {dest_dir_in_chroot}")
                
                # Copy file/directory preserving all attributes
                cmd_copy = ["cp", "-a", str(src_path), str(dest_path)]
                try:
                    if os.geteuid() != 0:
                        subprocess.run(["sudo"] + cmd_copy, check=True)
                    else:
                        subprocess.run(cmd_copy, check=True)
                except Exception as e:
                    logger.error(f"  [StructuredCopy] Failed to copy {src_path} to {dest_path}: {e}")
            else:
                logger.info(f"    [Mock] Copy {src_path} to {dest_path}")


class SystemConfigurator:
    def __init__(self, chroot: Optional[ChrootManager] = None):
        self.chroot = chroot
        self.actions: List[SystemAction] = []

    def load_from_config(self, config: Any):
        def _safe_get(cfg: Any, key: str, default: Any = None) -> Any:
            if not hasattr(cfg, "get"):
                return default
            try:
                value = cfg.get(key, default)
            except TypeError:
                value = cfg.get(key)
            return default if value is None else value

        if hasattr(config, "get"):
            cust_config = _safe_get(config, "customizations", {})
            sys_config = _safe_get(config, "system_config", {})
        else:
            return

        # 1. Overlay
        overlay_dir = cust_config.get("overlay_dir") or sys_config.get("overlay_dir")
        if overlay_dir:
            self.actions.append(OverlayAction(overlay_dir))

        include_dirs = cust_config.get("include_dirs", [])
        for inc_dir in include_dirs:
            if inc_dir:
                self.actions.append(OverlayAction(str(inc_dir)))

        # 2. Standalone files
        files = cust_config.get("files", []) or sys_config.get("files", [])
        for f in files:
            if hasattr(f, "get"):
                src = f.get("src")
                dest = f.get("dest")
                mode = f.get("mode")
                if src and dest:
                    self.actions.append(FileAction(src, dest, mode))

        # 3. Locale / hostname
        if cust_config:
            self.actions.append(LocaleAction(cust_config))

        # 4. Users
        users = cust_config.get("users", [])
        for u in users:
            if hasattr(u, "_data"):
                u = u._data
            self.actions.append(UserAction(u))

        # 5. Services
        services = cust_config.get("services", [])
        if not services:
            services = _safe_get(config, "platform_specific.services", [])
        if services:
            srv_list = [str(s) for s in services]
            self.actions.append(ServiceAction(srv_list))

        # 6. Commands
        commands = cust_config.get("commands", []) or sys_config.get("commands", [])
        for cmd in commands:
            self.actions.append(CommandAction(str(cmd)))

        # 7. Initramfs (dracut configuration)
        initramfs = (
            _safe_get(config, "initramfs_config")
            or _safe_get(config, "initramfs")
            or _safe_get(config, "platform_specific.initramfs_config")
        )
        if initramfs:
            if hasattr(initramfs, "_data"):
                initramfs = initramfs._data
            if isinstance(initramfs, dict):
                self.actions.append(DracutAction(initramfs))
        arch = _safe_get(config, "platform_specific.architecture", "x86_64")

        # 9. Pipewire configuration
        has_display_manager = False
        if services:
            for srv in services:
                if str(srv) in ("lightdm", "sddm", "gdm", "lxdm"):
                    has_display_manager = True
                    break
        
        has_desktop_pkg = False
        pkg_sources = _safe_get(config, "package_sources", {})
        if pkg_sources:
            off_pkgs = _safe_get(pkg_sources, "official", [])
            for p in off_pkgs:
                if any(desk in str(p) for desk in ("xfce4", "mate", "cinnamon", "gnome", "kde5", "kde", "lxde", "lxqt", "enlightenment")):
                    has_desktop_pkg = True
                    break

        if has_display_manager or has_desktop_pkg:
            self.actions.append(PipewireAction(arch))

            # 10. LoginManager session config
            display_manager = None
            if services:
                for srv in services:
                    if str(srv) in ("lightdm", "sddm", "gdm", "lxdm"):
                        display_manager = str(srv)
                        break

            if display_manager:
                username = "void"
                users = cust_config.get("users", [])
                if users:
                    first_user = users[0]
                    if hasattr(first_user, "_data"):
                        first_user = first_user._data
                    if isinstance(first_user, dict):
                        username = first_user.get("name", "void")

                session_name = None
                off_pkgs = _safe_get(pkg_sources, "official", [])
                for desk in ("xfce4", "xfce", "mate", "cinnamon", "enlightenment", "lxde", "lxqt", "kde5", "kde", "gnome"):
                    if any(desk in str(p) for p in off_pkgs):
                        session_name = desk
                        break
                if not session_name:
                    if display_manager == "sddm":
                        session_name = "plasma"
                    elif display_manager == "gdm":
                        session_name = "gnome"
                    else:
                        session_name = "xfce"
                
                # Normalize session names
                if session_name == "xfce4":
                    session_name = "xfce"
                elif session_name == "kde5":
                    session_name = "plasma"

                self.actions.append(LoginManagerAction(display_manager, session_name, username))

        # 11. Structured Copy (Desktop-environment file copying)
        desktop_env = _safe_get(config, "desktop_environment")
        if desktop_env:
            if hasattr(desktop_env, "_data"):
                desktop_env = desktop_env._data
            if isinstance(desktop_env, dict):
                custom_path = desktop_env.get("customizations_path", "custom_files/")
                use_common = desktop_env.get("use_common_config", False)
                copy_files = desktop_env.get("copy_files", []) or []

                final_copy_list = []
                if use_common:
                    base_custom_path = resolve_from_project("configs/base_customizations.json")
                    if base_custom_path.exists():
                        try:
                            import json
                            with open(base_custom_path, "r", encoding="utf-8") as f:
                                base_data = json.load(f)
                            base_list = base_data.get("base_copy_files", [])
                            final_copy_list.extend(base_list)
                            logger.info(f"Loaded {len(base_list)} common copy entries from base_customizations.json")
                        except Exception as e:
                            logger.error(f"Failed to load/parse configs/base_customizations.json: {e}")

                # Add desktop specific copy_files
                for item in copy_files:
                    if hasattr(item, "_data"):
                        item = item._data
                    if isinstance(item, dict):
                        final_copy_list.append(item)

                if final_copy_list:
                    arch = _safe_get(config, "platform_specific.architecture", "x86_64")
                    self.actions.append(StructuredCopyAction(custom_path, final_copy_list, arch))

        # 12. Flatpak Configuration (run unconditionally, checks inside if flatpak is installed)
        self.actions.append(FlatpakAction())
        
        # 13. Plymouth Configuration (sets bgrt theme)
        self.actions.append(PlymouthAction())

    def apply(self, source_base_dir: Optional[Path] = None):
        if not self.chroot:
            logger.warning(
                "Configurator called without a ChrootManager. No action was performed."
            )
            return

        source_base_dir = resolve_from_project(source_base_dir or project_root())

        if not self.actions:
            logger.info("No pending system configuration actions to apply.")
            return

        logger.info(
            f"Applying {len(self.actions)} system configuration actions..."
        )
        for action in self.actions:
            try:
                action.execute(self.chroot, source_base_dir)
            except Exception as e:
                logger.error(f"Failed to execute configuration action: {e}")
