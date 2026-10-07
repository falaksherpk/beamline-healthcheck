#!/usr/bin/env bash
# Convert the OCI image built from HEAD into an Apptainer SIF (handbook Ch15).
# Usage: packaging/sif/build-sif.sh OUTDIR
# Needs apptainer and the image built by packaging/oci/build-oci.sh from this exact commit.
set -euo pipefail

registry_image=gitlab.beamline:5050/beamline/beamline-healthcheck
out=${1:?usage: $0 OUTDIR}

repo=$(git rev-parse --show-toplevel)
cd "$repo"
if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "refusing: tracked files have uncommitted changes; the SIF must match HEAD" >&2
  exit 1
fi

revision=$(git rev-parse HEAD)
short=$(git rev-parse --short HEAD)
version=$(git show HEAD:pyproject.toml | python3 -c 'import sys, tomllib; print(tomllib.load(sys.stdin.buffer)["project"]["version"])')
image=$registry_image:$short

# The image must exist under this commit's tag AND carry this commit in its revision label,
# so a stale or re-tagged image can never be converted by mistake.
if ! podman image exists "$image"; then
  echo "refusing: $image not found; build it first with packaging/oci/build-oci.sh" >&2
  exit 1
fi
label=$(podman image inspect --format '{{index .Labels "org.opencontainers.image.revision"}}' "$image")
if [[ $label != "$revision" ]]; then
  echo "refusing: $image has revision label '$label', HEAD is $revision" >&2
  exit 1
fi

mkdir -p "$out"
out=$(realpath "$out")
sif=$out/beamline-healthcheck_$version.sif
if [[ -e $sif ]]; then
  echo "refusing: $sif already exists" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "=== converting $image (revision $short) -> $sif"
podman save --quiet --format oci-archive --output "$tmp/image.tar" "$image"
apptainer build "$sif" "oci-archive:$tmp/image.tar"

echo "=== result"
apptainer inspect --labels "$sif" | grep -E 'org\.opencontainers\.image\.(version|revision)'
sha256sum "$sif"
