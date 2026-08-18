"""Blocking RMBT measurement runner built on top of the `rmbt-client` package.

This module deliberately imports nothing from Home Assistant so that the
measurement can be exercised standalone and later replaced by a native asyncio
RMBT implementation without touching the coordinator or the entities.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from rmbt_client import connection, control, pretest, tests

_LOGGER = logging.getLogger(__name__)

CLIENT_VERSION = "1.0.0"

# The control server hands out its own thread count; this is only an upper bound.
MAX_THREADS = 20

PING_DURATION_SECONDS = 1.0
PING_MIN_COUNT = 10
PING_MAX_COUNT = 100

# Threads rendezvous before transferring so all of them load the link at once.
_BARRIER_TIMEOUT_SECONDS = 60

_MIN_JITTER_SAMPLES = 2

_CONTROL_PATH = "/RMBTControlServer"

_PHASE_DOWNLOAD = "download"
_PHASE_UPLOAD = "upload"


class RmbtError(Exception):
    """Raised when a measurement could not be completed."""


@dataclass(frozen=True, slots=True)
class RmbtOptions:
    """Input parameters for a single measurement."""

    control_server_url: str
    client_uuid: str | None = None
    use_websocket: bool = False


@dataclass(frozen=True, slots=True)
class RmbtResult:
    """Aggregated outcome of a single measurement."""

    timestamp: datetime
    client_uuid: str
    download_mbps: float
    upload_mbps: float
    ping_ms: float
    ping_median_ms: float
    jitter_ms: float | None
    server_address: str
    download_threads: int
    upload_threads: int
    bytes_download: int
    bytes_upload: int
    duration_seconds: int
    ping_count: int


@dataclass(frozen=True, slots=True)
class _Phase:
    """Everything a transfer phase needs to open its own connections."""

    name: str
    params: Any
    protocol: int
    threads: int
    duration: int
    chunk_size: int


def control_server_base(url: str) -> str:
    """Return the base URL that `rmbt_client` expects.

    The library appends `/RMBTControlServer/<endpoint>` itself, so the servlet
    path has to be stripped from the configured URL.
    """
    parts = urlsplit(url.strip().rstrip("/"))
    path = parts.path
    if path.rstrip("/").endswith(_CONTROL_PATH):
        path = path.rstrip("/")[: -len(_CONTROL_PATH)]
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


_output_redirected = False


def _redirect_library_output() -> None:
    """Route the library's progress reporting into the debug log.

    `rmbt_client` reports every phase with `print()`. Rebinding the module-level
    name keeps that off Home Assistant's stdout without touching `sys.stdout`,
    which would not be thread-safe.
    """
    global _output_redirected  # noqa: PLW0603
    if _output_redirected:
        return

    def progress(*args: Any, **_kwargs: Any) -> None:
        message = " ".join(str(arg) for arg in args).strip()
        if message:
            _LOGGER.debug("rmbt: %s", message)

    for module in (control, pretest, tests):
        module.print = progress
    _output_redirected = True


def register_client(control_server_url: str, client_uuid: str | None = None) -> str:
    """Register with the control server and return the client UUID.

    Blocking. Doubles as a connectivity check for the config flow. Passing a
    known UUID keeps the control server from creating a new client record.
    """
    _redirect_library_output()
    host = control_server_base(control_server_url)

    try:
        registered = control.request_settings(host, client_uuid, CLIENT_VERSION, False)
    except RmbtError:
        raise
    except Exception as err:
        _LOGGER.debug("Control server registration failed", exc_info=True)
        raise RmbtError(str(err) or type(err).__name__) from err

    if not registered:
        raise RmbtError("Control server did not return a client UUID")
    return registered


def run_test(options: RmbtOptions) -> RmbtResult:
    """Run a full RMBT measurement. Blocking, must not run in the event loop."""
    try:
        return _run_test(options)
    except RmbtError:
        raise
    except Exception as err:
        _LOGGER.debug("RMBT measurement failed", exc_info=True)
        raise RmbtError(str(err) or type(err).__name__) from err


def _run_test(options: RmbtOptions) -> RmbtResult:
    _redirect_library_output()

    host = control_server_base(options.control_server_url)
    client_uuid = register_client(options.control_server_url, options.client_uuid)

    params = control.request_test(
        host, client_uuid, CLIENT_VERSION, options.use_websocket, False
    )

    if options.use_websocket or params.server_type == "RMBTws":
        protocol = connection.PROTO_WS
    else:
        protocol = connection.PROTO_HTTP

    server_cap = max(1, min(params.num_threads, MAX_THREADS))

    _LOGGER.debug(
        "RMBT test server %s:%s (%s), duration %ss, up to %s threads",
        params.server_addr,
        params.server_port,
        "RMBTws" if protocol == connection.PROTO_WS else "RMBThttp",
        params.duration,
        server_cap,
    )

    if params.wait > 0:
        _LOGGER.debug("Control server queued the test, waiting %ss", params.wait)
        time.sleep(params.wait)

    pretest_result = pretest.run_pretest(
        params.server_addr,
        params.server_port,
        params.encryption,
        False,
        protocol,
        params.token,
        server_cap,
    )
    download_chunk = pretest_result.chunk_size

    started = datetime.now(UTC)
    pings = _run_ping(params, protocol)

    download = _run_transfer_phase(
        _Phase(
            name=_PHASE_DOWNLOAD,
            params=params,
            protocol=protocol,
            threads=max(1, min(pretest_result.dl_threads, server_cap)),
            duration=params.duration,
            chunk_size=download_chunk,
        )
    )
    if not download:
        raise RmbtError("All download threads failed")

    upload = _run_transfer_phase(
        _Phase(
            name=_PHASE_UPLOAD,
            params=params,
            protocol=protocol,
            threads=max(1, min(pretest_result.ul_threads, server_cap)),
            duration=params.duration,
            chunk_size=min(download_chunk, tests.MAX_UL_CHUNK),
        )
    )
    if not upload:
        raise RmbtError("All upload threads failed")

    download_bytes = sum(result.bytes for result in download)
    download_ns = max(result.elapsed_ns for result in download)
    upload_bytes = sum(result.bytes for result in upload)
    upload_ns = max(result.elapsed_ns for result in upload)

    return RmbtResult(
        timestamp=started,
        client_uuid=client_uuid,
        download_mbps=_throughput_mbps(download_bytes, download_ns),
        upload_mbps=_throughput_mbps(upload_bytes, upload_ns),
        ping_ms=_shortest_ping_ms(pings),
        ping_median_ms=_median_ping_ms(pings),
        jitter_ms=_jitter_ms(pings),
        server_address=params.server_addr,
        download_threads=len(download),
        upload_threads=len(upload),
        bytes_download=download_bytes,
        bytes_upload=upload_bytes,
        duration_seconds=params.duration,
        ping_count=len(pings),
    )


def _connect(params: Any, protocol: int) -> Any:
    conn = connection.RmbtConn.connect(
        params.server_addr, params.server_port, params.encryption, False, protocol
    )
    conn.greeting(params.token)
    return conn


def _run_ping(params: Any, protocol: int) -> list[Any]:
    conn = _connect(params, protocol)
    try:
        pings = tests.run_ping(
            conn, PING_DURATION_SECONDS, PING_MIN_COUNT, PING_MAX_COUNT
        )
        conn.quit()
    finally:
        conn.close()
    return pings


def _run_transfer_phase(phase: _Phase) -> list[Any]:
    barrier = threading.Barrier(phase.threads)
    results: list[Any] = [None] * phase.threads

    def worker(index: int) -> None:
        try:
            conn = _connect(phase.params, phase.protocol)
        except Exception:
            _LOGGER.debug("RMBT %s thread %s could not connect", phase.name, index)
            _wait(barrier)
            return

        try:
            if not _wait(barrier):
                return
            if phase.name == _PHASE_DOWNLOAD:
                results[index] = tests.run_download(
                    conn, phase.duration, phase.chunk_size, index
                )
            else:
                results[index] = tests.run_upload(
                    conn, phase.duration, phase.chunk_size, index
                )
            conn.quit()
        except Exception:
            _LOGGER.debug("RMBT %s thread %s dropped", phase.name, index, exc_info=True)
        finally:
            conn.close()

    workers = [
        threading.Thread(
            target=worker,
            args=(index,),
            name=f"rmbt-{phase.name}-{index}",
            daemon=True,
        )
        for index in range(phase.threads)
    ]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()

    return [result for result in results if result is not None]


def _wait(barrier: threading.Barrier) -> bool:
    """Wait for the other threads, tolerating a partially failed phase."""
    try:
        barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
    except threading.BrokenBarrierError:
        return False
    return True


def _throughput_mbps(transferred_bytes: int, elapsed_ns: int) -> float:
    if elapsed_ns <= 0:
        raise RmbtError("Test server reported a zero-length transfer")
    return round(transferred_bytes * 8.0 / (elapsed_ns / 1e9) / 1e6, 2)


def _shortest_ping_ms(pings: list[Any]) -> float:
    if not pings:
        raise RmbtError("Ping phase returned no samples")
    return round(min(ping.client_ns for ping in pings) / 1e6, 2)


def _median_ping_ms(pings: list[Any]) -> float:
    if not pings:
        raise RmbtError("Ping phase returned no samples")
    return round(statistics.median(ping.client_ns for ping in pings) / 1e6, 2)


def _jitter_ms(pings: list[Any]) -> float | None:
    """RMBT reports no jitter, so derive it from the spread of the ping samples."""
    if len(pings) < _MIN_JITTER_SAMPLES:
        return None
    return round(statistics.stdev(ping.client_ns for ping in pings) / 1e6, 2)
