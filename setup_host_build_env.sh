#!/bin/bash

# ==============================================================================
# SCRIPT: setup_host_build_env.sh
# PURPOSE: Prepares a Void Linux host environment for cross-architecture ISO builds.
# NOTE: This script is ONLY required when building for a foreign
#       architecture (e.g., aarch64 on an x86_64 host). If you build
#       for the host's own architecture, you do NOT need to run it.
#
# This script automates several setup steps required on the host machine
# when building ISO images for architectures different from the host (e.g.,
# building aarch64 or i686 ISOs on an x86_64 host).
#
# What this script does:
# 1. Updates the host's package list.
# 2. Installs QEMU user mode emulators, including the one for aarch64, and the
#    binfmt-support package.
# 3. Ensures the 'binfmt_misc' kernel module is loaded and its filesystem is
#    mounted.
# 4. Registers the installed QEMU user emulators with the kernel's binfmt_misc
#    interface using the correct update-binfmts command and ensures the
#    binfmt-support service is enabled and running for persistence.
#
# PREREQUISITES:
# - A Void Linux host system.
# - An active internet connection to download packages.
# - sudo privileges to install packages and configure system settings.
#
# USAGE:
# 1. Save this code to a file (e.g., setup_host_build_env.sh).
# 2. Make the file executable: chmod +x setup_host_build_env.sh
# 3. Run the script with sudo: sudo ./setup_host_build_env.sh
#
# IMPORTANT NOTE:
# This script ONLY sets up the HOST environment for cross-building and is
# optional unless you need foreign-arch builds.
# It DOES NOT modify your iso_builder.py script logic.
# Your iso_builder.py script still needs to be correctly configured to:
# - Use the right package names for the target architecture in its YAML configs.
# - Execute package management and system configuration commands, directing them
#   to the target rootfs (e.g., using -r, XBPS_ARCH, or chroot helpers).
# ==============================================================================

# Exit immediately if a command exits with a non-zero status.
set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run this script with sudo."
    exit 1
fi

echo "=> Detecting package manager and installing QEMU emulators..."

if command -v apt-get &> /dev/null; then
    echo "=> Debian/Ubuntu (APT) detected."
    apt-get update
    apt-get install -y qemu-user-static binfmt-support
elif command -v pacman &> /dev/null; then
    echo "=> Arch Linux (Pacman) detected."
    pacman -Syu --noconfirm qemu-user-static binfmt-support
elif command -v dnf &> /dev/null; then
    echo "=> Fedora/RHEL (DNF) detected."
    dnf install -y qemu-user-static binfmt-support
elif command -v zypper &> /dev/null; then
    echo "=> openSUSE (Zypper) detected."
    zypper install -y qemu-linux-user binfmt-support
elif command -v xbps-install &> /dev/null; then
    echo "=> Void Linux (XBPS) detected."
    xbps-install -S -y
    xbps-install -y qemu-user qemu-user-aarch64 qemu-user-arm qemu-user-ppc64le qemu-user-riscv64 binfmt-support
else
    echo "Error: Supported package manager not found. Please install qemu-user-static and binfmt-support manually."
    exit 1
fi

echo "=> Ensuring binfmt_misc kernel module is loaded and filesystem is mounted..."
# Load module if not loaded
if ! lsmod | grep -q binfmt_misc; then
    echo "Loading binfmt_misc kernel module..."
    modprobe binfmt_misc
    sleep 1
fi

# Mount filesystem if not mounted
if ! mountpoint -q /proc/sys/fs/binfmt_misc; then
    echo "Mounting binfmt_misc filesystem..."
    mount -t binfmt_misc none /proc/sys/fs/binfmt_misc
    sleep 1
fi

# Verificar se o diretório está acessível após tentar carregar/montar
if [ ! -d "/proc/sys/fs/binfmt_misc" ]; then
    echo "ERRO FATAL: O diretório /proc/sys/fs/binfmt_misc não existe ou não está acessível."
    echo "A configuração do binfmt_misc falhou. Não é possível continuar com a emulação."
    exit 1
fi

# --- START CORRECTED BINFMT REGISTRATION ---
echo "=> Registering QEMU user binfmts from /usr/share/binfmts/ using update-binfmts --import..."

# Use the correct command to import and register all binfmt configurations from /usr/share/binfmts/
# This command reads the config files and writes to /proc/sys/fs/binfmt_misc/register correctly.
if /usr/bin/update-binfmts --import; then
    echo "All binfmt entries from /usr/share/binfmts/ registered successfully."
else
    echo "Warning: Failed to register one or more binfmt entries using update-binfmts --import."
    echo "Check /proc/sys/fs/binfmt_misc/ for registered entries (e.g., qemu-aarch64)."
    # The build might still work if the required ones are registered, but this indicates a potential issue.
    # Don't exit here to allow checking registered entries afterwards.
fi

# We also need to ensure the init service is enabled and running so registration
# happens automatically on boot.
echo "=> Ensuring binfmt-support service is enabled and running..."
if command -v systemctl &> /dev/null; then
    echo "=> Systemd detected. Enabling systemd-binfmt..."
    systemctl enable --now systemd-binfmt.service || echo "Warning: Failed to enable systemd-binfmt service."
elif command -v sv &> /dev/null && [ -d "/etc/sv/binfmt-support" ]; then
    echo "=> Runit detected. Enabling binfmt-support..."
    if [ ! -L "/var/service/binfmt-support" ] || [ "$(readlink /var/service/binfmt-support)" != "/etc/sv/binfmt-support" ]; then
        ln -sf /etc/sv/binfmt-support /var/service/ || echo "Warning: Failed to enable binfmt-support service."
    fi
    sv restart binfmt-support || echo "Warning: Failed to restart binfmt-support service."
else
    echo "Warning: Init system not recognized or binfmt-support service directory not found."
    echo "Automatic binfmt registration on boot may not be configured."
fi

echo "=> Verifying registration for qemu-aarch64 in /proc/sys/fs/binfmt_misc/..."
echo "=> Verifying binfmt registration for all cross-build targets..."
HAS_ERROR=0
for ENTRY in qemu-aarch64 qemu-arm qemu-ppc64le qemu-riscv64; do
    if [ -f "/proc/sys/fs/binfmt_misc/${ENTRY}" ]; then
        echo "  OK  : ${ENTRY}"
    else
        echo "  FAIL: ${ENTRY} — não registado!"
        HAS_ERROR=1
    fi
done

if [ "$HAS_ERROR" -eq 0 ]; then
    echo "SUCCESS: Todos os emuladores estão ativos e registados."
else
    echo "AVISO: Um ou mais emuladores não foram registados."
    echo "       Builds para essas arquitecturas podem falhar com 'Exec format error'."
fi

echo "=> Host environment setup complete."
echo "You can now try running your iso_builder.py script for any supported architecture."
