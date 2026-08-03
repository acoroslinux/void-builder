#!/bin/sh
# Critical configuration for Void Linux Live: Launch the session within DBUS
# so that Polkit, pkexec, and Elogind work without blank screens.

# Disable screen locking and screensaver for the Live environment
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/lock-screen-suspend-hibernate -n -t bool -s false 2>/dev/null || true
xfconf-query -c xfce4-session -p /general/LockCommand -n -t string -s "" 2>/dev/null || true
xset s off -dpms 2>/dev/null || true

exec dbus-run-session startxfce4
