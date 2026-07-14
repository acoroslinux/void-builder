import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

# Setup Logger
logger = setup_logger("ConfigLoader")


class ConfigValidationError(Exception):
    """Exception raised for configuration validation errors."""

    pass


class Config:
    """
    Data wrapper for configuration objects with dot-notation access.
    """

    def __init__(self, data: Union[Dict[str, Any], "Config"]):
        if isinstance(data, Config):
            self._data = data._data
        else:
            self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        keys = path.split(".")
        current = self._data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, "_data"):
                current = (
                    current._data.get(key) if isinstance(current._data, dict) else None
                )
            else:
                return default

            if current is None:
                return default
        return current

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            val = self._data[name]
            return Config(val) if isinstance(val, dict) else val
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __getitem__(self, item):
        return self._data[item]

    def __repr__(self):
        return f"Config({self._data})"

    def to_dict(self) -> Dict[str, Any]:
        return self._data


class ConfigAssembler:
    """
    The assembler is the composition brain.
    It reads the global manifest and merges the configuration of all components
    (architectures, desktops, bootloaders, and so on) into a single
    configuration object.
    """

    def __init__(self, config_root: str):
        self.config_root = resolve_from_project(config_root)
        self.master_config: Dict[str, Any] = {}

    def _deep_merge(
        self, base: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge two dictionaries and combine lists without losing data."""
        for key, value in update.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                base[key] = self._deep_merge(base[key], value)
            elif (
                isinstance(value, list) and key in base and isinstance(base[key], list)
            ):
                # Extend lists while avoiding duplicates where simple checks work.
                for item in value:
                    if item not in base[key]:
                        base[key].append(item)
            else:
                base[key] = value
        return base

    def _load_json_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
            return {}

    def _load_optional_profile(self, category: str, profile_name: str, warn_if_missing: bool = True) -> Dict[str, Any]:
        """Load a profile JSON from configs/<category>/<profile_name>.json if it exists."""
        profile_path = self.config_root / category / f"{profile_name}.json"
        if not profile_path.exists():
            if warn_if_missing:
                logger.warning(
                    f"Profile '{profile_name}' not found in '{category}' at {profile_path}"
                )
            return {}
        return self._load_json_file(profile_path)

    def _apply_kernel_override(self, kernel_name: str) -> None:
        """Set selected kernel and align related fields in platform_specific."""
        platform = self.master_config.setdefault("platform_specific", {})
        platform["base_kernel"] = kernel_name
        platform["initramfs"] = "initrd"

        def is_kernel_package(name: str) -> bool:
            if not name:
                return False
            # Match "linux", "linux-lts", "linux-mainline", or versioned like "linux6.6"
            return name in {"linux", "linux-lts", "linux-mainline"} or (
                name.startswith("linux") and any(c.isdigit() for c in name)
            )

        def replace_kernel_in_list(pkg_list):
            replaced = False
            for idx, item in enumerate(pkg_list):
                if isinstance(item, dict):
                    name = item.get("name")
                    if name and is_kernel_package(name):
                        pkg_list[idx] = {"name": kernel_name}
                        replaced = True
                elif isinstance(item, str) and is_kernel_package(item):
                    pkg_list[idx] = kernel_name
                    replaced = True
            if not replaced:
                if pkg_list and isinstance(pkg_list[0], dict):
                    pkg_list.append({"name": kernel_name})
                else:
                    pkg_list.append(kernel_name)
            return replaced

        platform_pkgs = platform.get("packages")
        if isinstance(platform_pkgs, list):
            replace_kernel_in_list(platform_pkgs)

    def _apply_live_user_override(self, live_user: str, live_groups: Optional[List[str]]) -> None:
        """Apply live user overrides directly into system customizations and command targets."""
        customizations = self.master_config.setdefault("customizations", {})
        if not isinstance(customizations, dict):
            customizations = {}
            self.master_config["customizations"] = customizations

        users = customizations.get("users")
        if not isinstance(users, list) or not users:
            users = []
            customizations["users"] = users

        target_idx = None
        for idx, user in enumerate(users):
            if isinstance(user, dict) and user.get("name") == "live":
                target_idx = idx
                break

        if target_idx is None:
            if users:
                target_idx = 0
            else:
                users.append({"name": live_user, "password": "live", "groups": []})
                target_idx = 0

        target_user = users[target_idx]
        if not isinstance(target_user, dict):
            target_user = {}
            users[target_idx] = target_user

        target_user["name"] = live_user
        if live_groups is not None:
            target_user["groups"] = [g for g in live_groups if g]

    def _resolve_live_user_from_config(self) -> Optional[Dict[str, Any]]:
        """Return the primary live-user dict from current merged configuration."""
        customizations = self.master_config.get("customizations", {})
        if not isinstance(customizations, dict):
            return None

        users = customizations.get("users", [])
        if not isinstance(users, list) or not users:
            return None

        for user in users:
            if isinstance(user, dict) and user.get("name"):
                return user
        return None

    def assemble(
        self,
        target_arch: str,
        target_desktop: Optional[str] = None,
        target_kernel: Optional[str] = None,
        target_bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        target_live_profile: Optional[str] = None,
        live_user: Optional[str] = None,
        live_groups: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
    ) -> Config:
        """
        Configuration assembly process:
        1. Load the global manifest (global_build.json).
        2. Load the architecture-specific configuration.
        3. Load the requested desktop profile.
        4. Merge everything together.
        """
        logger.info(f"Starting configuration assembly for {target_arch}...")

        # 1. Global manifest
        global_path = self.config_root / "global_build.json"
        if not global_path.exists():
            raise ConfigValidationError(
                f"Global manifest not found at {global_path}"
            )

        self.master_config = self._load_json_file(global_path)

        # 2. Architecture (for example: configs/architectures/x86_64.json)
        arch_config_path = self.config_root / "architectures" / f"{target_arch}.json"
        if arch_config_path.exists():
            arch_data = self._load_json_file(arch_config_path)
            if "repositories" in arch_data:
                self.master_config["repositories"] = arch_data["repositories"]
                arch_data = arch_data.copy()
                del arch_data["repositories"]
            self._deep_merge(self.master_config, arch_data)
        else:
            logger.warning(
                f"No architecture-specific file found at {arch_config_path}"
            )

        # 3. Desktop profile (if requested)
        if target_desktop:
            desktop_path = self.config_root / "desktops" / f"{target_desktop}.json"
            if desktop_path.exists():
                desktop_data = self._load_json_file(desktop_path)
                self._deep_merge(self.master_config, desktop_data)
                
                # Automatically append pipewire packages if a desktop variant is loaded
                if target_desktop != "base":
                    if "package_sources" not in self.master_config:
                        self.master_config["package_sources"] = {}
                    if "official" not in self.master_config["package_sources"]:
                        self.master_config["package_sources"]["official"] = []
                    
                    pw_pkgs = ["pipewire", "alsa-pipewire"]
                    if target_arch.startswith("asahi"):
                        pw_pkgs.append("asahi-audio")
                        
                    for pkg in pw_pkgs:
                        if pkg not in self.master_config["package_sources"]["official"]:
                            self.master_config["package_sources"]["official"].append(pkg)
            else:
                logger.warning(
                    f"Desktop '{target_desktop}' not found at {desktop_path}"
                )

        # 4. Optional profile selections
        if target_kernel:
            kernel_data = self._load_optional_profile("kernels", target_kernel)
            if kernel_data:
                self._deep_merge(self.master_config, kernel_data)
            self._apply_kernel_override(target_kernel)

        if target_bootloader:
            bootloader_data = self._load_optional_profile("bootloaders", target_bootloader)
            if bootloader_data:
                self._deep_merge(self.master_config, bootloader_data)

        # Always load the base package profile as it is common to all builds.
        base_package_data = self._load_optional_profile("packages", "base")
        if base_package_data:
            self._deep_merge(self.master_config, base_package_data)

        for profile_name in package_profiles or []:
            if profile_name == "base":
                continue
            package_data = self._load_optional_profile("packages", profile_name)
            if package_data:
                self._deep_merge(self.master_config, package_data)

        for profile_name in service_profiles or []:
            services_data = self._load_optional_profile("services", profile_name)
            if services_data:
                self._deep_merge(self.master_config, services_data)

        if target_live_profile:
            live_profile_data = self._load_optional_profile("live-users", target_live_profile)
            if live_profile_data:
                self._deep_merge(self.master_config, live_profile_data)

        if live_user:
            self._apply_live_user_override(live_user, live_groups)
        elif target_live_profile:
            profile_user = self._resolve_live_user_from_config()
            if isinstance(profile_user, dict):
                resolved_name = profile_user.get("name")
                if resolved_name:
                    resolved_groups = profile_user.get("groups")
                    if not isinstance(resolved_groups, list):
                        resolved_groups = None
                    self._apply_live_user_override(str(resolved_name), resolved_groups)

        # 4b. Initramfs profile (for live ISO kernel hooks)
        initramfs_profile = self._load_optional_profile("initramfs", "live", warn_if_missing=False)
        if initramfs_profile:
            self._deep_merge(self.master_config, initramfs_profile)

        # 4c. Process platforms (ARM specific)
        if target_arch.startswith("aarch64"):
            platform_specific = self.master_config.setdefault("platform_specific", {})
            pkgs = platform_specific.setdefault("packages", [])
            if "grub-arm64-efi" not in pkgs:
                pkgs.append("grub-arm64-efi")

            if platforms:
                self.master_config.setdefault("platforms_config", {})
                for platform in platforms:
                    json_path = self.config_root / "platforms" / f"{platform}.json"
                    p_name = platform
                    p_pkgs = []
                    p_cmdline = ""
                    p_dtb = ""

                    if json_path.exists():
                        try:
                            p_data = self._load_json_file(json_path)
                            p_name = p_data.get("name", platform)
                            p_pkgs = p_data.get("packages", [])
                            p_cmdline = p_data.get("cmdline", "")
                            p_dtb = p_data.get("dtb", "")
                            logger.info(f"Loaded platform config from JSON: {json_path}")
                        except Exception as e:
                            logger.warning(f"Failed to parse platform JSON at {json_path}: {e}")
                    else:
                        sh_path = resolve_from_project(f"configs/assets/platforms/{platform}.sh")
                        if sh_path.exists():
                            content = sh_path.read_text(encoding="utf-8")
                            import re
                            name_match = re.search(r'PLATFORM_NAME=["\']?(.*?)["\']?$', content, re.M)
                            pkgs_match = re.search(r'PLATFORM_PKGS=\((.*?)\)', content, re.M)
                            cmdline_match = re.search(r'PLATFORM_CMDLINE=["\']?(.*?)["\']?$', content, re.M)
                            dtb_match = re.search(r'PLATFORM_DTB=["\']?(.*?)["\']?$', content, re.M)

                            p_name = name_match.group(1) if name_match else platform
                            p_pkgs = pkgs_match.group(1).split() if pkgs_match else []
                            p_cmdline = cmdline_match.group(1) if cmdline_match else ""
                            p_dtb = dtb_match.group(1) if dtb_match else ""
                            logger.info(f"Loaded platform config from shell script: {sh_path}")
                        else:
                            logger.warning(f"Platform config not found for: {platform}")
                            continue

                    # Merge package dependencies
                    for pkg in p_pkgs:
                        if pkg not in pkgs:
                            pkgs.append(pkg)

                    # Store settings
                    self.master_config["platforms_config"][platform] = {
                        "dtb": p_dtb,
                        "cmdline": p_cmdline,
                        "name": p_name,
                    }
                    logger.info(f"Loaded platform config for: {p_name}")

        # 4d. Apply dynamic package rules (architecture, platform, desktop)
        rules_path = self.config_root / "package_rules.json"
        if rules_path.exists():
            try:
                rules = self._load_json_file(rules_path)
                
                # Make sure master_config has the official package list initialized
                package_sources = self.master_config.setdefault("package_sources", {})
                official_pkgs = package_sources.setdefault("official", [])
                
                # 1. Match architecture packages
                arch_rules = rules.get("architecture_packages", {})
                for arch_key, pkgs_list in arch_rules.items():
                    if target_arch == arch_key or target_arch.startswith(arch_key):
                        for pkg in pkgs_list:
                            if pkg not in official_pkgs:
                                official_pkgs.append(pkg)
                
                # 2. Match platform packages
                platform_rules = rules.get("platform_packages", {})
                # Check for "asahi" platform specifically
                is_asahi = target_arch.startswith("asahi") or any("asahi" in p for p in (platforms or []))
                if is_asahi:
                    for pkg in platform_rules.get("asahi", []):
                        if pkg not in official_pkgs:
                            official_pkgs.append(pkg)
                
                for platform in (platforms or []):
                    for plat_key, pkgs_list in platform_rules.items():
                        if platform == plat_key or platform.startswith(plat_key):
                            for pkg in pkgs_list:
                                if pkg not in official_pkgs:
                                    official_pkgs.append(pkg)
                                    
                # 3. Match desktop packages
                if target_desktop:
                    desktop_rules = rules.get("desktop_packages", {})
                    # Load common desktop packages
                    for pkg in desktop_rules.get("common", []):
                        if pkg not in official_pkgs:
                            official_pkgs.append(pkg)
                    # Load specific desktop packages
                    for desk_key, pkgs_list in desktop_rules.items():
                        if desk_key == "common":
                            continue
                        if target_desktop == desk_key:
                            for pkg in pkgs_list:
                                if pkg not in official_pkgs:
                                    official_pkgs.append(pkg)
                                    
                logger.info("Applied dynamic package rules from package_rules.json successfully.")
            except Exception as e:
                logger.error(f"Failed to load or apply package rules: {e}")

        logger.info("Configuration assembly completed successfully.")
        return Config(self.master_config)


class ConfigLoader:
    def __init__(self, config_root: Optional[str] = None):
        self.config_root = str(resolve_from_project(config_root or "configs"))
        self.assembler = ConfigAssembler(self.config_root)

    def load_arch_config(self, global_path: str, arch: str) -> Optional[Dict[str, Any]]:
        try:
            assembler = ConfigAssembler(str(resolve_from_project(global_path).parent))
            config_obj = assembler.assemble(arch)
            return config_obj.to_dict()
        except Exception as e:
            logger.error(f"ConfigLoader error: {e}")
            return None
