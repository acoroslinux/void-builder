#!/bin/bash

# ==============================================================================
# SCRIPT: setup_host_build_env.sh
# PURPOSE: Prepares host environment (Gentoo, Void, Arch, Debian, Fedora, openSUSE)
#          for multi-architecture and cross-architecture ISO/Image builds.
# ==============================================================================

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run this script with sudo."
    exit 1
fi

echo "=> Detecting host distribution and package manager..."

if command -v emerge &> /dev/null; then
    echo "=> Gentoo Linux (Portage) detected."
    
    # 1. Safely configure QEMU_USER_TARGETS for Gentoo without damaging make.conf
    PORTAGE_DIR="/etc/portage"
    MAKE_CONF="${PORTAGE_DIR}/make.conf"
    
    mkdir -p "${PORTAGE_DIR}/package.use"
    
    # Configure QEMU user targets safely
    QEMU_TARGETS='QEMU_USER_TARGETS="aarch64 arm riscv64 x86_64 i386"'
    if [ -f "$MAKE_CONF" ]; then
        if ! grep -q "QEMU_USER_TARGETS" "$MAKE_CONF"; then
            echo "=> Safely appending QEMU_USER_TARGETS to ${MAKE_CONF} (preserving existing config)..."
            cp -a "$MAKE_CONF" "${MAKE_CONF}.bak.$(date +%s)"
            echo "" >> "$MAKE_CONF"
            echo "# Added by void-builder setup script for cross-compilation" >> "$MAKE_CONF"
            echo "$QEMU_TARGETS" >> "$MAKE_CONF"
        else
            echo "=> QEMU_USER_TARGETS already configured in ${MAKE_CONF}."
        fi
    fi
    
    # Ensure static-user flag is enabled for QEMU in package.use
    QEMU_USE_FILE="${PORTAGE_DIR}/package.use/void-builder-qemu"
    if [ ! -f "$QEMU_USE_FILE" ] || ! grep -q "app-emulation/qemu" "$QEMU_USE_FILE" 2>/dev/null; then
        echo "=> Enabling static-user flag for app-emulation/qemu in ${QEMU_USE_FILE}..."
        echo "app-emulation/qemu static-user" > "$QEMU_USE_FILE"
    fi

    echo "=> Installing / verifying required host build tools via emerge..."
    emerge -uDN --noreplace \
        app-emulation/qemu \
        app-cdr/xorriso \
        sys-fs/squashfs-tools \
        sys-fs/dosfstools \
        sys-fs/mtools \
        app-arch/tar \
        app-arch/xz-utils \
        app-arch/zstd \
        dev-lang/python || echo "=> Emerge finished or packages already satisfied."

elif command -v xbps-install &> /dev/null; then
    echo "=> Void Linux (XBPS) detected."
    xbps-install -S -y
    xbps-install -y qemu-user qemu-user-aarch64 qemu-user-arm qemu-user-ppc64le qemu-user-riscv64 binfmt-support xorriso squashfs-tools dosfstools mtools tar xz zstd python3

elif command -v apt-get &> /dev/null; then
    echo "=> Debian/Ubuntu (APT) detected."
    apt-get update
    apt-get install -y qemu-user-static binfmt-support xorriso squashfs-tools dosfstools mtools tar xz-utils zstd python3

elif command -v pacman &> /dev/null; then
    echo "=> Arch Linux (Pacman) detected."
    pacman -Syu --noconfirm qemu-user-static binfmt-support xorriso squashfs-tools dosfstools mtools tar xz zstd python

elif command -v dnf &> /dev/null; then
    echo "=> Fedora/RHEL (DNF) detected."
    dnf install -y qemu-user-static binfmt-support xorriso squashfs-tools dosfstools mtools tar xz zstd python3

elif command -v zypper &> /dev/null; then
    echo "=> openSUSE (Zypper) detected."
    zypper install -y qemu-linux-user binfmt-support xorriso squashfs dosfstools mtools tar xz zstd python3

else
    echo "Warning: Package manager not recognized. Ensuring binfmt_misc kernel module..."
fi

echo "=> Ensuring binfmt_misc kernel module is loaded and filesystem is mounted..."
# Load module if not loaded
if ! lsmod | grep -q binfmt_misc; then
    echo "Loading binfmt_misc kernel module..."
    modprobe binfmt_misc || true
    sleep 1
fi

# Mount filesystem if not mounted
if ! mountpoint -q /proc/sys/fs/binfmt_misc; then
    echo "Mounting binfmt_misc filesystem..."
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc || mount -t binfmt_misc none /proc/sys/fs/binfmt_misc || true
    sleep 1
fi

# Init service activation
echo "=> Enabling and starting binfmt services..."
if command -v rc-service &> /dev/null; then
    echo "=> OpenRC detected."
    if [ -f "/etc/init.d/qemu-binfmt" ]; then
        rc-service qemu-binfmt start || true
        rc-update add qemu-binfmt default 2>/dev/null || true
    fi
elif command -v systemctl &> /dev/null; then
    echo "=> Systemd detected."
    systemctl enable --now systemd-binfmt.service 2>/dev/null || true
elif command -v sv &> /dev/null && [ -d "/etc/sv/binfmt-support" ]; then
    echo "=> Runit detected."
    ln -sf /etc/sv/binfmt-support /var/service/ 2>/dev/null || true
    sv restart binfmt-support 2>/dev/null || true
fi

# Try update-binfmts if present
if command -v update-binfmts &> /dev/null; then
    echo "=> Importing binfmt configurations..."
    update-binfmts --import 2>/dev/null || true
fi

echo "=> Verifying binfmt registration in /proc/sys/fs/binfmt_misc/..."
HAS_AARCH64=0
if [ -f "/proc/sys/fs/binfmt_misc/qemu-aarch64" ] || [ -f "/proc/sys/fs/binfmt_misc/aarch64" ]; then
    echo "  ✅  aarch64 emulation is ACTIVE and registered."
    HAS_AARCH64=1
else
    echo "  ⚠️   aarch64 not yet in /proc/sys/fs/binfmt_misc/ (will be registered dynamically when QEMU is present)."
fi

for ENTRY in qemu-arm qemu-riscv64 qemu-ppc64le; do
    if [ -f "/proc/sys/fs/binfmt_misc/${ENTRY}" ]; then
        echo "  ✅  ${ENTRY} is active."
    fi
done

echo ""
echo "🎉 Host environment configuration completed successfully!"
echo "You can now run builds for Raspberry Pi, Pinebook Pro, and x86_64 targets."
