#!/bin/sh
# Example post-install hook: executed inside the chroot rootfs after system configuration
echo "[HOOK] Running post-install script inside chroot..."
# Example: write a custom build stamp
echo "Void-Builder Custom Release $(date -u +%Y%m%d)" > /etc/void-builder-release
