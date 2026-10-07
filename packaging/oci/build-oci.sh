#!/usr/bin/env bash
# Build the OCI image from the committed HEAD (handbook Ch15). Does not push.
# Usage: packaging/oci/build-oci.sh
# Tags:  gitlab.beamline:5050/beamline/beamline-healthcheck:<version> and :<short commit>
set -euo pipefail

registry_image=gitlab.beamline:5050/beamline/beamline-healthcheck

repo=$(git rev-parse --show-toplevel)
cd "$repo"
if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "refusing: tracked files have uncommitted changes; the build uses HEAD only" >&2
  exit 1
fi

version=$(git show HEAD:pyproject.toml | python3 -c 'import sys, tomllib; print(tomllib.load(sys.stdin.buffer)["project"]["version"])')
revision=$(git rev-parse HEAD)
short=$(git rev-parse --short HEAD)
epoch=$(git log -1 --format=%ct HEAD)

# The build context is exactly the committed tree, extracted into a throwaway directory.
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
git archive --format=tar HEAD | tar -x -C "$context"

echo "=== building $short (version $version) -> $registry_image:{$version,$short}"
# --timestamp pins the image's created time and the layer file times to the commit time.
podman build \
  --file "$context/packaging/oci/Containerfile" \
  --build-arg VERSION="$version" \
  --build-arg REVISION="$revision" \
  --timestamp "$epoch" \
  --tag "$registry_image:$version" \
  --tag "$registry_image:$short" \
  "$context"

echo "=== result"
podman image inspect --format '{{.Id}}  {{.Size}} bytes  created {{.Created}}' "$registry_image:$version"
