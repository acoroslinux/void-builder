#!/bin/bash
# ==============================================================================
# Void Modern Installer - Universal Desktop Icon Creation Script
# ==============================================================================

# Check if the system is in live mode
if grep -qE "live\.user=|boot=live|rd\.live|live\.autologin" /proc/cmdline || [ -d /run/rootfsbase ] || [ -d /run/initramfs/live ] || [ -f /etc/default/live.conf ]; then
    LIVE_USER="live"
    if [ -f /etc/default/live.conf ]; then
        . /etc/default/live.conf
        [ -n "$USERNAME" ] && LIVE_USER="$USERNAME"
    fi

    # Path to the live user's Desktop directory
    desktop_dir="/home/${LIVE_USER}/Desktop"
    mkdir -p "$desktop_dir"

    # --- Desktop Entry Creation ---
    cat << EOF > "$desktop_dir/Install Void Modern.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Install Void Modern
Name[es]=Instalar Void Modern
Name[fr]=Installer Void Modern
Name[pt]=Instalar Void Modern
Name[pt_BR]=Instalar Void Modern
Comment=Install Void Modern to disk
Exec=pkexec calamares
Icon=calamares
Terminal=false
Categories=System;
StartupNotify=true
EOF

    # --- Permissions ---
    chmod +x "$desktop_dir/Install Void Modern.desktop"
    chown "${LIVE_USER}:${LIVE_USER}" "$desktop_dir/Install Void Modern.desktop" 2>/dev/null

    # --- Desktop Specific Configurations ---
    # 1. GNOME/XFCE/Mate/Cinnamon (GIO Metadata)
    gio set --type=string "$desktop_dir/Install Void Modern.desktop" metadata::trusted true 2>/dev/null
    
    # Specific checksum for XFCE to bypass "Untrusted Launcher"
    gio set --type=string "$desktop_dir/Install Void Modern.desktop" metadata::xfce-exe-checksum \
        "$(sha256sum "$desktop_dir/Install Void Modern.desktop" | cut -f1 -d' ')" 2>/dev/null

    # 2. KDE Plasma Support
    if command -v kbuildsycoca5 >/dev/null 2>&1; then
        sudo -u "$LIVE_USER" kbuildsycoca5 --noincremental 2>/dev/null
    fi
    if command -v kbuildsycoca6 >/dev/null 2>&1; then
        sudo -u "$LIVE_USER" kbuildsycoca6 --noincremental 2>/dev/null
    fi

    # --- Finalize ---
    touch "$desktop_dir/Install Void Modern.desktop"
    
    echo "✓ Void Modern Installer icon created and optimized for desktop user ${LIVE_USER}."
fi