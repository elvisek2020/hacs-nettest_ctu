"""Tests for the RMBT runner that wraps the `rmbt-client` package."""

import logging
from unittest.mock import MagicMock

import pytest
from rmbt_client import connection, control, pretest
from rmbt_client import tests as rmbt_tests

from custom_components.ctu_nettest.rmbt_runner import (
    RmbtError,
    RmbtOptions,
    control_server_base,
    register_client,
    run_test,
)

CLIENT_UUID = "00000000-0000-4000-8000-000000000001"
CONTROL_URL = "https://nettest.ctu.gov.cz/RMBTControlServer"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "https://nettest.ctu.gov.cz/RMBTControlServer",
            "https://nettest.ctu.gov.cz",
        ),
        (
            "https://nettest.ctu.gov.cz/RMBTControlServer/",
            "https://nettest.ctu.gov.cz",
        ),
        ("https://nettest.ctu.gov.cz", "https://nettest.ctu.gov.cz"),
        ("http://localhost:8080", "http://localhost:8080"),
    ],
)
def test_control_server_base(configured, expected):
    """The library appends the servlet path itself, so it must be stripped."""
    assert control_server_base(configured) == expected


def test_register_client_returns_uuid(monkeypatch):
    monkeypatch.setattr(control, "request_settings", lambda *args: CLIENT_UUID)
    assert register_client(CONTROL_URL) == CLIENT_UUID


def test_register_client_wraps_errors(monkeypatch):
    def boom(*args):
        raise OSError("connection refused")

    monkeypatch.setattr(control, "request_settings", boom)
    with pytest.raises(RmbtError, match="connection refused"):
        register_client(CONTROL_URL)


def test_register_client_rejects_empty_uuid(monkeypatch):
    monkeypatch.setattr(control, "request_settings", lambda *args: "")
    with pytest.raises(RmbtError, match="client UUID"):
        register_client(CONTROL_URL)


def _params(**overrides):
    defaults = {
        "token": "test-token",
        "test_uuid": "00000000-0000-4000-8000-000000000002",
        "open_test_uuid": "O00000000-0000-4000-8000-000000000003",
        "server_addr": "m01v4-nettest.ctu.gov.cz",
        "server_port": 443,
        "encryption": True,
        "duration": 10,
        "num_threads": 3,
        "wait": 0,
        "server_type": "RMBThttp",
    }
    return control.TestParams(**{**defaults, **overrides})


@pytest.fixture
def mock_library(monkeypatch):
    """Replace every network-facing call of the library."""
    monkeypatch.setattr(control, "request_settings", lambda *args: CLIENT_UUID)
    monkeypatch.setattr(control, "request_test", lambda *args: _params())
    monkeypatch.setattr(
        pretest,
        "run_pretest",
        lambda *args: pretest.PretestResult(
            chunk_size=505856, dl_threads=3, ul_threads=3
        ),
    )
    monkeypatch.setattr(
        connection.RmbtConn, "connect", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        rmbt_tests,
        "run_ping",
        lambda *args: [
            rmbt_tests.PingResult(client_ns=ns, server_ns=ns, time_ns=index)
            for index, ns in enumerate((10_000_000, 12_000_000, 14_000_000))
        ],
    )
    monkeypatch.setattr(
        rmbt_tests,
        "run_download",
        lambda conn, duration, chunk_size, index: rmbt_tests.TransferResult(
            bytes=100_000_000, elapsed_ns=10_000_000_000, thread_id=index
        ),
    )
    monkeypatch.setattr(
        rmbt_tests,
        "run_upload",
        lambda conn, duration, chunk_size, index: rmbt_tests.TransferResult(
            bytes=50_000_000, elapsed_ns=10_000_000_000, thread_id=index
        ),
    )


def test_run_test_aggregates_all_threads(mock_library):
    """Throughput is the sum over threads across the longest thread runtime."""
    result = run_test(RmbtOptions(control_server_url=CONTROL_URL))

    assert result.download_mbps == pytest.approx(240.0)
    assert result.upload_mbps == pytest.approx(120.0)
    assert result.download_threads == 3
    assert result.upload_threads == 3
    assert result.bytes_download == 300_000_000
    assert result.bytes_upload == 150_000_000
    assert result.client_uuid == CLIENT_UUID
    assert result.server_address == "m01v4-nettest.ctu.gov.cz"
    assert result.duration_seconds == 10


def test_run_test_derives_ping_and_jitter(mock_library):
    """RMBT reports no jitter, it comes from the spread of the ping samples."""
    result = run_test(RmbtOptions(control_server_url=CONTROL_URL))

    assert result.ping_ms == pytest.approx(10.0)
    assert result.ping_median_ms == pytest.approx(12.0)
    assert result.jitter_ms == pytest.approx(2.0)
    assert result.ping_count == 3


def test_run_test_never_submits_results(mock_library, monkeypatch):
    """Results must not end up in the public ČTÚ open data set."""
    submit = MagicMock()
    monkeypatch.setattr(control, "submit_result", submit)

    run_test(RmbtOptions(control_server_url=CONTROL_URL))

    submit.assert_not_called()


def test_run_test_reuses_stored_uuid(mock_library, monkeypatch):
    """A known UUID is offered so ČTÚ does not register a client per test."""
    seen: list[object] = []

    def request_settings(host, uuid, version, debug):
        seen.append(uuid)
        return CLIENT_UUID

    monkeypatch.setattr(control, "request_settings", request_settings)

    run_test(RmbtOptions(control_server_url=CONTROL_URL, client_uuid=CLIENT_UUID))

    assert seen == [CLIENT_UUID]


def test_run_test_fails_when_all_threads_drop(mock_library, monkeypatch):
    monkeypatch.setattr(
        connection.RmbtConn, "connect", MagicMock(side_effect=OSError("no route"))
    )

    with pytest.raises(RmbtError):
        run_test(RmbtOptions(control_server_url=CONTROL_URL))


def test_run_test_wraps_control_server_errors(mock_library, monkeypatch):
    def boom(*args):
        raise RuntimeError("control server error: ERROR_REQUEST_NEEDED")

    monkeypatch.setattr(control, "request_test", boom)

    with pytest.raises(RmbtError, match="ERROR_REQUEST_NEEDED"):
        run_test(RmbtOptions(control_server_url=CONTROL_URL))


def test_library_progress_goes_to_the_debug_log(mock_library, caplog):
    """The library prints its progress; that must not reach stdout."""
    with caplog.at_level(logging.DEBUG, logger="custom_components.ctu_nettest"):
        run_test(RmbtOptions(control_server_url=CONTROL_URL))
        rmbt_tests.print("dl[ 0]  101.36 Mbit/s")

    assert any("101.36 Mbit/s" in record.message for record in caplog.records)
