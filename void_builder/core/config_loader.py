import json
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
        """Recursively merge two dictionaries and combine lists without losing or duplicating data."""
        for key, value in update.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                base[key] = self._deep_merge(base[key], value)
            elif (
                isinstance(value, list) and key in base and isinstance(base[key], list)
            ):
                # Extend lists while handling dictionary items by unique 'name' identifier
                existing_dict_indices = {
                    item["name"]: idx
                    for idx, item in enumerate(base[key])
                    if isinstance(item, dict) and "name" in item
                }
                for item in value:
                    if isinstance(item, dict) and "name" in item and item["name"] in existing_dict_indices:
                        idx = existing_dict_indices[item["name"]]
                        if isinstance(base[key][idx], dict):
                            base[key][idx] = self._deep_merge(base[key][idx], item)
                    elif item not in base[key]:
                        base[key].append(item)
            else:
                base[key] = value
        return base

    def _load_json_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
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
        """Set selected kernel and align related fields across all package lists."""
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
            if not isinstance(pkg_list, list):
                return False
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
            return replaced

        replace_kernel_in_list(platform.get("software"))
        pkg_sources = self.master_config.get("package_sources", {})
        if isinstance(pkg_sources, dict):
            replace_kernel_in_list(pkg_sources.get("official"))
        replace_kernel_in_list(self.master_config.get("software"))

    def _apply_live_user_override(self, live_user: str, live_groups: Optional[List[str]]) -> None:
        """Apply live user overrides directly into system customizations and command targets."""
        customizations = self.master_config.setdefault("customizations", {})
        if not isinstance(customizations, dict):
            customizations = {}
            self.master_config["customizations"] = customizations

        users = customizations.get("users")
        if not isinstance(users, list):
            users = []
            customizations["users"] = users

        target_idx = None
        for idx, user in enumerate(users):
            if isinstance(user, dict) and user.get("name") in ("live", live_user):
                target_idx = idx
                break

        if target_idx is None:
            new_user = {"name": live_user, "password": "live", "groups": []}
            users.append(new_user)
            target_user = new_user
        else:
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
        preset: Optional[str] = None,
        hostname: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        keymap: Optional[str] = None,
        root_password: Optional[str] = None,
        lock_root: bool = False,
        live_password: Optional[str] = None,
        boot_title: Optional[str] = None,
        iso_label: Optional[str] = None,
        boot_cmdline: Optional[str] = None,
        extra_kernel_args: Optional[str] = None,
        ssh_keys: Optional[List[str]] = None,
        hooks: Optional[Dict[str, Any]] = None,
    ) -> Config:
        """
        Configuration assembly process:
        1. Load the global manifest (global_build.json).
        2. Load optional preset profile if specified.
        3. Load the architecture-specific configuration.
        4. Load the requested desktop profile.
        5. Merge everything together and apply dynamic overrides.
        """
        logger.info(f"Starting configuration assembly for {target_arch}...")

        # 1. Global manifest
        global_path = self.config_root / "global_build.json"
        if not global_path.exists():
            raise ConfigValidationError(
                f"Global manifest not found at {global_path}"
            )

        self.master_config = self._load_json_file(global_path)

        # 1b. Load Preset (if provided)
        if preset:
            preset_name = preset.replace(".json", "")
            self.master_config["preset_name"] = preset_name
            preset_data = self._load_optional_profile("presets", preset_name)
            if preset_data:
                logger.info(f"Applying preset profile '{preset_name}'...")
                if not target_desktop and preset_data.get("desktop"):
                    target_desktop = preset_data.get("desktop")
                if not target_kernel and preset_data.get("kernel"):
                    target_kernel = preset_data.get("kernel")
                if not target_bootloader and preset_data.get("bootloader"):
                    target_bootloader = preset_data.get("bootloader")
                if not boot_title and preset_data.get("boot_title"):
                    boot_title = preset_data.get("boot_title")
                
                preset_pkgs = preset_data.get("package_profiles", [])
                if preset_pkgs:
                    package_profiles = (package_profiles or []) + list(preset_pkgs)
                preset_srvs = preset_data.get("service_profiles", [])
                if preset_srvs:
                    service_profiles = (service_profiles or []) + list(preset_srvs)

                self._deep_merge(self.master_config, preset_data)

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
            self.master_config["desktop"] = target_desktop
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
            kernel_data = self._load_optional_profile("system", target_kernel)
            if kernel_data:
                self._deep_merge(self.master_config, kernel_data)
            self._apply_kernel_override(target_kernel)

        if target_bootloader:
            if isinstance(target_bootloader, dict):
                self._deep_merge(self.master_config, {"bootloader": target_bootloader})
            else:
                bootloader_data = self._load_optional_profile("boot", target_bootloader)
                if bootloader_data:
                    self._deep_merge(self.master_config, bootloader_data)

        # Always load base, filesystems, hardware, and networking package profiles as default foundations.
        default_profiles = ["base", "filesystems", "hardware", "networking"]
        if target_desktop and target_desktop != "base":
            default_profiles.extend(["printing", "desktop-essentials"])

        for default_profile in default_profiles:
            prof_data = self._load_optional_profile("software", default_profile)
            if prof_data:
                self._deep_merge(self.master_config, prof_data)
                profile_packages = prof_data.get("software", prof_data.get("packages", []))
                if isinstance(profile_packages, list):
                    package_sources = self.master_config.setdefault("package_sources", {})
                    official_pkgs = package_sources.setdefault("official", [])
                    for pkg in profile_packages:
                        pkg_name = pkg.get("name") if isinstance(pkg, dict) else pkg
                        if pkg_name and pkg_name not in official_pkgs:
                            official_pkgs.append(pkg_name)

        # Helper to flatten and split comma-separated profile strings (e.g. "profile1,profile2")
        def flatten_profiles(profiles_input: Optional[List[str]]) -> List[str]:
            if not profiles_input:
                return []
            flattened = []
            for item in profiles_input:
                if isinstance(item, str):
                    for sub in item.split(","):
                        cleaned = sub.strip()
                        if cleaned and cleaned not in flattened:
                            flattened.append(cleaned)
                elif isinstance(item, list):
                    for sub in flatten_profiles(item):
                        if sub not in flattened:
                            flattened.append(sub)
            return flattened

        for profile_name in flatten_profiles(package_profiles):
            if profile_name in default_profiles:
                continue
            package_data = self._load_optional_profile("software", profile_name)
            if package_data:
                self._deep_merge(self.master_config, package_data)
                profile_packages = package_data.get("software", package_data.get("packages", []))
                if isinstance(profile_packages, list):
                    package_sources = self.master_config.setdefault("package_sources", {})
                    official_pkgs = package_sources.setdefault("official", [])
                    for pkg in profile_packages:
                        pkg_name = pkg.get("name") if isinstance(pkg, dict) else pkg
                        if pkg_name and pkg_name not in official_pkgs:
                            official_pkgs.append(pkg_name)

        for profile_name in flatten_profiles(service_profiles):
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
            pkgs = platform_specific.setdefault("software", [])
            if "grub-arm64-efi" not in pkgs:
                pkgs.append("grub-arm64-efi")

            if platforms:
                self.master_config.setdefault("platforms_config", {})
                for platform in platforms:
                    json_path = self.config_root / "hardware" / f"{platform}.json"
                    p_name = platform
                    p_pkgs = []
                    p_cmdline = ""
                    p_dtb = ""

                    if json_path.exists():
                        try:
                            p_data = self._load_json_file(json_path)
                            p_name = p_data.get("name", platform)
                            p_pkgs = p_data.get("software", [])
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
                            pkgs_match = re.search(r'PLATFORM_PKGS=\((.*?)\)', content, re.DOTALL | re.M)
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

        # 4e. Architecture Compatibility Sanitizer: filter out foreign arch packages
        is_arm = target_arch.startswith(("aarch64", "arm", "rpi", "pinebook", "asahi"))
        is_x86 = target_arch.startswith(("x86_64", "i686"))
        is_musl = "musl" in target_arch
        is_32bit = target_arch.startswith(("i686", "armv7l", "armv6l", "rpi-armv7l", "rpi-armv6l"))

        ARCH_64BIT_EXCLUSIVE_PACKAGES = {
            "element-desktop", "intel-media-driver"
        }

        GLIBC_EXCLUSIVE_PACKAGES = {
            "nss-mdns", "glibc-locales", "xf86-video-vmware", "open-vm-tools", "spice-vdagent"
        }

        X86_EXCLUSIVE_PACKAGES = {
            "intel-ucode", "amd-ucode", "linux-firmware-amd", "sof-firmware", "alsa-firmware",
            "intel-media-driver", "libva-intel-driver", "mesa-vulkan-intel",
            "xf86-video-intel", "xf86-video-vmware", "xf86-video-vesa", "xf86-video-ati",
            "open-vm-tools", "thermald", "syslinux",
            "grub-i386-efi", "grub-x86_64-efi", "memtest86+", "virtualbox-ose-guest-dkms"
        }

        ARM_EXCLUSIVE_PACKAGES = {
            "rpi-base", "rpi-kernel", "rpi-firmware", "rpi-userland",
            "pinebookpro-base", "x13s-base", "asahi-base", "grub-arm64-efi"
        }

        def _filter_pkg_list(pkg_list: list) -> list:
            if not isinstance(pkg_list, list):
                return pkg_list
            res = []
            for p in pkg_list:
                p_str = p.get("name") if isinstance(p, dict) else str(p)
                if is_32bit and p_str in ARCH_64BIT_EXCLUSIVE_PACKAGES:
                    continue
                if is_musl and p_str in GLIBC_EXCLUSIVE_PACKAGES:
                    continue
                if is_arm and p_str in X86_EXCLUSIVE_PACKAGES:
                    continue
                if is_x86 and p_str in ARM_EXCLUSIVE_PACKAGES:
                    continue
                res.append(p)
            # Deduplicate kernel for RPi
            has_rpi_kernel = any((p.get("name") if isinstance(p, dict) else str(p)) == "rpi-kernel" for p in res)
            if has_rpi_kernel:
                res = [p for p in res if (p.get("name") if isinstance(p, dict) else str(p)) != "linux"]
            return res

        package_sources = self.master_config.get("package_sources", {})
        if "official" in package_sources and isinstance(package_sources["official"], list):
            package_sources["official"] = _filter_pkg_list(package_sources["official"])

        if "software" in self.master_config and isinstance(self.master_config["software"], list):
            self.master_config["software"] = _filter_pkg_list(self.master_config["software"])

        platform_pkgs = self.master_config.get("platform_specific", {}).get("software")
        if platform_pkgs and isinstance(platform_pkgs, list):
            self.master_config["platform_specific"]["software"] = _filter_pkg_list(platform_pkgs)

        # 4f. Apply direct customization overrides
        cust = self.master_config.setdefault("customizations", {})
        if hostname:
            cust["hostname"] = hostname
        if timezone:
            cust["timezone"] = timezone
        if locale:
            cust["locale"] = locale
        if keymap:
            cust["keymap"] = keymap
        if root_password or lock_root:
            cust["root_password"] = root_password
            cust["lock_root"] = bool(lock_root)
        if live_password:
            users = cust.setdefault("users", [])
            for u in users:
                if isinstance(u, dict) and u.get("name") in ("live", live_user or "live"):
                    u["password"] = live_password
        if boot_title:
            self.master_config["boot_title"] = boot_title
        if iso_label:
            self.master_config.setdefault("system", {})["iso_label"] = iso_label
        if boot_cmdline:
            self.master_config["boot_cmdline"] = boot_cmdline
        if extra_kernel_args:
            current_cmdline = self.master_config.get("boot_cmdline", "")
            self.master_config["boot_cmdline"] = f"{current_cmdline} {extra_kernel_args}".strip()
        if ssh_keys:
            cust["ssh_keys"] = ssh_keys
        if hooks:
            cust["hooks"] = hooks

        # 4f. Multilib & Nonfree repository auto-detection for x86_64
        official_pkgs = self.master_config.get("package_sources", {}).get("official", [])
        repos = self.master_config.setdefault("repositories", [])
        if target_arch == "x86_64":
            if any("multilib" in str(p) or p in ("steam", "wine") for p in official_pkgs):
                multilib_repo = "https://repo-default.voidlinux.org/current/multilib"
                if multilib_repo not in repos:
                    repos.append(multilib_repo)
                if any("multilib-nonfree" in str(p) or p == "steam" for p in official_pkgs):
                    ml_nonfree = "https://repo-default.voidlinux.org/current/multilib/nonfree"
                    if ml_nonfree not in repos:
                        repos.append(ml_nonfree)

        logger.info("Configuration assembly completed successfully.")
        return Config(self.master_config)

    def validate(
        self,
        target_arch: str,
        target_desktop: Optional[str] = None,
        target_kernel: Optional[str] = None,
        target_bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate configuration files and profile references before starting build."""
        report: Dict[str, Any] = {"valid": True, "errors": [], "warnings": [], "summary": {}}

        # Check preset profile if specified
        if preset:
            preset_name = preset.replace(".json", "")
            preset_path = self.config_root / "presets" / f"{preset_name}.json"
            if not preset_path.exists():
                report["valid"] = False
                report["errors"].append(f"Preset profile '{preset_name}' missing at {preset_path}")

        # Check global build file
        global_path = self.config_root / "global_build.json"
        if not global_path.exists():
            report["valid"] = False
            report["errors"].append(f"Global build config missing at {global_path}")

        # Check architecture profile
        arch_path = self.config_root / "architectures" / f"{target_arch}.json"
        if not arch_path.exists():
            report["valid"] = False
            report["errors"].append(f"Architecture profile '{target_arch}' missing at {arch_path}")

        # Check desktop profile
        if target_desktop:
            dt_path = self.config_root / "desktops" / f"{target_desktop}.json"
            if not dt_path.exists():
                report["valid"] = False
                report["errors"].append(f"Desktop profile '{target_desktop}' missing at {dt_path}")

        # Check bootloader profile
        if target_bootloader:
            bl_path = self.config_root / "boot" / f"{target_bootloader}.json"
            if not bl_path.exists():
                report["valid"] = False
                report["errors"].append(f"Bootloader profile '{target_bootloader}' missing at {bl_path}")

        # Helper to flatten and split comma-separated profile strings
        def flatten_names(names_input: Optional[List[str]]) -> List[str]:
            if not names_input:
                return []
            res = []
            for item in names_input:
                if isinstance(item, str):
                    for sub in item.split(","):
                        c = sub.strip()
                        if c and c not in res:
                            res.append(c)
                elif isinstance(item, list):
                    for sub in flatten_names(item):
                        if sub not in res:
                            res.append(sub)
            return res

        # Check package profiles
        if package_profiles:
            for pkg_prof in flatten_names(package_profiles):
                p_path = self.config_root / "software" / f"{pkg_prof}.json"
                if not p_path.exists():
                    report["valid"] = False
                    report["errors"].append(f"Package profile '{pkg_prof}' missing at {p_path}")

        # Check service profiles
        if service_profiles:
            for srv_prof in flatten_names(service_profiles):
                s_path = self.config_root / "services" / f"{srv_prof}.json"
                if not s_path.exists():
                    report["valid"] = False
                    report["errors"].append(f"Service profile '{srv_prof}' missing at {s_path}")

        try:
            config = self.assemble(
                target_arch=target_arch,
                target_desktop=target_desktop,
                target_kernel=target_kernel,
                target_bootloader=target_bootloader,
                package_profiles=package_profiles,
                service_profiles=service_profiles,
                preset=preset,
            )
            pkg_list = config.get("software", []) or []
            off_pkgs = config.get("package_sources.official", []) or []
            common_pkgs = config.get("common_desktop_packages", []) or []
            all_pkgs = []
            for item in (pkg_list + off_pkgs + common_pkgs):
                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        all_pkgs.append(name)
                elif isinstance(item, str):
                    all_pkgs.append(item)
            desktop_val = target_desktop
            if not desktop_val:
                raw_desk = config.get("desktop_environment")
                if isinstance(raw_desk, dict):
                    desktop_val = raw_desk.get("name", "custom")
                elif hasattr(raw_desk, "get"):
                    desktop_val = raw_desk.get("name", "custom")
                else:
                    desktop_val = raw_desk or "base"

            report["summary"] = {
                "target_arch": target_arch,
                "preset": preset or "(none)",
                "desktop": desktop_val,
                "kernel": target_kernel or config.get("kernel", "default"),
                "total_packages": len(set(all_pkgs)),
                "services": config.get("customizations.services", []),
                "repositories": config.get("repositories", []),
            }
        except Exception as e:
            report["valid"] = False
            report["errors"].append(f"Assembly failed: {e}")

        return report


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
