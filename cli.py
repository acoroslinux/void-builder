import argparse
import re
import sys
from pathlib import Path
from typing import Any, Optional, Union, List, Dict

from void_builder.core.config_loader import ConfigLoader
from void_builder.core.iso_engine import Config
from void_builder.core.orchestrator import BuildOrchestrator, BuildOrchestratorError
from void_builder.core.path_utils import resolve_from_project


def _available_profiles(config_root: Path, category: str):
    category_dir = config_root / category
    if not category_dir.exists() or not category_dir.is_dir():
        return []
    return sorted([p.stem for p in category_dir.glob("*.json")])


def _slugify_name(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower())
    normalized = normalized.strip("-._")
    return normalized or fallback


def _resolve_output_name(architecture: str, desktop: str = None, output: str = None, platform: Any = None) -> str:
    if output:
        return output

    desktop_label = _slugify_name(desktop or "base", "base")
    arch_label = _slugify_name(architecture, "x86_64")

    plat_str = ""
    if isinstance(platform, list) and platform:
        plat_str = "-".join(str(p) for p in platform)
    elif isinstance(platform, str) and platform:
        plat_str = platform

    if plat_str and plat_str.lower() != architecture.lower():
        plat_label = _slugify_name(plat_str, "")
        return f"void-builder-{desktop_label}-{plat_label}-{arch_label}.iso"
    return f"void-builder-{desktop_label}-{arch_label}.iso"


