import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from void_builder.core.chroot_manager import ChrootError, ChrootManager
from void_builder.core.path_utils import project_root, resolve_from_base, resolve_from_project

logger = logging.getLogger("SystemConfigurator")


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
                        import subprocess
                        import os
                        cmd = ["mkdir", "-p", str(runsvdir_default)]
                        if os.geteuid() != 0:
                            cmd = ["sudo"] + cmd
                        subprocess.run(cmd, check=True)
                    except Exception as e:
                        logger.warning(f"  [Service] Could not create runsvdir directory: {e}")
                
                sv_dir = chroot.chroot_path / "etc" / "sv" / srv
                if sv_dir.exists():
                    try:
                        import subprocess
                        import os
                        cmd = ["ln", "-sf", f"/etc/sv/{srv}", f"/etc/runit/runsvdir/default/{srv}"]
                        if os.geteuid() != 0:
                            cmd = ["sudo"] + cmd
                        subprocess.run(cmd, check=True)
                    except Exception as e:
                        logger.warning(f"  [Service] Could not symlink service {srv}: {e}")
                else:
                    logger.warning(f"  [Service] Service '{srv}' directory does not exist at /etc/sv/{srv}. Is it installed?")
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
            mklive_dir = project_root() / "void-mklive"
            dracut_modules_dir = chroot.chroot_path / "usr" / "lib" / "dracut" / "modules.d"
            dracut_modules_dir.mkdir(parents=True, exist_ok=True)

            for module_name, dest_name in [("vmklive", "01vmklive"), ("autoinstaller", "01autoinstaller")]:
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
            versions = [d.name for d in modules_dir.iterdir() if d.is_dir()]
            if not versions:
                logger.error("  [Dracut] No kernel found in /usr/lib/modules!")
                return
            kernel_version = versions[0]
            logger.info(f"  [Dracut] Detected kernel version: {kernel_version}")

            comp_flags = {
                "xz": "--xz",
                "gzip": "--gzip",
                "lz4": "--lz4",
                "bzip2": "--bzip2",
                "zstd": "--zstd",
            }
            comp = comp_flags.get(self.compression, "--xz")

            force_add = ["vmklive", "autoinstaller"] + self.extra_modules
            omit = ["systemd", "iscsi", "lunmask", "lvm", "cifs", "hwdb"]

            cmd = ["dracut", "-N", comp]
            for mod in force_add:
                cmd.extend(["--force-add", mod])
            for mod in omit:
                cmd.extend(["--omit", mod])
            cmd.extend(["--force", "/boot/initrd", kernel_version])

            cmd_str = " ".join(cmd)
            logger.info(f"  [Dracut] Command: {cmd_str}")
            
            try:
                chroot.run_command(cmd_str)
                logger.info("  [Dracut] Initramfs generated successfully")
            except Exception as e:
                logger.warning(f"  [Dracut] Dracut failed: {e}. Retrying with extra omissions...")
                fallback_cmd = cmd_str.replace('--omit hwdb', '--omit "hwdb udev-rules dmsquash-live dm"')
                chroot.run_command(fallback_cmd)
                logger.info("  [Dracut] Initramfs generated (fallback mode)")
        else:
            logger.info("    [Mock] dracut -N --xz --force-add vmklive --force-add autoinstaller --omit systemd ... /boot/initrd")


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
