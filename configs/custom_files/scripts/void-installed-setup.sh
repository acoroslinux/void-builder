#!/bin/sh
# Run inside the installed system, after Calamares creates the user.
set -eu

mkdir -p /etc/runit/runsvdir/default

for srv in dbus NetworkManager polkitd bluetoothd cupsd avahi-daemon sshd chronyd alsa acpid elogind ufw tlp; do
    if [ -d "/etc/sv/$srv" ]; then
        ln -sf "/etc/sv/$srv" "/etc/runit/runsvdir/default/$srv"
    fi
done

HNAME=$(cat /etc/hostname 2>/dev/null || printf '%s' void-installed)
printf '127.0.0.1\tlocalhost\n::1\tlocalhost ip6-localhost ip6-loopback\n127.0.1.1\t%s.localdomain %s\n' "$HNAME" "$HNAME" > /etc/hosts

rm -f /etc/sudoers.d/99-void-live /etc/sudoers.d/10-wheel /etc/sudoers.d/99-live-user /etc/sudoers.d/90-live-session /etc/runit/core-services/90-live-privileges.sh /etc/polkit-1/rules.d/49-nopasswd-calamares.rules /etc/default/live.conf /etc/xdg/autostart/create-install-icon.desktop /usr/share/applications/calamares.desktop /etc/lightdm/lightdm.conf.d/live.conf /etc/sddm.conf.d/live.conf /etc/sddm.conf.d/autologin.conf /etc/lightdm/.session

rm -rf /usr/lib/dracut/modules.d/01vmklive

[ -f /etc/sv/agetty-tty1/conf ] && sed -i 's,GETTY_ARGS=.*,GETTY_ARGS="--noclear",g' /etc/sv/agetty-tty1/conf || true

[ -f /usr/bin/plymouth-set-default-theme ] && echo 'add_dracutmodules+=" plymouth "' > /etc/dracut.conf.d/plymouth.conf || true

/usr/bin/xbps-reconfigure -fa

mkdir -p /etc/sudoers.d

printf '%s
' '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-installed-wheel

/bin/sh /usr/local/bin/void-fix-auth-permissions.sh

/usr/bin/python3 /usr/local/bin/void-apply-locales.py
