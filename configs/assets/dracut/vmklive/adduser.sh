#!/bin/sh
# -*- mode: shell-script; indent-tabs-mode: nil; sh-basic-offset: 4; -*-
# ex: ts=8 sw=4 sts=4 et filetype=sh

if ! type getarg >/dev/null 2>&1 && ! type getargbool >/dev/null 2>&1; then
    . /lib/dracut-lib.sh
fi

if [ ! -s ${NEWROOT}/etc/hostname ]; then
    echo void-live > ${NEWROOT}/etc/hostname
fi

USERNAME=$(getarg live.user)
USERSHELL=$(getarg live.shell)

[ -z "$USERNAME" ] && USERNAME=live
[ -x $NEWROOT/bin/bash -a -z "$USERSHELL" ] && USERSHELL=/bin/bash
[ -z "$USERSHELL" ] && USERSHELL=/bin/sh

# Create /etc/default/live.conf to store USER.
echo "USERNAME=$USERNAME" >> ${NEWROOT}/etc/default/live.conf
chmod 644 ${NEWROOT}/etc/default/live.conf

if ! grep -q "^${USERSHELL}$" ${NEWROOT}/etc/shells 2>/dev/null; then
    echo ${USERSHELL} >> ${NEWROOT}/etc/shells
fi

# Ensure autologin group exists
chroot ${NEWROOT} groupadd -r autologin 2>/dev/null || true

# Create new user and remove password. We'll use autologin by default.
if ! chroot ${NEWROOT} id -u $USERNAME >/dev/null 2>&1; then
    chroot ${NEWROOT} useradd -m -c "$USERNAME" -G audio,video,wheel,storage,network,input,dialout,kvm,lp,lpadmin,scanner,users,autologin -s $USERSHELL $USERNAME
else
    chroot ${NEWROOT} usermod -aG audio,video,wheel,storage,network,input,dialout,kvm,lp,lpadmin,scanner,users,autologin $USERNAME 2>/dev/null || true
fi
chroot ${NEWROOT} passwd -d $USERNAME >/dev/null 2>&1

# Setup default root/user password (voidlinux).
chroot ${NEWROOT} sh -c 'echo "root:voidlinux" | chpasswd -c SHA512' 2>/dev/null || true
chroot ${NEWROOT} sh -c "echo \"$USERNAME:voidlinux\" | chpasswd -c SHA512" 2>/dev/null || true

# Enable sudo permission by default with correct 0440 mode
if [ -d ${NEWROOT}/etc/sudoers.d ]; then
    echo "${USERNAME} ALL=(ALL:ALL) NOPASSWD: ALL" > "${NEWROOT}/etc/sudoers.d/99-void-live"
    echo "%wheel ALL=(ALL:ALL) NOPASSWD: ALL" >> "${NEWROOT}/etc/sudoers.d/99-void-live"
    chmod 440 "${NEWROOT}/etc/sudoers.d/99-void-live" 2>/dev/null || true
elif [ -f ${NEWROOT}/etc/sudoers ]; then
    echo "${USERNAME} ALL=(ALL:ALL) NOPASSWD: ALL" >> "${NEWROOT}/etc/sudoers"
fi

if [ -d ${NEWROOT}/etc/polkit-1 ]; then
    # If polkit is installed allow users in the wheel group to run anything.
    cat > ${NEWROOT}/etc/polkit-1/rules.d/void-live.rules <<_EOF
polkit.addAdminRule(function(action, subject) {
    return ["unix-group:wheel"];
});

polkit.addRule(function(action, subject) {
    if (subject.isInGroup("wheel") || subject.isInGroup("autologin")) {
        return polkit.Result.YES;
    }
});
_EOF
    chroot ${NEWROOT} chown polkitd:polkitd /etc/polkit-1/rules.d/void-live.rules 2>/dev/null || true
fi

if getargbool 0 live.autologin; then
    if [ -f "${NEWROOT}/etc/sv/agetty-tty1/conf" ]; then
        sed -i "s,GETTY_ARGS=\"--noclear\",GETTY_ARGS=\"--noclear -a $USERNAME\",g" ${NEWROOT}/etc/sv/agetty-tty1/conf
    fi
fi
