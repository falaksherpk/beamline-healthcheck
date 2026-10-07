# beamline-healthcheck

Host health check for the beamline lab fleet: disk, memory (`MemAvailable`), load per CPU and
optional TCP targets. Exit 0 if every check passes, 1 if any fails, 2 on usage errors.
`--prometheus FILE` also writes metrics for node_exporter's textfile collector (atomic replace).

    beamline-healthcheck --tcp gitlab.beamline:443 --prometheus /var/lib/node_exporter/textfile/healthcheck.prom

Built and distributed as wheel, .deb, conda package, Apptainer image and OCI image
(handbook Part 2, Chapter 15). Python >= 3.12, standard library only.
