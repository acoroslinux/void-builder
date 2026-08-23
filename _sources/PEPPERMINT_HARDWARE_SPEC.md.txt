# Void-Builder: Hardware, Architecture & Platform Compatibility Matrix

**Document Version:** 1.0.0  
**Project:** Void-Builder / PeppermintOS Next-Gen Build Infrastructure  
**Author:** AçorOS Linux / PeppermintOS Team  

---

## 1. Executive Summary

**`void-builder`** is a high-performance, modular, and dynamic operating system image builder. Engineered with clean separation of concerns, hermetic build-host isolation, and cross-architecture virtualization (QEMU User Static + binfmt_misc), it builds production-ready bootable images, flashable disk images, and rootfs stage seeds across a wide spectrum of computing architectures—ranging from high-end x86_64 servers to ARM64 single-board computers (SBCs), Snapdragon/Apple Silicon laptops, and open-source RISC-V 64-bit platforms.

---

## 2. Supported CPU Architectures

| Architecture | C Standard Library (`libc`) | Target Platform & Device Category | Primary Bootloader Stack |
| :--- | :--- | :--- | :--- |
| **`x86_64`** | `glibc` | Standard 64-bit Desktop PCs, Laptops & Servers | Dual-Mode: ISOLINUX (BIOS) + GRUB2 (UEFI x86_64) |
| **`x86_64-musl`** | `musl` | Ultra-lightweight, hardened & high-security x86_64 systems | Dual-Mode: ISOLINUX (BIOS) + GRUB2 (UEFI x86_64) |
| **`i686`** | `glibc` | Legacy 32-bit PCs and older netbooks/industrial systems | ISOLINUX (BIOS Legacy El-Torito) |
| **`aarch64`** | `glibc` | Standard 64-bit ARM Servers, Laptops and Generic UEFI boards | GRUB2 (UEFI `BOOTAA64.EFI` + `efiboot.img`) |
| **`aarch64-musl`** | `musl` | High-efficiency, low-memory ARM64 embedded & server systems | GRUB2 (UEFI `BOOTAA64.EFI` + `efiboot.img`) |
| **`armv7l`** | `glibc` | 32-bit ARMv7-A devices (Cortex-A7 / A8 / A9 / A15) | U-Boot / Broadcom VC4 Firmware |
| **`armv7l-musl`** | `musl` | Lightweight 32-bit ARMv7 embedded targets | U-Boot / Broadcom VC4 Firmware |
| **`armv6l`** | `glibc` | Legacy 32-bit ARMv6 devices (Raspberry Pi 1 / Pi Zero) | Broadcom VC4 Firmware Boot Tree |
| **`armv6l-musl`** | `musl` | Ultra-compact 32-bit ARMv6 appliances | Broadcom VC4 Firmware Boot Tree |
| **`riscv64`** | `glibc` | Standard 64-bit RISC-V Open Architecture targets | OpenSBI Firmware + GRUB2 RISC-V |
| **`riscv64-musl`** | `musl` | Minimalist, standalone RISC-V appliances | OpenSBI Firmware + GRUB2 RISC-V |

---

## 3. Dedicated Hardware Profiles & Single Board Computers (SBCs)

### 🍓 Raspberry Pi Family (Compressed `.img.xz` Flashable Disk Images)
Generates pre-partitioned dual-stage disk images (256MB FAT32 Boot with Broadcom VC4 firmware + Ext4 RootFS):
* **Raspberry Pi 5 / 500** (`rpi-aarch64`): Broadcom BCM2712 Quad-Core Cortex-A76 @ 2.4GHz.
* **Raspberry Pi 4 Model B / 400 / Compute Module 4** (`rpi-aarch64` / `rpi-armv7l`): Broadcom BCM2711 Quad-Core Cortex-A72.
* **Raspberry Pi 3 Model B/B+ / Compute Module 3 / Zero 2 W** (`rpi-aarch64` / `rpi-armv7l`): Broadcom BCM2837/BCM2710 Quad-Core Cortex-A53.
* **Raspberry Pi 2 Model B** (`rpi-armv7l`): Broadcom BCM2836/BCM2837 (ARMv7 32-bit).
* **Raspberry Pi 1 Model A/B / Zero / Zero W** (`rpi-armv6l`): Broadcom BCM2835 (ARMv6 32-bit).

