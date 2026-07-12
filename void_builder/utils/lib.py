"""
lib.py - Central utility library for void_builder.
Equivalent to void-mklive's lib.sh.
"""

import os
import platform
import glob
from typing import Optional, List

from void_builder.utils.command import CommandRunner


def info_msg(msg):
    print(f"\033[1m{msg}\033[0m")

def step_msg(current, total, msg):
    info_msg(f"[{current}/{total}] {msg}")

def warn_msg(msg):
    print(f"\033[93m[WARN]\033[0m {msg}")

def error_msg(msg):
    print(f"\033[91m[ERROR]\033[0m {msg}")


def get_host_arch():
    """Returns the host architecture in XBPS format."""
    machine = platform.machine()
    m = {
        'x86_64': 'x86_64', 'i686': 'i686', 'i386': 'i686',
        'aarch64': 'aarch64', 'armv7l': 'armv7l', 'armv6l': 'armv6l',
        'riscv64': 'riscv64', 'ppc64le': 'ppc64le', 'ppc64': 'ppc64',
    }
    return m.get(machine, machine)


def is_target_native(target_arch):
    """Check whether target binaries can run natively on the host."""
    host = get_host_arch()
    hb = host.replace('-musl', '')
    tb = target_arch.replace('-musl', '')
    if hb == tb:
        return True
    if hb == 'ppc64le':
        return False
    if hb == 'x86_64' and '86' in tb:
        return True
    if hb == 'aarch64' and tb.startswith('armv'):
        return True
    if hb == 'ppc64' and tb == 'ppc':
        return True
    return False


def _qemu_cpu_name(target_arch):
    """Map XBPS target arch to QEMU CPU name."""
    base = target_arch.replace('-musl', '')
    m = {
        'i686': 'i386', 'armv5tel': 'arm', 'armv6l': 'arm',
        'armv7l': 'arm', 'aarch64': 'aarch64', 'mipsel': 'mipsel',
        'ppc': 'ppc', 'ppc64': 'ppc64', 'ppc64le': 'ppc64le',
        'riscv64': 'riscv64',
    }
    return m.get(base)


def setup_qemu_binfmt(target_arch):
    """Set up QEMU user-static binfmt_misc for cross-arch builds."""
    if is_target_native(target_arch):
        return True
    cpu = _qemu_cpu_name(target_arch)
    if cpu is None:
        error_msg(f"Unknown target architecture for QEMU: {target_arch}")
        return False
    qemu_bin = f"qemu-{cpu}-static"
    rc, _, _ = CommandRunner.run([qemu_bin, '-version'], check=False, capture_output=True)
    if rc != 0:
        qemu_bin = f"qemu-{cpu}"
        rc, _, _ = CommandRunner.run([qemu_bin, '-version'], check=False, capture_output=True)
        if rc != 0:
            error_msg(f"QEMU binary not found: qemu-{cpu}-static or qemu-{cpu}")
            return False
    bp = '/proc/sys/fs/binfmt_misc'
    if not os.path.isdir(bp):
        CommandRunner.run(['modprobe', '-q', 'binfmt_misc'], check=False)
        CommandRunner.run(['mount', '-t', 'binfmt_misc', 'binfmt_misc', bp], check=False)
    rf = os.path.join(bp, f"qemu-{cpu}")
    if not os.path.exists(rf):
        rc, _, _ = CommandRunner.run(['update-binfmts', '--import', f'qemu-{cpu}'], check=False)
        if rc != 0:
            warn_msg(f"Could not register binfmt for qemu-{cpu}")
            return False
    return True


def mount_pseudofs(rootfs):
    """Mount /dev, /proc, /sys into the rootfs."""
    for fs in ('dev', 'proc', 'sys'):
        target = os.path.join(rootfs, fs)
        os.makedirs(target, exist_ok=True)
        rc, _, _ = CommandRunner.run(['mountpoint', '-q', target], check=False, capture_output=True)
        if rc == 0:
            continue
        rc, _, stderr = CommandRunner.run(
            ['mount', '-r', '--rbind', f'/{fs}', target, '--make-rslave'], check=False)
        if rc != 0:
            error_msg(f"Failed to mount {fs}: {stderr}")
            return False
    return True


def umount_pseudofs(rootfs):
    """Unmount /dev, /proc, /sys from the rootfs."""
    success = True
    for fs in ('dev', 'proc', 'sys'):
        target = os.path.join(rootfs, fs)
        if os.path.isdir(target):
            rc, _, stderr = CommandRunner.run(['umount', '-R', '-f', target], check=False)
            if rc != 0:
                warn_msg(f"Failed to unmount {target}: {stderr}")
                success = False
    return success


def run_cmd_chroot(rootfs, command, env=None, check=True):
    """Run a command inside the rootfs using chroot."""
    chroot_cmd = ['chroot', rootfs, '/bin/sh', '-c', command]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return CommandRunner.run(chroot_cmd, env=merged_env, check=check)


def run_cmd_target(command, target_arch, check=True):
    """Run a command with XBPS_ARCH set to the target architecture."""
    merged_env = os.environ.copy()
    merged_env['XBPS_ARCH'] = target_arch
    return CommandRunner.run(command, env=merged_env, check=check)


def cleanup_chroot(rootfs):
    """Remove QEMU shims and unmount pseudofs."""
    for path in glob.glob(os.path.join(rootfs, 'usr', 'bin', 'qemu-*-static')):
        try:
            os.remove(path)
        except OSError:
            pass
    umount_pseudofs(rootfs)


def get_mklive_dir():
    """Return the path to the void-mklive directory."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, 'void-mklive')


def get_tools_dir():
    """Return the path to the tools directory for static binaries."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools')


def ensure_dir(path):
    """Create a directory if it doesn't exist and return its path."""
    os.makedirs(path, exist_ok=True)
    return path