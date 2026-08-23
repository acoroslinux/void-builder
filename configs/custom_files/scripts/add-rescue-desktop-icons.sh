#!/bin/bash
# ==============================================================================
# Void / Peppermint Rescue Edition - Desktop Shortcuts Generator
# ==============================================================================

# Only proceed in live environment and if rescue tools are installed
if [ ! -x /usr/bin/testdisk ] && [ ! -x /usr/bin/gparted ] && [ ! -x /usr/bin/ddrescue ] && ! command -v testdisk >/dev/null 2>&1; then
    exit 0
fi

if grep -qE "live\.user=|boot=live|rd\.live|live\.autologin" /proc/cmdline || [ -d /run/rootfsbase ] || [ -d /run/initramfs/live ] || [ -f /etc/default/live.conf ]; then
    LIVE_USER="live"
    if [ -f /etc/default/live.conf ]; then
        . /etc/default/live.conf
        [ -n "$USERNAME" ] && LIVE_USER="$USERNAME"
    fi

    desktop_dir="/home/${LIVE_USER}/Desktop"
    mkdir -p "$desktop_dir"

    # 1. GParted
    if command -v gparted >/dev/null 2>&1 || [ -x /usr/bin/gparted ]; then
        cat << 'EOF' > "$desktop_dir/GParted.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=GParted Partition Editor
Name[pt]=Gestor de Partições GParted
Comment=Create, reorganize, and delete disk partitions
Exec=sudo -E gparted
Icon=gparted
Terminal=false
Categories=System;Filesystem;
StartupNotify=true
EOF
    fi

    # 2. Wireshark
    if command -v wireshark >/dev/null 2>&1 || [ -x /usr/bin/wireshark ]; then
        cat << 'EOF' > "$desktop_dir/Wireshark.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Wireshark Network Analyzer
Name[pt]=Analisador de Rede Wireshark
Comment=Network traffic packet capture and analysis
Exec=wireshark
Icon=wireshark
Terminal=false
Categories=Network;System;
StartupNotify=true
EOF
    fi

    # 3. TestDisk
    if command -v testdisk >/dev/null 2>&1 || [ -x /usr/bin/testdisk ]; then
        cat << 'EOF' > "$desktop_dir/TestDisk Recovery.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=TestDisk Partition Recovery
Name[pt]=Recuperação de Partições TestDisk
Comment=Scan, repair and recover lost disk partitions
Exec=xfce4-terminal --title="TestDisk Partition Recovery" --geometry=100x30 -e "sudo testdisk"
Icon=utilities-system-monitor
Terminal=false
Categories=System;
StartupNotify=true
EOF
    fi

    # 4. PhotoRec
    if command -v photorec >/dev/null 2>&1 || [ -x /usr/bin/photorec ]; then
        cat << 'EOF' > "$desktop_dir/PhotoRec Undelete.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=PhotoRec File Undelete
Name[pt]=Recuperação de Ficheiros PhotoRec
Comment=Carve and recover lost files and photos from damaged drives
Exec=xfce4-terminal --title="PhotoRec File Undelete" --geometry=100x30 -e "sudo photorec"
Icon=system-file-manager
Terminal=false
Categories=System;
StartupNotify=true
EOF
    fi

    # 5. Disk Health (smartctl / nvme)
    cat << 'EOF' > "$desktop_dir/Disk Health Check.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Disk Health Diagnostics
Name[pt]=Diagnóstico de Saúde de Discos
Comment=Inspect SMART health and NVMe metrics
Exec=xfce4-terminal --title="Disk SMART & Health Diagnostics" --geometry=110x35 -e "bash -c 'echo \"===================================================\"; echo \" 🔍 AVAILABLE DISKS & NVMe DRIVES:\"; echo \"===================================================\"; sudo smartctl --scan; echo; lsblk -o NAME,SIZE,TYPE,FSTYPE,MODEL; echo; echo \"Type device name (e.g. /dev/sda or /dev/nvme0n1) for detailed SMART report:\"; read -p \"Target Device: \" dev; if [ -n \"\$dev\" ]; then sudo smartctl -a \"\$dev\" | less; fi'"
Icon=drive-harddisk
Terminal=false
Categories=System;
StartupNotify=true
EOF

    # 6. Hardware Information (inxi)
    cat << 'EOF' > "$desktop_dir/Hardware Information.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Hardware & System Info
Name[pt]=Informações de Hardware e Sistema
Comment=Complete hardware and system sensor inventory
Exec=xfce4-terminal --title="Hardware & System Information" --geometry=115x35 -e "bash -c 'sudo inxi -Fzxxx; echo; read -n 1 -s -r -p \"Press any key to close...\";'"
Icon=dialog-information
Terminal=false
Categories=System;
StartupNotify=true
EOF

    # --- Permissions and metadata ---
    for f in "$desktop_dir"/*.desktop; do
        [ -f "$f" ] || continue
        chmod +x "$f"
        chown "${LIVE_USER}:${LIVE_USER}" "$f" 2>/dev/null
        gio set --type=string "$f" metadata::trusted true 2>/dev/null
        gio set --type=string "$f" metadata::xfce-exe-checksum "$(sha256sum "$f" | cut -f1 -d' ')" 2>/dev/null
        touch "$f"
    done

    echo "✓ Rescue Desktop icons generated for user ${LIVE_USER}."
fi
