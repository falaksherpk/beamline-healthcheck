"""beamline-healthcheck: host health check with Prometheus textfile output."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("beamline-healthcheck")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0+unknown"
