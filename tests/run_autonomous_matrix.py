#!/usr/bin/env python3
"""
Autonomous Batch Build Test Matrix for Void Builder.
Runs completely unattended and produces a consolidated test report.
"""
import os
import sys
import time
import tempfile
import traceback
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from void_builder.core.orchestrator import BuildOrchestrator
from void_builder.core.verifier import ImageVerifier

TEST_CASES = [
    # 1. Base Architectures & Formats
    {"name": "x86_64 Minimal ISO", "arch": "x86_64", "preset": "minimal", "format": "iso", "mode": "mock"},
    {"name": "x86_64-musl Minimal Tarball", "arch": "x86_64-musl", "preset": "minimal", "format": "tarball", "mode": "mock"},
    {"name": "i686 Syslinux/BIOS ISO", "arch": "i686", "preset": "minimal", "format": "iso", "mode": "mock"},
    {"name": "aarch64 Generic ISO", "arch": "aarch64", "preset": "minimal", "format": "iso", "mode": "mock"},
    
    # 2. SBC and ARM Platforms Disk Images
    {"name": "Raspberry Pi (rpi-aarch64) Disk Image", "arch": "rpi-aarch64", "preset": "minimal", "format": "img", "mode": "mock"},
    {"name": "Pinebook Pro (pinebookpro) Raw Image", "arch": "pinebookpro", "preset": "desktop-xfce", "format": "raw", "mode": "mock"},
    {"name": "Apple Silicon (asahi) Disk Image", "arch": "asahi", "preset": "desktop-kde", "format": "img", "mode": "mock"},
    {"name": "RISC-V 64 (riscv64) Tarball", "arch": "riscv64", "preset": "minimal", "format": "tarball", "mode": "mock"},
    
    # 3. Virtual Machine Formats
    {"name": "x86_64 QCOW2 Virtual Disk", "arch": "x86_64", "preset": "minimal", "format": "qcow2", "mode": "mock"},
    {"name": "x86_64 VirtualBox VDI Disk", "arch": "x86_64", "preset": "rescue-sysadmin", "format": "vdi", "mode": "mock"},
    {"name": "x86_64 VMware VMDK Disk", "arch": "x86_64", "preset": "minimal", "format": "vmdk", "mode": "mock"},
    
    # 4. Desktop Presets & Customizations
    {"name": "x86_64 Desktop XFCE ISO", "arch": "x86_64", "preset": "desktop-xfce", "format": "iso", "mode": "mock"},
    {"name": "x86_64 Desktop KDE ISO", "arch": "x86_64", "preset": "desktop-kde", "format": "iso", "mode": "mock"},
    {"name": "x86_64 Rescue Sysadmin ISO", "arch": "x86_64", "preset": "rescue-sysadmin", "format": "iso", "mode": "mock"},
    {"name": "x86_64 Fast Mode (Zstd) ISO", "arch": "x86_64", "preset": "minimal", "format": "iso", "mode": "mock", "fast_mode": True, "benchmark": True},
    {"name": "x86_64 Offline Repo Embedded ISO", "arch": "x86_64", "preset": "minimal", "format": "iso", "mode": "mock", "with_offline_repo": True, "offline_repo_packages": ["git", "vim"]},
    {"name": "rpi-aarch64 Compressed Image (.xz)", "arch": "rpi-aarch64", "preset": "minimal", "format": "img", "mode": "mock", "compress_image": True},
]

def run_tests():
    print("=" * 70)
    print("🚀 STARTING AUTONOMOUS VOID-BUILDER TEST MATRIX")
    print(f"Total test cases to execute: {len(TEST_CASES)}")
    print("=" * 70)

    results = []
    start_total = time.time()

    with tempfile.TemporaryDirectory() as tmp_root:
        tmp_base = Path(tmp_root)
        
        for idx, tc in enumerate(TEST_CASES, 1):
            name = tc["name"]
            arch = tc["arch"]
            preset = tc.get("preset", "minimal")
            fmt = tc["format"]
            mode = tc.get("mode", "mock")
            fast_mode = tc.get("fast_mode", False)
            benchmark = tc.get("benchmark", False)
            with_offline_repo = tc.get("with_offline_repo", False)
            offline_repo_pkgs = tc.get("offline_repo_packages", [])
            compress_image = tc.get("compress_image", False)

            print(f"\n[{idx:02d}/{len(TEST_CASES):02d}] Testing: {name} (Arch: {arch}, Preset: {preset}, Format: {fmt})...")
            out_ext = fmt
            if fmt == "tarball":
                out_ext = "tar.xz"
            elif fmt == "img" and compress_image:
                out_ext = "img.xz"
            
            output_file = tmp_base / f"test-{idx}-{arch}.{out_ext}"
            workdir = tmp_base / f"workdir-{idx}-{arch}"
            
            t0 = time.time()
            try:
                orch = BuildOrchestrator(
                    arch=arch,
                    config_path="configs/global_build.json",
                    preset=preset,
                    mode=mode,
                    clean=True,
                    fast_mode=fast_mode,
                    benchmark=benchmark,
                    with_offline_repo=with_offline_repo,
                    offline_repo_packages=offline_repo_pkgs,
                    compress_image=compress_image,
                )
                orch.workdir = workdir
                artifact = orch.run_build(str(output_file), output_format=fmt)
                elapsed = time.time() - t0
                
                artifact_path = Path(artifact)
                if not artifact_path.exists():
                    raise FileNotFoundError(f"Generated artifact not found: {artifact}")
                
                # Check manifest and sha256
                sha_file = Path(str(artifact) + ".sha256")
                manifest_file = Path(str(artifact) + ".manifest.json")
                if not sha_file.exists():
                    raise FileNotFoundError(f"Missing SHA256 checksum file: {sha_file}")
                if not manifest_file.exists():
                    raise FileNotFoundError(f"Missing manifest file: {manifest_file}")

                print(f"  ✅ PASS ({elapsed:.2f}s) - Generated: {artifact_path.name}")
                results.append((name, True, f"{elapsed:.2f}s", ""))
            except Exception as e:
                elapsed = time.time() - t0
                err_msg = str(e)
                print(f"  ❌ FAIL ({elapsed:.2f}s) - {err_msg}")
                traceback.print_exc()
                results.append((name, False, f"{elapsed:.2f}s", err_msg))

    total_time = time.time() - start_total
    passed_count = sum(1 for _, ok, _, _ in results)
    failed_count = len(results) - passed_count

    print("\n" + "=" * 70)
    print("📊 CONSOLIDATED AUTONOMOUS TEST MATRIX REPORT")
    print("=" * 70)
    for name, ok, dur, err in results:
        status_icon = "✅ PASS" if ok else "❌ FAIL"
        err_str = f" - Error: {err}" if err else ""
        print(f"  {status_icon} [{dur:>6s}] {name}{err_str}")
    print("=" * 70)
    print(f"Total: {len(results)} | Passed: {passed_count} | Failed: {failed_count} | Total Time: {total_time:.2f}s")
    print("=" * 70)
    
    return 0 if failed_count == 0 else 1

if __name__ == "__main__":
    sys.exit(run_tests())