---

### 🌲 Pine64 & Rockchip Family
* **Pinebook Pro** (`--platform pinebookpro`):
  * **SoC:** Rockchip RK3399 (Dual-core Cortex-A72 + Quad-core Cortex-A53).
  * **Hardware Features:** 1080p eDP IPS Display, Mali-T860 MP4 GPU, Realtek Audio, dedicated `rk3399-pinebook-pro.dtb`.
* **RockPro64** (`--platform rockpro64`):
  * **SoC:** Rockchip RK3399 High-Performance SBC with PCIe slot, USB-C DisplayPort, and Gigabit Ethernet.
  * **Hardware Features:** `rk3399-rockpro64.dtb` + Serial UART diagnostic console (`ttyS2,1500000n8`).
* **Pine A64 / Pinebook 11.6** (`--platform pine64`):
  * **SoC:** Allwinner A64 Quad-Core Cortex-A53.
  * **Hardware Features:** `sun50i-a64-pine64.dtb` + Serial UART console (`ttyS0,115200n8`).

---

### ⚡ Hardkernel ODROID Family (Amlogic Meson Architecture)
* **ODROID-N2 / ODROID-N2+** (`--platform odroid-n2`):
  * **SoC:** Amlogic S922X Hexa-Core (Quad Cortex-A73 @ 2.4GHz + Dual Cortex-A53 @ 2.0GHz).
  * **Hardware Features:** Mali-G52 GPU, `meson-g12b-odroid-n2-plus.dtb`, native Amlogic UART (`ttyAML0,115200n8`).
* **ODROID-C4** (`--platform odroid-c4`):
  * **SoC:** Amlogic S905X3 Quad-Core Cortex-A55.
  * **Hardware Features:** Low power consumption, `meson-sm1-odroid-c4.dtb`, native Amlogic UART (`ttyAML0,115200n8`).

---

### 💻 ARM64 Laptops & Apple Silicon
* **Lenovo ThinkPad X13s** (`--platform x13s`):
  * **SoC:** Qualcomm Snapdragon SC8280XP (8-Core Kryo CPU @ 3.0GHz).
  * **Hardware Features:** Qualcomm Adreno 690 GPU, Wi-Fi 6E, 5G Sub-6/mmWave, power-domain management flags, `sc8280xp-lenovo-thinkpad-x13s.dtb`.
* **Apple Silicon M1 / M2 Macs** (`--platform asahi`):
  * **SoC:** Apple M1 / M2 / Pro / Max / Ultra.
  * **Hardware Features:** Apple Silicon framebuffer drivers, `earlycon` diagnostic telemetry, `t8103-j274.dtb` Device Tree bindings.

---

### 🔮 RISC-V 64-bit Architecture
* **StarFive VisionFive 2** (`--platform visionfive2`):
  * **SoC:** StarFive JH7110 Quad-Core RISC-V 64-bit (SiFive U74 @ 1.5GHz).
  * **Hardware Features:** Imagination BXE-4-32 GPU, OpenSBI supervisor binary interface, `jh7110-starfive-visionfive-2-v1.3b.dtb`.

---

## 4. Pre-Packaged Unified Presets & Desktop Environments

| Preset Identifier | Description & Included Components | Target Use-Case |
| :--- | :--- | :--- |
| **`desktop-xfce`** | Lightweight, modular XFCE 4.18/4.20 Desktop, LightDM greeter, PipeWire/ALSA audio stack, NetworkManager, CUPS printing, and modern GTK theme suite. | **Default PeppermintOS Flagship Experience** |
| **`desktop-gnome`** | Complete GNOME Desktop with Wayland compositor, GDM, PipeWire, GNOME Shell extensions, and full desktop app ecosystem. | Modern workstation & tablet computing |
| **`desktop-kde`** | High-performance KDE Plasma 6 Desktop, SDDM, Wayland/X11, KWin compositor, and KDE Frameworks utilities. | Power users, multi-monitor setups |
| **`minimal`** | Pure headless/server base system with essential networking, SSH daemon, security hardening, and Void package management. | Headless servers, IoT, edge gateways |
| **`rescue-sysadmin`** | Comprehensive emergency toolkit with disk partition tools (GParted, TestDisk), network forensics (Wireshark, Nmap), filesystem repair, and hardware benchmarks. | IT forensics, disaster recovery, sysadmin |
| **`developer`** | Complete programming toolchain with GCC, Clang, Rust, Python 3, Git, CMake, Docker/Podman container runtime, and debugging suites. | Software engineers, DevOps, builders |
| **`gaming`** | Optimized low-latency gaming environment with 32-bit Multilib libraries, Mesa Vulkan drivers, MangoHud, Wine/Proton dependencies, and game controller support. | Enthusiast gaming, Steam, emulation |

