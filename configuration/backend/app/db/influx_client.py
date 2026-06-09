"""Shared InfluxDB client lifecycle for the Flask backend.

InfluxDBClient manages an HTTP connection pool internally. Creating and closing a
client for every query prevents connection reuse and adds avoidable overhead.
This module therefore keeps one lazily-created client per Python process (for
example per gunicorn worker) and closes it when the process exits.
"""

import atexit
import threading

from influxdb_client import InfluxDBClient

from ..config import Config

_client = None
_client_lock = threading.Lock()


def _create_influxdb_client():
    return InfluxDBClient(
        url=Config.INFLUX_URL,
        token=Config.INFLUX_TOKEN,
        org=Config.INFLUX_ORG,
        timeout=Config.INFLUX_TIMEOUT_MS,
    )


def get_influxdb_client():
    """Return the shared InfluxDB client for the current backend process."""
    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _create_influxdb_client()

    return _client


def close_influxdb_client():
    """Close the shared InfluxDB client, if it has been created."""
    global _client

    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


atexit.register(close_influxdb_client)
