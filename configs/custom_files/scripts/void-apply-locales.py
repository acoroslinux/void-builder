#!/usr/bin/python3
"""Generate every locale selected by Calamares, preserving its language settings."""
from pathlib import Path
import re
import subprocess


def apply_locales(root=Path('/'), run=subprocess.run):
    config = root / 'etc/locale.conf'
    values = {}
    for line in config.read_text().splitlines():
        key, separator, value = line.partition('=')
        key = key.strip()
        if separator and (key == 'LANG' or key.startswith('LC_')):
            value = value.strip().strip('\"\'')
            if not re.fullmatch(r'[A-Za-z0-9_.@-]+', value):
                raise ValueError(f'Invalid locale for {key}')
            values[key] = value
    if not values.get('LANG'):
        raise ValueError('Calamares did not write LANG in /etc/locale.conf')
    normalized = ''.join(f'{key}={value}\n' for key, value in values.items())
    config.write_text(normalized)
    default = root / 'etc/default'
    default.mkdir(parents=True, exist_ok=True)
    (default / 'locale').write_text(normalized)
    supported = default / 'libc-locales'
    if not supported.exists():  # musl has no glibc locale archive
        return
    requested = set(values.values()) - {'C', 'POSIX', 'C.UTF-8', 'C.utf8'}
    found = set()
    lines = []
    for line in supported.read_text().splitlines():
        candidate = line.lstrip('# ').split()
        if candidate and candidate[0] in requested:
            found.add(candidate[0])
            line = line.lstrip('# ')
        lines.append(line)
    if requested - found:
        raise ValueError(f'Unsupported locales: {sorted(requested - found)}')
    supported.write_text('\n'.join(lines) + '\n')
    run(['xbps-reconfigure', '-f', 'glibc-locales'], check=True)


if __name__ == '__main__':
    apply_locales()
