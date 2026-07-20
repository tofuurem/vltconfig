"""Source-tree packaging metadata checks."""

import tomllib
from importlib import metadata, resources
from pathlib import Path

from vltconfig import VaultJsonConfig


def test_distribution_metadata_matches_public_package() -> None:
    """The installed project metadata should describe the importable package."""
    distribution = metadata.distribution("vltconfig")
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]

    assert distribution.metadata["Name"] == "vltconfig"
    assert distribution.version == project["version"]
    assert distribution.metadata["Requires-Python"] == ">=3.11"
    assert issubclass(VaultJsonConfig, object)


def test_typing_marker_is_packaged() -> None:
    """PEP 561 consumers should be able to discover the inline typing marker."""
    marker = resources.files("vltconfig").joinpath("py.typed")

    assert marker.is_file()


def test_console_entry_point_is_installed() -> None:
    """The distribution exposes the documented command-line entry point."""
    distribution = metadata.distribution("vltconfig")
    scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }

    assert scripts["vltconfig"] == "vltconfig.cli:main"
