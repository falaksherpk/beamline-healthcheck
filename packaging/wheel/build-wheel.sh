#!/usr/bin/env bash
# Build the sdist and wheel from the committed HEAD (handbook Ch15).
# Usage: packaging/wheel/build-wheel.sh OUTDIR
# Needs python3-build and python3-venv (pkg role, tag pkg_build); the isolated build
# environment fetches setuptools from PyPI.
set -euo pipefail

out=${1:?usage: $0 OUTDIR}

repo=$(git rev-parse --show-toplevel)
cd "$repo"
if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "refusing: tracked files have uncommitted changes; the build uses HEAD only" >&2
  exit 1
fi
mkdir -p "$out"
out=$(realpath "$out")
if compgen -G "$out/*.whl" >/dev/null || compgen -G "$out/*.tar.gz" >/dev/null; then
  echo "refusing: $out already contains a wheel or sdist" >&2
  exit 1
fi

# Build from exactly the committed tree, extracted into a throwaway directory.
src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
git archive --format=tar HEAD | tar -x -C "$src"

# Archive timestamps from the commit: the wheel is then byte-reproducible (the sdist is not;
# setuptools' sdist ignores SOURCE_DATE_EPOCH for its generated files and gzip header).
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct HEAD)
export SOURCE_DATE_EPOCH

echo "=== building $(git rev-parse --short HEAD) -> $out"
python3 -m build --outdir "$out" "$src"

echo "=== result"
sha256sum "$out"/*.whl "$out"/*.tar.gz
