#!/bin/sh
set -eu
for file in /etc/passwd /etc/group; do
    chown 0:0 "$file"
    chmod 644 "$file"
done
chown 0:0 /etc/shadow
chmod 600 /etc/shadow
for file in /etc/gshadow /etc/shadow- /etc/gshadow- /etc/security/opasswd /etc/security/opasswd.old; do
    if [ -f "$file" ]; then
        chown 0:0 "$file"
        chmod 600 "$file"
    fi
done
for directory in /etc/pam.d /etc/security; do
    if [ -d "$directory" ]; then
        find "$directory" -type d -exec chown 0:0 {} +
        find "$directory" -type d -exec chmod 755 {} +
    fi
done
if [ -d /etc/pam.d ]; then
    find /etc/pam.d -type f -exec chown 0:0 {} +
    find /etc/pam.d -type f -exec chmod 644 {} +
fi
if [ -d /etc/security ]; then
    find /etc/security -type f -name '*.conf' -exec chown 0:0 {} +
    find /etc/security -type f -name '*.conf' -exec chmod 644 {} +
fi
if [ -f /etc/sudoers ]; then
    chown 0:0 /etc/sudoers
    chmod 440 /etc/sudoers
fi
if [ -d /etc/sudoers.d ]; then
    find /etc/sudoers.d -type d -exec chown 0:0 {} +
    find /etc/sudoers.d -type d -exec chmod 750 {} +
    find /etc/sudoers.d -type f -exec chown 0:0 {} +
    find /etc/sudoers.d -type f -exec chmod 440 {} +
fi
for file in /usr/bin/passwd /usr/bin/su /usr/bin/sudo /usr/bin/chfn /usr/bin/chsh /usr/bin/newgrp /usr/bin/gpasswd /usr/bin/unix_chkpwd /usr/bin/pkexec /usr/lib/polkit-1/polkit-agent-helper-1; do
    if [ -f "$file" ]; then
        chown 0:0 "$file"
        chmod 4755 "$file"
    fi
done
if [ -x /usr/bin/visudo ]; then
    /usr/bin/visudo -c
fi
