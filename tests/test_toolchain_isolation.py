from pathlib import Path
from types import SimpleNamespace

import pytest

from void_builder.core.toolchain import ToolchainManager
from void_builder.core.stage_manager import StageManager


def test_toolchain_tools_are_per_build_and_cache_is_persistent(tmp_path):
    tc = ToolchainManager(tmp_path / "build", mode="mock")
    assert tc.tools_dir == (tmp_path / "build" / "build_host" / "tools").resolve()
    assert not str(tc.tools_dir).startswith(str(Path.cwd() / "void_builder" / "tools"))
    stage = StageManager(tmp_path / "build", mode="mock")
    assert stage.cache_dir.name == "tarballs"
    assert not stage.cache_dir.is_relative_to(tmp_path / "build")


def test_real_build_host_refuses_ambient_host_tools(tmp_path):
    tc = ToolchainManager(tmp_path / "build", mode="real")
    tc.host_dir = tmp_path / "build" / "build_host" / "void-host"
    tc.host_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="missing from isolated host"):
        tc.run_in_build_host(["qemu-img", "--version"])
    with pytest.raises(RuntimeError, match="outside the isolated build directories"):
        tc.run_in_build_host(["/usr/bin/qemu-img", "--version"])


def test_execute_command_requires_chroot_in_real_mode(tmp_path):
    tc = ToolchainManager(tmp_path / "build", mode="real")
    with pytest.raises(RuntimeError, match="inside the build chroot"):
        tc.execute_command(["echo", "host"])
