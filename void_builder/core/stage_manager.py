import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from void_builder.core.path_utils import resolve_from_project
from void_builder.utils.logger import setup_logger

logger = setup_logger("StageManager")


class StageManagerError(Exception):
    """Exception raised for StageManager failures."""
    pass


class StageManager:
    """
    Manages Void Linux stage/base tarballs for rapid ISO and image creation.
    Allows bootstrapping from pre-built tarballs to skip downloading/installing base packages.
    """

    def __init__(self, workdir: Path, mode: str = "mock", arch: str = "x86_64"):
        self.workdir = Path(workdir).resolve()
        self.mode = mode.lower()
        self.arch = arch
        try:
            self.cache_dir = resolve_from_project("cache/tarballs")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Verify writable
            test_file = self.cache_dir / ".write_test"
            test_file.write_text("ok")
            test_file.unlink(missing_ok=True)
        except Exception:
            import tempfile
            self.cache_dir = Path(tempfile.gettempdir()) / "void-builder-cache" / "tarballs"
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def resolve_tarball(self, tarball_arg: str) -> Path:
        """
        Resolves a user-provided tarball argument (file path, URL, or 'y'/'auto').
        Returns the resolved local Path to the tarball.
        """
        tarball_str = str(tarball_arg).strip()

        # 1. Direct file path or file:// URI
        if tarball_str.startswith("file://"):
            local_path = Path(tarball_str.replace("file://", "")).resolve()
            if not local_path.exists():
                raise StageManagerError(f"Local tarball file not found: {local_path}")
            return local_path

        p = Path(tarball_str)
        if p.exists() and p.is_file():
            return p.resolve()

        # 2. Remote HTTP/HTTPS URL
        if tarball_str.startswith(("http://", "https://")):
            from urllib.parse import urlparse
            url_path = urlparse(tarball_str).path
            filename = Path(url_path).name or f"void-base-{self.arch}.tar.xz"
            target_file = self.cache_dir / filename
            if not target_file.exists():
                logger.info(f"Downloading base tarball from {tarball_str}...")
                if self.mode == "mock":
                    logger.info(f"[MOCK STAGE] Downloading tarball from {tarball_str}")
                    target_file.touch()
                else:
                    tmp_file = target_file.with_suffix(".tmp")
                    try:
                        req = urllib.request.Request(tarball_str, headers={"User-Agent": "Void-Builder/1.0"})
                        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_file, "wb") as out:
                            shutil.copyfileobj(resp, out)
                        os.replace(tmp_file, target_file)
                    except Exception as e:
                        if tmp_file.exists():
                            tmp_file.unlink(missing_ok=True)
                        raise StageManagerError(f"Failed to download tarball from {tarball_str}: {e}")
            return target_file

        # 3. Default/Auto lookup for 'y', 'yes', 'true', 'auto'
        if tarball_str.lower() in ("y", "yes", "true", "auto", "default", "1"):
            candidates = [
                self.cache_dir / f"void-base-{self.arch}.tar.xz",
                self.cache_dir / f"void-base-{self.arch}.tar.gz",
                resolve_from_project(f"output/stage_seeds/void-base-{self.arch}.tar.xz"),
                resolve_from_project(f"output/void-base-{self.arch}.tar.xz"),
                resolve_from_project(f"cache/tarballs/void-base-{self.arch}.tar.xz"),
            ]
            for cand in candidates:
                if cand.exists():
                    logger.info(f"Found cached base tarball: {cand}")
                    return cand

            if self.mode == "mock":
                mock_tb = self.cache_dir / f"void-base-{self.arch}.tar.xz"
                mock_tb.touch()
                logger.info(f"[MOCK STAGE MANAGER] Auto-created mock base tarball: {mock_tb}")
                return mock_tb

            raise StageManagerError(
                f"Auto-tarball enabled ('{tarball_arg}'), but no pre-built base seed found in cache.\n"
                f"Searched:\n  - " + "\n  - ".join(str(c) for c in candidates) + "\n"
                f"Build a fresh image or specify an explicit URL/path."
            )

        # 4. Fallback search inside cache directory
        direct_cache = self.cache_dir / tarball_str
        if direct_cache.exists():
            return direct_cache

        raise StageManagerError(f"Cannot resolve base tarball: '{tarball_arg}' does not exist.")

    def extract_tarball(self, tarball_path: Path, target_root: Path) -> None:
        """Extract a base stage tarball into the target root directory with attribute preservation."""
        tarball_path = Path(tarball_path).resolve()
        target_root = Path(target_root).resolve()
        target_root.mkdir(parents=True, exist_ok=True)

        logger.info(f"Extracting base tarball '{tarball_path.name}' -> {target_root}...")

        if self.mode == "mock":
            logger.info(f"[MOCK STAGE MANAGER] Extracted {tarball_path} -> {target_root}")
            (target_root / "bin").mkdir(exist_ok=True)
            (target_root / "etc").mkdir(exist_ok=True)
            return

        if os.geteuid() != 0:
            raise StageManagerError(
                "Extracting base tarballs in real mode requires root privileges (sudo).\n"
                "Please run with sudo: sudo python3 cli.py ..."
            )

        # Detect fastest available parallel decompressor
        decompressor_opt = []
        tb_name = tarball_path.name.lower()
        if tb_name.endswith((".tar.xz", ".txz")):
            if shutil.which("pixz"):
                decompressor_opt = ["--use-compress-program=pixz"]
        elif tb_name.endswith((".tar.zst", ".tzst")):
            if shutil.which("zstd"):
                decompressor_opt = ["--use-compress-program=zstd -T0 -d"]
        elif tb_name.endswith((".tar.gz", ".tgz")):
            if shutil.which("pigz"):
                decompressor_opt = ["--use-compress-program=pigz -d"]

        cmd = ["tar"] + decompressor_opt + ["-xpf", str(tarball_path), "-C", str(target_root), "--numeric-owner", "--xattrs-include=*.*"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Tarball extraction failed: {res.stderr}")
            raise StageManagerError(f"Failed to extract tarball: {res.stderr}")

        logger.info(f"Base tarball successfully extracted to {target_root}.")

    def create_stage_tarball(
        self, source_root: Path, output_tarball: Path, compression: str = "xz"
    ) -> Path:
        """
        Packages a clean rootfs directory into a stage tarball (.tar.xz, .tar.gz, .tar.zst).
        Automatically leverages multi-core parallel compressors (zstd, pixz, pigz) when present.
        """
        source_root = Path(source_root).resolve()
        output_tarball = Path(output_tarball).resolve()
        output_tarball.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating stage tarball '{output_tarball.name}' from {source_root}...")

        if self.mode == "mock":
            logger.info(f"[MOCK STAGE MANAGER] Creating stage tarball {output_tarball}")
            output_tarball.touch()
            return output_tarball

        # Select fastest compressor
        compressor_opt = []
        if compression == "zstd" or output_tarball.name.endswith((".tar.zst", ".zst")):
            if shutil.which("zstd"):
                compressor_opt = ["--use-compress-program=zstd -T0 -3"]
            else:
                compressor_opt = ["--zstd"]
        elif compression == "gzip" or output_tarball.name.endswith((".tar.gz", ".gz")):
            if shutil.which("pigz"):
                compressor_opt = ["--use-compress-program=pigz"]
            else:
                compressor_opt = ["-z"]
        else:
            # xz default
            if shutil.which("pixz"):
                compressor_opt = ["--use-compress-program=pixz"]
            else:
                compressor_opt = ["-J"]

        cmd = ["tar"] + compressor_opt + ["-cpf", str(output_tarball), "-C", str(source_root), "."]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Stage tarball creation failed: {res.stderr}")
            raise StageManagerError(f"Failed to create stage tarball: {res.stderr}")

        logger.info(f"Stage tarball created successfully: {output_tarball}")
        return output_tarball
