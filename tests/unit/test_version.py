import tomllib
from pathlib import Path

import sqlide


def test_package_version_matches_pyproject():
    data = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert sqlide.__version__ == data["project"]["version"]