def main():
    parser = argparse.ArgumentParser(
        description="Void-Builder: Modular and Dynamic Void Linux ISO Builder",
        epilog="Use --help to see a detailed list of available arguments.",
    )

    # Required/Primary Arguments
    parser.add_argument(
        "architecture",
        nargs="?",
        default="x86_64",
        help="Target architecture (e.g., x86_64). Default: x86_64",
    )

    # Configuration and Environment
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=str(resolve_from_project("configs/global_build.json")),
        help="Path to the global configuration JSON file. Default: configs/global_build.json",
    )

    parser.add_argument(
        "--mode",
        choices=["mock", "real"],
        default="mock",
        help="Execution mode: 'mock' (simulation, no root required) or 'real' (actual build, requires root/chroot). Default: mock",
    )

    clean_group = parser.add_mutually_exclusive_group()
    clean_group.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        help="Clean previous build artifacts before starting a new build (default).",
    )
    clean_group.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="Reuse previous build tree without pre-build cleanup.",
    )
    parser.set_defaults(clean=True)

    parser.add_argument(
        "--force-isolated-toolchain",
        action="store_true",
        help="Force isolated bootstrap toolchain in real mode, even if host tools are available.",
    )

    parser.add_argument(
        "--toolchain-debug",
        action="store_true",
        help="Enable detailed toolchain diagnostics and write them to a dedicated log file.",
    )

    parser.add_argument(
        "--toolchain-debug-log",
        type=str,
        help="Optional path for toolchain diagnostics log file.",
    )

    parser.add_argument(
        "--toolchain-pacman-retries",
        type=int,
        default=3,
        help="Number of retry attempts for package operations.",
    )

    parser.add_argument(
        "--update-toolchain",
        action="store_true",
        help="Force redownloading and updating the static xbps and proot toolchain binaries.",
    )

    # Presets & Flavours
    parser.add_argument(
        "-P",
        "--preset",
        type=str,
        help="Pre-defined unified profile preset from configs/presets (e.g. minimal, desktop-xfce, desktop-kde, desktop-gnome, rescue-sysadmin, developer, gaming).",
    )

    # Customization Overrides
    parser.add_argument(
        "-k",
        "--kernel",
        type=str,
        help="Kernel selection (profile in configs/kernels or direct package name, e.g. linux-lts).",
    )

    parser.add_argument(
        "-d",
        "--desktop",
        type=str,
        help="Override the default desktop environment defined in the configuration.",
    )

    parser.add_argument(
        "-b",
        "--bootloader",
        type=str,
        help="Bootloader profile name from configs/bootloaders.",
    )

    parser.add_argument(
        "-p",
        "--package-profile",
        action="append",
        default=[],
        help="Package profile from configs/packages. Can be provided multiple times.",
    )

    parser.add_argument(
        "-s",
        "--service-profile",
        action="append",
        default=[],
        help="Common services profile from configs/services. Can be provided multiple times.",
    )

    parser.add_argument(
        "--live-user",
        type=str,
        help="Override live ISO username (default from architecture config).",
    )

    parser.add_argument(
        "--live-password",
        type=str,
        help="Set custom password for the live user (default: live).",
    )

    parser.add_argument(
        "--live-profile",
        type=str,
        help="Live user profile name from configs/live-users.",
    )

    parser.add_argument(
        "--live-groups",
        type=str,
        help="Comma-separated group list for live user (e.g. wheel,audio,video).",
    )

    # Security & User Management
    parser.add_argument(
        "--root-password",
        type=str,
        help="Set password for root user account.",
    )

    parser.add_argument(
        "--lock-root",
        action="store_true",
        help="Lock root user account password for security.",
    )

    parser.add_argument(
        "--ssh-key",
        action="append",
        default=[],
        help="Path to an SSH public key file to inject into authorized_keys. Can be specified multiple times.",
    )

    parser.add_argument(
        "--ssh-pubkey",
        type=str,
        help="Direct SSH public key string to inject into authorized_keys.",
    )

    # System & Locale Overrides
    parser.add_argument(
        "--hostname",
        type=str,
        help="Override system hostname (e.g. void-custom).",
    )

    parser.add_argument(
        "--locale",
        type=str,
        help="Override system locale (e.g. pt_PT.UTF-8, en_US.UTF-8).",
    )

    parser.add_argument(
        "--timezone",
        type=str,
        help="Override system timezone (e.g. Europe/Lisbon, UTC).",
    )

    parser.add_argument(
        "--keymap",
        type=str,
        help="Override console keymap (e.g. pt-latin1, br-abnt2, us).",
    )

    # Boot & Kernel Options
    parser.add_argument(
        "--boot-title",
        type=str,
        help="Custom bootloader menu title (e.g. 'Void Linux Custom').",
    )

    parser.add_argument(
        "--iso-label",
        type=str,
        help="Custom ISO volume label (default: VOID_MODERN).",
    )

    parser.add_argument(
        "--extra-kernel-args",
        type=str,
        help="Extra kernel parameters appended to bootloader command line (e.g. 'nomodeset quiet').",
    )

    # Lifecycle Hooks
    parser.add_argument(
        "--hook",
        action="append",
        default=[],
        help="Lifecycle hook in format phase:script_path (e.g. 'post-install:configs/hooks/custom.sh').",
    )

    parser.add_argument(
        "--save-config",
        type=str,
        help="Export assembled build configuration JSON to specified file path and continue.",
    )

    parser.add_argument(
        "--clean-cache",
        action="store_true",
        help="Clean downloaded XBPS packages and stage seed tarball caches, then exit.",
    )

    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Launch interactive terminal wizard for step-by-step ISO/image configuration.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the build without root privileges (alias for --mode mock).",
    )

    parser.add_argument(
        "--platform",
        action="append",
        default=[],
        help="Platforms to enable for aarch64 EFI ISO images (available: pinebookpro, x13s). Can be specified multiple times.",
    )

    parser.add_argument(
        "-R",
        "--repository",
        action="append",
        default=[],
        help="Add a custom XBPS repository. Can be specified multiple times.",
    )

    parser.add_argument(
        "-I",
        "--include",
        action="append",
        default=[],
        help="Include directory structure under given path in the rootfs. Can be specified multiple times.",
    )

    parser.add_argument(
        "--list-options",
        action="store_true",
        help="List available presets, desktops, kernels, bootloaders, and package profiles.",
    )

    # Output
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output ISO file name. Default: void-builder-<desktop>-<architecture>.iso",
    )

    # Verbosity
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    # Validation & Verification
    parser.add_argument(
        "--check",
        "--validate",
        dest="validate_only",
        action="store_true",
        help="Validate configuration files, profile references, and package dependencies without building.",
    )

    parser.add_argument(
        "--verify",
        type=str,
        default=None,
        metavar="IMAGE_PATH",
        help="Deeply verify an existing ISO, disk image (.img), or rootfs tarball (.tar.xz), then exit.",
    )

    parser.add_argument(
        "--verify-platform",
        type=str,
        default=None,
        metavar="PLATFORM_NAME",
        help="Verify platform-specific image, DTB, and bootloader integration for a given platform (e.g. pinebookpro, x13s, rpi-aarch64).",
    )

    # Output Format & Compression
    parser.add_argument(
        "--format",
        choices=["iso", "img", "tarball"],
        default="iso",
        help="Target build artifact format: 'iso' (bootable ISO), 'img' (disk image), or 'tarball' (rootfs tar.xz). Default: iso",
    )

    parser.add_argument(
        "--compression",
        choices=["xz", "zstd", "gzip"],
        default="xz",
        help="SquashFS and Initramfs compression algorithm. Default: xz",
    )

    # Performance & Speed Optimization
    parser.add_argument(
        "--fast",
        "--quick",
        dest="fast_mode",
        action="store_true",
        help="Enable ultra-fast build mode (multi-threaded zstd level 3, fast block sizes, and optimized staging).",
    )

    parser.add_argument(
        "--tmpfs",
        action="store_true",
        help="Build entirely inside RAM (tmpfs) to maximize I/O throughput and avoid SSD wear.",
    )

    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Record and display a detailed execution timing benchmark report for each build stage.",
    )

    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of CPU cores/threads for compression and packaging (default: all available cores).",
    )

    parser.add_argument(
        "--generate-manifest",
        dest="generate_manifest",
        action="store_true",
        default=True,
        help="Generate SHA256/MD5 checksums and manifest.json alongside the build artifact (default: enabled).",
    )
    parser.add_argument(
        "--no-manifest",
        dest="generate_manifest",
        action="store_false",
        help="Disable automatic checksum and manifest generation.",
    )

    # Base System Tarball & Stage Seed Pipeline
    parser.add_argument(
        "--use-tarball",
        "--tarball",
        dest="use_tarball",
        type=str,
        nargs="?",
        const="y",
        default=None,
        help="Use a pre-built base system stage tarball (local path, URL, or 'y'/'auto') to skip downloading base packages.",
    )

    parser.add_argument(
        "--create-tarball",
        dest="create_tarball",
        action="store_true",
        help="Save the bootstrapped base rootfs as a stage tarball (.tar.xz) for rapid future builds.",
    )

    # Calamares Pipeline
    parser.add_argument(
        "--build-calamares",
        action="store_true",
        help="Build the Calamares package from the local template and exit.",
    )

    parser.add_argument(
        "--with-calamares",
        action="store_true",
        help="Build the Calamares package first and inject it into the ISO build as a local repository.",
    )

    args = parser.parse_args()

    if args.dry_run:
        args.mode = "mock"

    if args.clean_cache:
        import shutil
        cache_dirs = [
            resolve_from_project("workdir/cache/xbps"),
            resolve_from_project("workdir/cache/tarballs"),
            resolve_from_project("workdir/cache"),
        ]
        print("🧹 Cleaning local package and stage seed caches...")
        for cd in cache_dirs:
            if cd.exists():
                shutil.rmtree(cd, ignore_errors=True)
                print(f"  - Cleaned: {cd}")
        print("✅ Cache cleaning complete.")
        sys.exit(0)

    if args.interactive:
        print("\n" + "=" * 60)
        print(" 🚀 Void-Builder Interactive Build Wizard")
        print("=" * 60)
        print("\nSelect target architecture:")
        print("  1) x86_64 (Default PC 64-bit)")
        print("  2) x86_64-musl (Musl libc)")
        print("  3) aarch64 (ARM 64-bit)")
        print("  4) rpi-aarch64 (Raspberry Pi 3/4/5 64-bit)")
        print("  5) pinebookpro (Pinebook Pro ARM)")
        print("  6) asahi (Apple Silicon)")
        arch_choice = input("Enter choice [1-6, default 1]: ").strip()
        arch_map = {
            "1": "x86_64", "2": "x86_64-musl", "3": "aarch64",
            "4": "rpi-aarch64", "5": "pinebookpro", "6": "asahi"
        }
        args.architecture = arch_map.get(arch_choice, "x86_64")

        print("\nSelect build preset/edition:")
        print("  1) minimal (Minimal / Server / Headless)")
        print("  2) desktop-xfce (XFCE Lightweight Workstation)")
        print("  3) desktop-kde (KDE Plasma Workstation)")
        print("  4) desktop-gnome (GNOME Workstation)")
        print("  5) rescue-sysadmin (System Rescue & Disk Partitioning)")
        print("  6) developer (Developer & Engineering Tools)")
        print("  7) gaming (Steam & Vulkan Gaming Edition)")
        preset_choice = input("Enter choice [1-7, default 2]: ").strip()
        preset_map = {
            "1": "minimal", "2": "desktop-xfce", "3": "desktop-kde",
            "4": "desktop-gnome", "5": "rescue-sysadmin", "6": "developer", "7": "gaming"
        }
        args.preset = preset_map.get(preset_choice, "desktop-xfce")

        mode_choice = input("\nRun mode ('mock' simulation or 'real' root build) [mock/real, default mock]: ").strip()
        if mode_choice in ("real", "r"):
            args.mode = "real"
        else:
            args.mode = "mock"

    def build_calamares_package(target_arch):
        import os
        import subprocess
        import shutil
        import pwd
        from void_builder.utils.lib import ensure_static_xbps, get_tools_dir
        
        real_user = os.environ.get("SUDO_USER") or os.environ.get("USER")
        if not real_user or real_user == "root":
            print("Error: Could not determine a non-root user for compilation. Please run without sudo or with 'sudo -E'.")
            sys.exit(1)
            
        print(f"\n[Calamares] Starting Calamares compilation via void-packages for architecture: {target_arch}...")
        workdir = resolve_from_project("workdir/void-packages")
        template_src = resolve_from_project("custom_packages/calamares")
        
        if not template_src.exists():
            print(f"Error: Calamares template not found at {template_src}")
            sys.exit(1)
            
        print("[Calamares] Preparing static xbps tools...")
        tools_dir = get_tools_dir()
        ensure_static_xbps(tools_dir=tools_dir)
        
        # Symlink .static tools so void-packages can find them
        bin_dir = Path(tools_dir) / "usr" / "bin"
        for f in bin_dir.glob("*.static"):
            link_name = f.with_suffix("")
            if not link_name.exists():
                os.symlink(f.name, link_name)
                
        # Fix permissions so the non-root user can traverse and execute the static tools
        if os.geteuid() == 0:
            subprocess.run(["chown", "-R", f"{real_user}:{real_user}", str(tools_dir)], check=True)
            subprocess.run(["chmod", "-R", "a+rx", str(tools_dir)], check=True)
                
        # Inject our portable tools into PATH
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            
        if not workdir.exists() or not (workdir / "xbps-src").exists():
            print("[Calamares] Cloning void-packages repository (depth=1)...")
            if workdir.exists():
                shutil.rmtree(workdir)
            workdir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--depth", "1", "https://github.com/void-linux/void-packages.git", str(workdir)], check=True)
        else:
            print("[Calamares] void-packages repository detected.")
            
        # Ensure correct ownership before dropping privileges
        if os.geteuid() == 0:
            subprocess.run(["chown", "-R", f"{real_user}:{real_user}", str(workdir)], check=True)
            
        print("[Calamares] Preparing the template...")
        dest_pkg = workdir / "srcpkgs" / "calamares"
        if dest_pkg.exists():
            shutil.rmtree(dest_pkg)
        shutil.copytree(template_src, dest_pkg)
        
        if os.geteuid() == 0:
            subprocess.run(["chown", "-R", f"{real_user}:{real_user}", str(dest_pkg)], check=True)
            
        cmd_prefix = []
        if os.geteuid() == 0:
            cmd_prefix = ["sudo", "-u", real_user, "env", f"PATH={env['PATH']}"]
            
        masterdir = f"masterdir-{target_arch}"
        print(f"[Calamares] Configuring xbps-src native environment ({masterdir})...")
        subprocess.run(cmd_prefix + ["./xbps-src", "-m", masterdir, "-A", target_arch, "binary-bootstrap"], cwd=str(workdir), check=True)
        
        print(f"[Calamares] Compiling the package natively for {target_arch} (This may take some time and CPU)...")
        pkg_cmd = cmd_prefix + ["./xbps-src", "-m", masterdir, "-A", target_arch, "pkg", "calamares"]
            
        subprocess.run(pkg_cmd, cwd=str(workdir), check=True)
        
        binpkgs_dir = workdir / "hostdir" / "binpkgs"
        if target_arch != "x86_64":
             # xbps-src stores cross compiled packages in hostdir/binpkgs/<arch>
             binpkgs_dir = binpkgs_dir / target_arch
             if not binpkgs_dir.exists():
                 binpkgs_dir = workdir / "hostdir" / "binpkgs" # fallback
                 
        print(f"\n[Calamares] ✅ Compilation completed successfully!")
        print(f"[Calamares] Binary repository generated at: {binpkgs_dir}\n")
        return binpkgs_dir

    if args.verify or args.verify_platform:
        from void_builder.core.verifier import ImageVerifier
        target_path = Path(args.verify) if args.verify else Path(args.output or "output")
        if args.verify_platform:
            report = ImageVerifier.verify_platform(args.verify_platform, target_path)
        elif target_path.name.endswith(".iso"):
            report = ImageVerifier.verify_iso(target_path, args.architecture)
        elif target_path.name.endswith((".img", ".img.xz", ".img.gz", ".raw")):
            report = ImageVerifier.verify_disk_image(target_path, args.architecture)
        elif target_path.name.endswith((".tar.xz", ".tar.gz", ".tar")):
            report = ImageVerifier.verify_tarball(target_path, args.architecture)
        else:
            report = ImageVerifier.verify_iso(target_path, args.architecture)
        report.print_summary()
        sys.exit(0 if report.all_passed else 1)

    VALID_ARCHS = (
        "x86_64", "x86_64-musl",
        "i686",
        "aarch64", "aarch64-musl",
        "armv7l", "armv7l-musl",
        "armv6l", "armv6l-musl",
        "riscv64", "riscv64-musl",
        "rpi-aarch64", "rpi-armv7l", "rpi-armv6l",
        "pinebookpro", "asahi", "x13s", "rockpro64", "pine64", "odroid-c4", "odroid-n2", "visionfive2",
    )
    arch_lower = args.architecture.lower()
    if arch_lower not in VALID_ARCHS:
        print(f"Error: Architecture '{args.architecture}' is not supported.")
        print(f"Supported architectures: {', '.join(VALID_ARCHS)}")
        sys.exit(1)
    args.architecture = arch_lower
    output_name = _resolve_output_name(
        architecture=args.architecture,
        desktop=args.desktop or args.preset,
        output=args.output,
        platform=args.platform,
    )

    config_root = resolve_from_project("configs")
    if args.list_options:
        print("Available build selections:")
        print(f"- presets:       {', '.join(_available_profiles(config_root, 'presets')) or '(none)'}")
        print(f"- architectures: {', '.join(_available_profiles(config_root, 'architectures')) or '(none)'}")
        print(f"- desktops:      {', '.join(_available_profiles(config_root, 'desktops')) or '(none)'}")
        print(f"- kernels:       {', '.join(_available_profiles(config_root, 'kernels')) or '(none)'}")
        print(f"- bootloaders:   {', '.join(_available_profiles(config_root, 'bootloaders')) or '(none)'}")
        print(f"- packages:      {', '.join(_available_profiles(config_root, 'packages')) or '(none)'}")
        print(f"- services:      {', '.join(_available_profiles(config_root, 'services')) or '(none)'}")
        print(f"- live-users:    {', '.join(_available_profiles(config_root, 'live-users')) or '(none)'}")
        sys.exit(0)

    # Prepare paths
    config_path = resolve_from_project(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)

    # Parse SSH keys and Hooks
    ssh_keys_list = []
    if args.ssh_key:
        for kpath in args.ssh_key:
            kp = Path(kpath)
            if kp.exists():
                ssh_keys_list.append(kp.read_text(encoding="utf-8").strip())
            else:
                print(f"Warning: SSH key file not found: {kpath}")
    if args.ssh_pubkey:
        ssh_keys_list.append(args.ssh_pubkey.strip())

    hooks_dict = {}
    if args.hook:
        for h in args.hook:
            if ":" in h:
                phase, hpath = h.split(":", 1)
                phase = phase.strip()
                hpath = hpath.strip()
                hooks_dict.setdefault(phase, []).append(hpath)
            else:
                hooks_dict.setdefault("post-install", []).append(h.strip())

    # Initialize Orchestrator
    parsed_live_groups = None
    if args.live_groups:
        parsed_live_groups = [g.strip() for g in args.live_groups.split(",") if g.strip()]

    orchestrator = BuildOrchestrator(
        arch=args.architecture,
        config_path=str(config_path),
        mode=args.mode,
        clean=args.clean,
        force_isolated_toolchain=args.force_isolated_toolchain,
        toolchain_debug=args.toolchain_debug,
        toolchain_debug_log=args.toolchain_debug_log,
        toolchain_pacman_retries=args.toolchain_pacman_retries,
        desktop=args.desktop,
        kernel=args.kernel,
        bootloader=args.bootloader,
        package_profiles=args.package_profile,
        service_profiles=args.service_profile,
        live_profile=args.live_profile,
        live_user=args.live_user,
        live_groups=parsed_live_groups,
        platforms=args.platform,
        repositories=args.repository,
        include_dirs=args.include,
        update_toolchain=args.update_toolchain,
        compression=args.compression,
        generate_manifest=args.generate_manifest,
        use_tarball=args.use_tarball,
        create_tarball=args.create_tarball,
        preset=args.preset,
        hostname=args.hostname,
        timezone=args.timezone,
        locale=args.locale,
        keymap=args.keymap,
        root_password=args.root_password,
        lock_root=args.lock_root,
        live_password=args.live_password,
        boot_title=args.boot_title,
        iso_label=args.iso_label,
        extra_kernel_args=args.extra_kernel_args,
        ssh_keys=ssh_keys_list,
        hooks=hooks_dict,
        save_config_path=args.save_config,
        fast_mode=args.fast_mode,
        use_tmpfs=args.tmpfs,
        benchmark=args.benchmark,
        jobs=args.jobs,
    )

    # Handle Validation Mode (--check / --validate)
    if args.validate_only:
        print(f"\n🔍 Validating configuration for target architecture '{args.architecture}'...")
        report = orchestrator.validate()
        if report.get("valid"):
            print("✅ Configuration is VALID!")
            print("Summary:")
            summary = report.get("summary", {})
            print(f"  - Target Architecture: {summary.get('target_arch')}")
            print(f"  - Desktop Profile:     {summary.get('desktop')}")
            print(f"  - Total Packages:      {summary.get('total_packages')}")
            print(f"  - Enabled Services:    {', '.join(summary.get('services', []))}")
            sys.exit(0)
        else:
            print("❌ Configuration validation FAILED!")
            for err in report.get("errors", []):
                print(f"  - ERROR: {err}")
            sys.exit(1)

    print(f"--- Void-Builder Execution ---")
    print(f"Target Arch: {args.architecture}")
    print(f"Mode:        {args.mode}")
    print(f"Format:      {args.format}")
    print(f"Compression: {orchestrator.compression}")
    if args.fast_mode:
        print("Fast Mode:   enabled (zstd level 3, fast blocks, optimal staging)")
    if args.tmpfs:
        print("TmpFS (RAM): enabled (zero disk wear, max I/O throughput)")
    if args.benchmark:
        print("Benchmark:   enabled (stage timing metrics active)")
    if args.jobs:
        print(f"CPU Threads: {args.jobs}")
    print(f"Manifest:    {'enabled' if args.generate_manifest else 'disabled'}")
    print(f"Clean:       {'yes' if args.clean else 'no'}")
    if args.preset:
        print(f"Preset:      {args.preset}")
    if args.force_isolated_toolchain:
        print("Toolchain:   forced isolated bootstrap")
    print(f"Config:      {config_path}")
    print(f"Output:      {output_name}")
    if args.kernel:
        print(f"Kernel:     {args.kernel} (Override)")
    if args.desktop:
        print(f"Desktop:    {args.desktop} (Override)")
    if args.bootloader:
        print(f"Bootloader: {args.bootloader} (Override)")
    if args.hostname:
        print(f"Hostname:   {args.hostname} (Override)")
    if args.locale:
        print(f"Locale:     {args.locale} (Override)")
    if args.timezone:
        print(f"Timezone:   {args.timezone} (Override)")
    if args.keymap:
        print(f"Keymap:     {args.keymap} (Override)")
    if args.package_profile:
        print(f"Profiles:   {', '.join(args.package_profile)}")
    if args.service_profile:
        print(f"Services:   {', '.join(args.service_profile)}")
    if args.live_profile:
        print(f"Live Prof.: {args.live_profile}")
    if args.live_user:
        print(f"Live User:  {args.live_user} (Override)")
    if parsed_live_groups:
        print(f"Live Group: {', '.join(parsed_live_groups)}")
    if ssh_keys_list:
        print(f"SSH Keys:   {len(ssh_keys_list)} key(s) configured")
    if hooks_dict:
        print(f"Hooks:      {sum(len(v) for v in hooks_dict.values())} hook(s) configured")
    if args.platform:
        print(f"Platforms:  {', '.join(args.platform)}")
    if args.repository:
        print(f"Repos:      {', '.join(args.repository)} (Custom)")
    if args.use_tarball:
        print(f"Tarball Src: {args.use_tarball}")
    if args.create_tarball:
        print("Save Tarball: enabled")
    if args.include:
        print(f"Includes:   {', '.join(args.include)}")
    print(f"------------------------------\n")

    try:
        result_file = orchestrator.run_build(output_name, output_format=args.format)
        print(f"\n✅ Success! Build artifact created at: {result_file}")
    except BuildOrchestratorError as e:
        print(f"\n❌ Build Orchestration Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

