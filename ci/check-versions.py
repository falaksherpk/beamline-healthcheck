#!/usr/bin/env python3
"""Refuse a version mismatch before anything is built (handbook Ch17).

The version is written in three files: pyproject.toml, the conda recipe and
debian/changelog. In a tag pipeline the tag (vMAJOR.MINOR.PATCH) must say the
same. Reads files only; never rewrites them - a release bumps all three in one
commit, and this check refuses the tag if one was missed.
"""
import os
import re
import sys
import tomllib
from pathlib import Path

import yaml

root = Path(__file__).resolve().parent.parent
found = {}

with open(root / "pyproject.toml", "rb") as f:
    found["pyproject.toml"] = tomllib.load(f)["project"]["version"]

recipe = yaml.safe_load((root / "packaging/conda/recipe.yaml").read_text())
found["packaging/conda/recipe.yaml"] = str(recipe["context"]["version"])

first = (root / "debian/changelog").read_text().splitlines()[0]
m = re.match(r"^\S+ \(([^)]+)\) ", first)
if not m:
    sys.exit(f"refusing: no version in debian/changelog's first line: {first!r}")
# A native package has no Debian revision; strip one (-N) if it is ever added.
found["debian/changelog"] = re.sub(r"-[^-]+$", "", m.group(1))

tag = os.environ.get("CI_COMMIT_TAG", "")
if tag:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        sys.exit(f"refusing: tag {tag!r} is not vMAJOR.MINOR.PATCH")
    found[f"tag {tag}"] = tag[1:]

for source, version in found.items():
    print(f"{version:<12} {source}")
if len(set(found.values())) != 1:
    sys.exit("refusing: the versions differ")
print(f"versions agree: {found['pyproject.toml']}")
