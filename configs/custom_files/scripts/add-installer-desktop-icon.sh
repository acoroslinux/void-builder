#!/bin/bash
# ==============================================================================
# Void Modern Installer - Universal Desktop Icon Creation Script
# ==============================================================================

# Check if the system is in live mode by checking the root filesystem type
root_fs_type=$(findmnt -n -o FSTYPE /)

# If the root filesystem is overlay or squashfs, we are likely in live mode
if [ "$root_fs_type" == "overlay" ] || [ "$root_fs_type" == "squashfs" ]; then
    # Path to the live user's Desktop directory
    desktop_dir="/home/live/Desktop"
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
Exec=pkexec python3 /usr/share/void_installer/launch_installer.py
Icon=system-software-install
Terminal=false
Categories=System;
StartupNotify=true
EOF

    # --- Permissions ---
    # Set permissions for the .desktop file
    chmod +x "$desktop_dir/Install Void Modern.desktop"
    chown live:live "$desktop_dir/Install Void Modern.desktop" 2>/dev/null

    # --- Desktop Specific Configurations ---

    # 1. GNOME/XFCE/Mate/Cinnamon (GIO Metadata)
    # Marking the desktop launcher as trusted
    gio set --type=string "$desktop_dir/Install Void Modern.desktop" metadata::trusted true 2>/dev/null
    
    # Specific checksum for XFCE to bypass "Untrusted Launcher"
    gio set --type=string "$desktop_dir/Install Void Modern.desktop" metadata::xfce-exe-checksum \
        "$(sha256sum "$desktop_dir/Install Void Modern.desktop" | cut -f1 -d' ')" 2>/dev/null

    # 2. KDE Plasma Support
    if command -v kbuildsycoca5 >/dev/null 2>&1; then
        sudo -u live kbuildsycoca5 --noincremental 2>/dev/null
    fi

    # --- Finalize ---
    # Update the timestamp for the .desktop file
    touch "$desktop_dir/Install Void Modern.desktop"
    
    echo "✓ Void Modern Installer icon created and optimized for desktops."
fi