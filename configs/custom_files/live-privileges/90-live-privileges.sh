#!/bin/sh
# Sourced by runit stage 1. Never grant this exception on an installed boot.
rm -f /etc/sudoers.d/90-live-session
if grep -Eq '(^| )(rd.live.image(=1)?|root=live:[^ ]+)( |$)' /proc/cmdline && id live >/dev/null 2>&1; then
    mkdir -p /etc/sudoers.d
    printf '%s\n' 'live ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-live-session
    chown 0:0 /etc/sudoers.d/90-live-session
    chmod 440 /etc/sudoers.d/90-live-session
fi
