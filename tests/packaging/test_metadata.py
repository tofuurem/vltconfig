"""Source-tree packaging metadata checks."""

from importlib import metadata, resources

from vltconfig import VaultJsonConfig


def test_distribution_metadata_matches_public_package() -> None:
    """The installed project metadata should describe the importable package."""
    distribution = metadata.distribution("vltconfig")

    assert distribution.metadata["Name"] == "vltconfig"
    assert distribution.metadata["Requires-Python"] == ">=3.11"
    assert issubclass(VaultJsonConfig, object)


def test_typing_marker_is_packaged() -> None:
    """PEP 561 consumers should be able to discover the inline typing marker."""
    marker = resources.files("vltconfig").joinpath("py.typed")

    assert marker.is_file()
