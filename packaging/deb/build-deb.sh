#!/usr/bin/env bash
# Build the .deb from the committed HEAD in a clean, throwaway container (handbook Ch15).
# Usage: packaging/deb/build-deb.sh OUTDIR
# Needs the builder image: podman build -t localhost/beamline-deb-builder:noble packaging/deb
set -euo pipefail

image=localhost/beamline-deb-builder:noble
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
if compgen -G "$out/*.deb" >/dev/null; then
  echo "refusing: $out already contains .deb files" >&2
  exit 1
fi

echo "=== building $(git rev-parse --short HEAD) in $image -> $out"
# git archive sends exactly the committed tree (no untracked files, no build leftovers).
# Inside: root installs the Build-Depends, the unprivileged 'ubuntu' user builds and runs
# lintian (Rules-Requires-Root: no), root copies the results to the bind-mounted /out.
git archive --format=tar HEAD |
  podman run --rm -i -v "$out:/out" "$image" bash -euo pipefail -c '
    mkdir /build/src
    tar -x -C /build/src
    chown -R ubuntu:ubuntu /build
    apt-get update -qq
    apt-get build-dep -y -qq --no-install-recommends /build/src
    cd /build/src
    runuser -u ubuntu -- dpkg-buildpackage -b -us -uc
    cd /build
    runuser -u ubuntu -- lintian --fail-on error --info ./*.changes
    cp ./*.deb ./*.buildinfo ./*.changes /out/
  '
echo "=== results"
ls -l "$out"
