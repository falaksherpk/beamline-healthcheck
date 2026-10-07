# beamline-healthcheck

Host health check for the beamline lab fleet: disk, memory (`MemAvailable`), load per CPU and
optional TCP targets. Exit 0 if every check passes, 1 if any fails, 2 on usage errors.
`--prometheus FILE` also writes metrics for node_exporter's textfile collector (atomic replace).

    beamline-healthcheck --tcp gitlab.beamline:443 --prometheus /var/lib/node_exporter/textfile/healthcheck.prom

Built and distributed as wheel, .deb, conda package, Apptainer image and OCI image
(handbook Part 2, Chapter 15). Python >= 3.12, standard library only.

## Running in containers

In the OCI image and the Apptainer SIF, `/` is the container's own filesystem, so the
default disk check says nothing about the host. Point it at host paths that are mounted
into the container instead:

    podman run --rm -v /srv:/srv:ro gitlab.beamline:5050/beamline/beamline-healthcheck:1.0.0 --disk-path /srv
    apptainer run --bind /scratch beamline-healthcheck_1.0.0.sif --disk-path /scratch --disk-path "$HOME"

The OCI image runs as UID 10001; Apptainer runs it as the invoking user.
