#!/usr/bin/env bash
# Build the conda package from the committed HEAD in a clean, throwaway container (handbook Ch15).
# Usage: packaging/conda/build-conda.sh OUTDIR
# Needs the builder image: podman build -t localhost/beamline-conda-builder:0.76.1 packaging/conda
set -euo pipefail

image=localhost/beamline-conda-builder:0.76.1
out=${1:?usage: $0 OUTDIR}

repo=$(git rev-parse --show-toplevel)
cd "$repo"
if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "refusing: tracked files have uncommitted changes; the build uses HEAD only" >&2
  exit 1
fi
if ! podman image exists "$image"; then
  echo "refusing: builder image $image not found" >&2
  exit 1
fi
mkdir -p "$out"
out=$(realpath "$out")
if compgen -G "$out/*.conda" >/dev/null; then
  echo "refusing: $out already contains .conda files" >&2
  exit 1
fi

echo "=== building $(git rev-parse --short HEAD) in $image -> $out"
# git archive sends exactly the committed tree. rattler-build runs as the unprivileged
# 'ubuntu' user (HOME set so its package cache lands in /home/ubuntu), builds from conda-forge
# only, and runs the recipe's tests in a fresh environment; root copies the package to /out.
git archive --format=tar HEAD |
  podman run --rm -i -v "$out:/out" "$image" bash -euo pipefail -c '
    mkdir /build/src
    tar -x -C /build/src
    chown -R ubuntu:ubuntu /build
    runuser -u ubuntu -- env HOME=/home/ubuntu rattler-build build \
      --recipe /build/src/packaging/conda/recipe.yaml \
      --output-dir /build/output \
      --channel conda-forge
    cp /build/output/noarch/*.conda /out/
  '
echo "=== results"
ls -l "$out"
