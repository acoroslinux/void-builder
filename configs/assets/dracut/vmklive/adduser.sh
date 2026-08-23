#!/bin/sh -x
# -*- mode: shell-script; indent-tabs-mode: nil; sh-basic-offset: 4; -*-
# ex: ts=8 sw=4 sts=4 et filetype=sh

if ! type getarg >/dev/null 2>&1 && ! type getargbool >/dev/null 2>&1; then
    . /lib/dracut-lib.sh
fi

# Save hostname only if it's empty or not configured yet
if [ ! -s ${NEWROOT}/etc/hostname ]; then
    echo void-live > ${NEWROOT}/etc/hostname
fi

USERNAME=$(getarg live.user)
USERSHELL=$(getarg live.shell)
PASSWORD=$(getarg live.password)
ROOTPASSWORD=$(getarg live.rootpassword)

[ -z "$USERNAME" ] && USERNAME=live
[ -z "$PASSWORD" ] && PASSWORD=live
[ -z "$ROOTPASSWORD" ] && ROOTPASSWORD=voidlinux
[ -x $NEWROOT/bin/bash -a -z "$USERSHELL" ] && USERSHELL=/bin/bash
[ -z "$USERSHELL" ] && USERSHELL=/bin/sh

# Create /etc/default/live.conf to store USER.
echo "USERNAME=$USERNAME" >> ${NEWROOT}/etc/default/live.conf
chmod 644 ${NEWROOT}/etc/default/live.conf

if ! grep -q "^${USERSHELL}$" ${NEWROOT}/etc/shells 2>/dev/null; then
    echo ${USERSHELL} >> ${NEWROOT}/etc/shells
fi

# Ensure user groups exist
for grp in wheel audio video storage network input dialout kvm lp lpadmin scanner users rpc _rpc; do
    chroot ${NEWROOT} sh -c "getent group $grp >/dev/null 2>&1 || groupadd -r $grp 2>/dev/null || groupadd $grp"
done
chroot ${NEWROOT} sh -c "getent passwd rpc >/dev/null 2>&1 || useradd -r -M -g rpc -d /var/empty -s /bin/false rpc 2>/dev/null || true"
chroot ${NEWROOT} sh -c "getent passwd _rpc >/dev/null 2>&1 || useradd -r -M -g _rpc -d /var/empty -s /bin/false _rpc 2>/dev/null || true"

# Create new user if not exists, and set password with SHA512
if ! chroot ${NEWROOT} id -u $USERNAME >/dev/null 2>&1; then
    chroot ${NEWROOT} useradd -m -c "$USERNAME" -G audio,video,wheel,storage,network,input,dialout,kvm,lp,lpadmin,scanner,users -s $USERSHELL $USERNAME
else
    chroot ${NEWROOT} usermod -aG audio,video,wheel,storage,network,input,dialout,kvm,lp,lpadmin,scanner,users $USERNAME 2>/dev/null
fi

# Explicitly set the live user password with SHA-512 hashing
chroot ${NEWROOT} sh -c "echo \"$USERNAME:$PASSWORD\" | chpasswd -c SHA512"

# Setup root password with SHA-512 hashing
chroot ${NEWROOT} sh -c "echo \"root:$ROOTPASSWORD\" | chpasswd -c SHA512"

# Ensure user home permissions
chroot ${NEWROOT} sh -c "mkdir -p /home/$USERNAME && chown -R $USERNAME:$USERNAME /home/$USERNAME"

# Fix shadow and PAM permissions strictly
chmod 600 ${NEWROOT}/etc/shadow 2>/dev/null
chmod 644 ${NEWROOT}/etc/passwd 2>/dev/null
chmod 644 ${NEWROOT}/etc/group 2>/dev/null
[ -f ${NEWROOT}/etc/gshadow ] && chmod 600 ${NEWROOT}/etc/gshadow 2>/dev/null
chown root:root ${NEWROOT}/etc/shadow ${NEWROOT}/etc/passwd ${NEWROOT}/etc/group 2>/dev/null
[ -f ${NEWROOT}/etc/gshadow ] && chown root:root ${NEWROOT}/etc/gshadow 2>/dev/null

# Fix SUID permissions on critical PAM / auth binaries
for suid_bin in /usr/bin/passwd /usr/bin/su /usr/bin/sudo /usr/bin/chfn /usr/bin/chsh /usr/bin/newgrp /usr/bin/gpasswd /usr/bin/unix_chkpwd /sbin/unix_chkpwd /usr/libexec/polkit-1/polkit-agent-helper-1; do
    if [ -f "${NEWROOT}${suid_bin}" ]; then
        chmod 4755 "${NEWROOT}${suid_bin}" 2>/dev/null
        chown root:root "${NEWROOT}${suid_bin}" 2>/dev/null
    fi
done

# Enable sudo permission by default with correct strict permissions (0440)
if [ -f ${NEWROOT}/etc/sudoers ]; then
    chmod 440 ${NEWROOT}/etc/sudoers 2>/dev/null
    chown root:root ${NEWROOT}/etc/sudoers 2>/dev/null
    mkdir -p "${NEWROOT}/etc/sudoers.d"
    chmod 750 "${NEWROOT}/etc/sudoers.d" 2>/dev/null
    chown root:root "${NEWROOT}/etc/sudoers.d" 2>/dev/null
    echo "${USERNAME} ALL=(ALL:ALL) NOPASSWD: ALL" > "${NEWROOT}/etc/sudoers.d/99-void-live"
    echo "%wheel ALL=(ALL:ALL) NOPASSWD: ALL" >> "${NEWROOT}/etc/sudoers.d/99-void-live"
    chmod 440 ${NEWROOT}/etc/sudoers.d/* 2>/dev/null
    chown -R root:root "${NEWROOT}/etc/sudoers.d" 2>/dev/null
fi

if [ -d ${NEWROOT}/etc/polkit-1 ]; then
    # If polkit is installed allow users in the wheel group to run anything.
    cat > ${NEWROOT}/etc/polkit-1/rules.d/void-live.rules <<_EOF
polkit.addAdminRule(function(action, subject) {
    return ["unix-group:wheel"];
});

polkit.addRule(function(action, subject) {
    if (subject.isInGroup("wheel")) {
        return polkit.Result.YES;
    }
});
_EOF
    chroot ${NEWROOT} chown polkitd:polkitd /etc/polkit-1/rules.d/void-live.rules 2>/dev/null
fi

if getargbool 0 live.autologin; then
    if [ -f "${NEWROOT}/etc/sv/agetty-tty1/conf" ]; then
        sed -i "s,GETTY_ARGS=\"--noclear\",GETTY_ARGS=\"--noclear -a $USERNAME\",g" ${NEWROOT}/etc/sv/agetty-tty1/conf
    fi
fi
