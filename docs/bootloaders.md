# Bootloaders & Boot Process

This document details the bootloader generation, partitioning schemes, and boot process for all supported architectures and platform targets in **Void-Builder**.

---

## Boot Architecture Overview

Void-Builder supports three distinct boot strategies depending on the target architecture:

| Target Architecture | Primary Bootloader | Partitioning | Firmware Files / Binaries |
| :--- | :--- | :--- | :--- |
| `x86_64`, `i686` | Hybrid SYSLINUX (BIOS) + GRUB2 (UEFI) | ISO 9660 / El Torito | `isolinux.bin`, `isohdpfx.bin`, `efiboot.img` |
| `aarch64` | GRUB2 EFI | ISO 9660 / UEFI FAT | `bootaa64.efi`, `efiboot.img` |
| `rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l` | Native Raspberry Pi Firmware | MBR (FAT16 + EXT4) | `bootcode.bin`, `start.elf`, `cmdline.txt` |
| `pinebookpro` | Rockchip U-Boot | GPT (FAT16 + EXT4) | `idbloader.img`, `u-boot.itb` |
| `asahi` | GRUB ARM64 EFI | MBR / GPT (FAT16 + EXT4) | `bootx64.efi` / m1n1 chain |

---

## PC Hybrid Boot (x86_64 / i686)

### BIOS Boot (SYSLINUX)
- `VoidEngine` generates `boot/isolinux/isolinux.bin` and `boot/isolinux/isolinux.cfg`.
- MBR boot record is embedded using `isohdpfx.bin` via `xorriso -isohybrid-mbr`.
- Displays boot menu using SYSLINUX `vesamenu.c32` with custom splash PNG image (`configs/assets/data/splash.png`).

### UEFI Boot (GRUB2)
- Generates a FAT filesystem image at `boot/grub/efiboot.img`.
- Contains `boot/efi/boot/bootx64.efi` or `bootia32.efi`.
- `xorriso` links `efiboot.img` via `-eltorito-alt-boot -e boot/grub/efiboot.img -no-emul-boot -isohybrid-gpt-basdat`.

---

## Single-Board Computer Platform Images (`.img`)

### Raspberry Pi (`rpi-aarch64`, `rpi-armv7l`, `rpi-armv6l`)
- Platform images generate raw MBR disk images.
- **Partition 1** (FAT16, 256MiB): Contains Raspberry Pi GPU firmware (`bootcode.bin`, `start.elf`, `fixup.dat`), kernel image (`kernel8.img` / `kernel7.img`), and `cmdline.txt` pointing to `root=PARTUUID=<uuid>`.
- **Partition 2** (EXT4, remainder): Root filesystem containing `/etc/fstab` matched to partition UUIDs.

### Pinebook Pro (`pinebookpro`)
- Uses Rockchip RK3399 U-Boot loader.
- **GPT Partitioning**:
  - `idbloader.img` written to sector 64 via `dd conv=notrunc,fsync`.
  - `u-boot.itb` written to sector 16384 via `dd conv=notrunc,fsync`.
  - Partition 1 (FAT16, 512MiB): `/boot` partition.
  - Partition 2 (EXT4): Root filesystem.

### Apple Silicon (`asahi`)
- Installs GRUB EFI (`grub-install --target=arm64-efi --efi-directory=/boot --removable`).
- Configures `linux-asahi` kernel modules and Apple Silicon device trees.
