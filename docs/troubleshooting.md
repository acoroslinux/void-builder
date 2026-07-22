# Troubleshooting & FAQ

This document addresses common issues, error messages, and solutions when working with **Void-Builder**.

---

## Common Issues & Solutions

### 1. `Permission denied` on `workdir/cache` or loop devices
- **Cause**: Running real mode without `sudo` privileges.
- **Solution**: Execute the command using `sudo`:
  ```bash
  sudo python3 cli.py x86_64 --mode real
  ```

### 2. `Root privileges are required to generate platform images via loop devices`
- **Cause**: Single-board computer images (`.img`) require `losetup`, `sfdisk`, and `mount` which need root access.
- **Solution**: Run with `sudo`, or use `--mode mock` if you are only testing configurations.

### 3. Cross-architecture builds fail to execute commands inside chroot
- **Cause**: QEMU user emulators (`qemu-user-static`) or `binfmt_misc` kernel module are not configured on the host machine.
- **Solution**: Run the host setup helper script:
  ```bash
  sudo ./setup_host_build_env.sh
  ```

### 4. `xorriso reported an exit error/crash`
- **Cause**: Missing `xorriso` utility or corrupted `efiboot.img`.
- **Solution**: Install `xorriso` on your host machine (`xbps-install -S xorriso` or `apt-get install xorriso`).

### 5. `ConfigValidationFailed` error on `--check`
- **Cause**: Referenced desktop, kernel, or bootloader profile JSON file does not exist in `configs/`.
- **Solution**: Check spelling of profile names or verify file path in `configs/desktops/` or `configs/architectures/`.

---

## Log Inspection

Detailed build logs are written to `void_builder.log` at the project root and printed to stdout when using `-v` (`--verbose`).

```bash
python3 cli.py x86_64 -v --mode mock
```