---

## 5. Build Pipeline & Technical Highlights

1. **Hermetic Build-Host Isolation:**
   * Tools like `xorriso`, `mksquashfs`, `grub-mkstandalone`, `mtools`, and `dosfstools` run from a segregated toolchain environment (`build_host`), preventing any pollution or dependency on host packages.
2. **Multi-Threaded Parallel Compression:**
   * Utilizes multi-threaded Zstandard (`zstd` Level 3) across all available CPU cores (e.g., 20+ hardware threads), reducing 5.3 GB root filesystems down to 1.3 GB in under 3 seconds.
3. **Automated Static Verification Suite (`ImageVerifier`):**
   * Every built image automatically undergoes 9 programmatic integrity checks:
     1. Volume size and boundaries.
     2. Cryptographic hash calculation (SHA256, SHA512, MD5).
     3. JSON Manifest structural parsing.
     4. ISO9660 CD001 primary volume header validation.
     5. SquashFS internal compression integrity.
     6. GRUB2 UEFI configuration tree (`boot/grub/grub.cfg`).
     7. UEFI boot image inspection (`efiboot.img` / `BOOTAA64.EFI` / `BOOTX64.EFI`).
     8. Platform Device Tree Blob (DTB) verification.
     9. Hardware-specific serial/clocks/framebuffer runtime parameters.

---

## 6. Artifact Outputs & Standards

1. **Hybrid ISO9660 (`.iso`):** Universal bootable image supporting BIOS (El-Torito / ISOLINUX) and UEFI (GRUB2) across x86_64, i686, ARM64, and RISC-V.
2. **Flashable Disk Images (`.img.xz`):** Pre-partitioned raw images ready for flashing to MicroSD/eMMC using `dd` or BalenaEtcher.
3. **Stage Seeds (`.tar.xz`):** Clean root filesystem tarballs for container bootstrapping (Docker, LXC, systemd-nspawn) or custom chroot installs.
4. **Security Checksums:** Auto-generated `.sha256`, `.sha512`, `.md5`, and `.manifest.json` files accompanying each release artifact.

---

## 7. Quick CLI Usage Examples

```bash
# 1. Build PeppermintOS XFCE Flagship for PC (x86_64)
sudo python3 cli.py x86_64 --preset desktop-xfce --fast --mode real --clean

# 2. Build Raspberry Pi 64-bit Disk Image (Pi 4/5/Zero 2W)
sudo python3 cli.py rpi-aarch64 --preset minimal --fast --mode real --clean

# 3. Build Pinebook Pro ARM64 Laptop ISO
sudo python3 cli.py aarch64 --platform pinebookpro --preset desktop-xfce --fast --mode real --clean

# 4. Build Hardkernel ODROID-N2+ ARM64 ISO
sudo python3 cli.py aarch64 --platform odroid-n2 --preset minimal --fast --mode real --clean

# 5. Build Apple Silicon (M1/M2 Asahi) ARM64 ISO
sudo python3 cli.py aarch64 --platform asahi --preset minimal --fast --mode real --clean

# 6. Build StarFive VisionFive 2 RISC-V 64-bit ISO
sudo python3 cli.py riscv64 --platform visionfive2 --preset minimal --fast --mode real --clean

# 7. Build Ultra-Lightweight Musl libc Image
sudo python3 cli.py x86_64-musl --preset minimal --fast --mode real --clean

# 8. Verify Any Generated Image
python3 cli.py --verify output/void-builder-desktop-xfce-x86_64.iso
```
