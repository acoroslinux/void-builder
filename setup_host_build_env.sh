#!/bin/bash

# ==============================================================================
# SCRIPT: setup_host_build_env.sh
# PURPOSE: Configures the host system strictly for cross-architecture ISO and
#          image building (QEMU user-static emulators and binfmt_misc support).
# ==============================================================================

set -e

# Require root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run this script with sudo."
    exit 1
fi

echo "========================================================"
echo " 🌐 Setting up Host for Cross-Architecture Builds"
echo "========================================================"

# 1. Install QEMU User Static Emulators and binfmt support based on distro
if command -v emerge &> /dev/null; then
    echo "=> Gentoo Linux (Portage) detected."
    
    # Configure QEMU user targets and static library dependencies in package.use
    mkdir -p /etc/portage/package.use
    QEMU_USE="/etc/portage/package.use/qemu-cross-build"
    
    echo "=> Configuring ${QEMU_USE} with required static-libs flags..."
    cat << 'PORTAGE_EOF' > "$QEMU_USE"
# void-builder cross-compilation dependencies
app-emulation/qemu static-user
app-emulation/qemu QEMU_USER_TARGETS: aarch64 arm riscv64 x86_64 i386
virtual/zlib static-libs
sys-libs/zlib static-libs
virtual/libintl static-libs
virtual/libiconv static-libs
virtual/libffi static-libs
dev-libs/libffi static-libs
dev-libs/glib static-libs
dev-libs/libpcre2 static-libs
sys-apps/attr static-libs
sys-libs/libcap static-libs
app-arch/bzip2 static-libs
app-arch/xz-utils static-libs
app-arch/zstd static-libs
dev-libs/lzo static-libs
PORTAGE_EOF

    echo "=> Installing app-emulation/qemu via emerge..."
    emerge -uDN --autounmask-write=y --autounmask-continue=y --noreplace app-emulation/qemu || true

elif command -v xbps-install &> /dev/null; then
    echo "=> Void Linux (XBPS) detected."
    xbps-install -S -y
    xbps-install -y qemu-user qemu-user-aarch64 qemu-user-arm qemu-user-riscv64 binfmt-support

elif command -v apt-get &> /dev/null; then
    echo "=> Debian/Ubuntu (APT) detected."
    apt-get update
    apt-get install -y qemu-user-static binfmt-support

elif command -v pacman &> /dev/null; then
    echo "=> Arch Linux (Pacman) detected."
    pacman -Syu --noconfirm qemu-user-static binfmt-support

elif command -v dnf &> /dev/null; then
    echo "=> Fedora/RHEL (DNF) detected."
    dnf install -y qemu-user-static

elif command -v zypper &> /dev/null; then
    echo "=> openSUSE (Zypper) detected."
    zypper install -y qemu-linux-user binfmt-support
fi

# 2. Ensure binfmt_misc kernel module is loaded
echo "=> Ensuring binfmt_misc kernel module is active..."
if ! lsmod | grep -q binfmt_misc; then
    modprobe binfmt_misc || true
fi

# 3. Mount /proc/sys/fs/binfmt_misc if needed
if ! mountpoint -q /proc/sys/fs/binfmt_misc; then
    echo "=> Mounting /proc/sys/fs/binfmt_misc..."
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null || \
    mount -t binfmt_misc none /proc/sys/fs/binfmt_misc 2>/dev/null || true
fi

# 4. Enable binfmt service for current init system
echo "=> Activating binfmt services..."
if command -v rc-service &> /dev/null && [ -f "/etc/init.d/qemu-binfmt" ]; then
    rc-service qemu-binfmt start 2>/dev/null || true
    rc-update add qemu-binfmt default 2>/dev/null || true
elif command -v systemctl &> /dev/null; then
    systemctl enable --now systemd-binfmt.service 2>/dev/null || true
elif command -v sv &> /dev/null && [ -d "/etc/sv/binfmt-support" ]; then
    ln -sf /etc/sv/binfmt-support /var/service/ 2>/dev/null || true
    sv restart binfmt-support 2>/dev/null || true
fi

# 5. Import binfmts if update-binfmts exists
if command -v update-binfmts &> /dev/null; then
    update-binfmts --import 2>/dev/null || true
fi

# 6. Verify cross-architecture emulation readiness
echo "--------------------------------------------------------"
echo "🔍 Cross-Architecture Emulation Status:"
if [ -f "/proc/sys/fs/binfmt_misc/qemu-aarch64" ] || [ -f "/proc/sys/fs/binfmt_misc/aarch64" ]; then
    echo "  ✅ AArch64 / ARM64 (Raspberry Pi, Pinebook Pro, X13s): READY"
else
    echo "  ⚠️  AArch64 binfmt registration pending (active once QEMU binaries are in path)."
fi

if [ -f "/proc/sys/fs/binfmt_misc/qemu-arm" ] || [ -f "/proc/sys/fs/binfmt_misc/arm" ]; then
    echo "  ✅ ARM 32-bit (armv7l, armv6l): READY"
fi

if [ -f "/proc/sys/fs/binfmt_misc/qemu-riscv64" ] || [ -f "/proc/sys/fs/binfmt_misc/riscv64" ]; then
    echo "  ✅ RISC-V 64-bit: READY"
fi

echo "========================================================"
echo "🎉 Host cross-build environment configured successfully!"
echo "========================================================"
