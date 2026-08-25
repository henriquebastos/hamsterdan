"""Repository-wide pytest policy shared by serial and xdist runs."""

from __future__ import annotations

import pytest

_SKIPPED_NODE_IDS: set[str] = set()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--forbid-skips",
        action="store_true",
        help="Fail the session if any selected test skips instead of passing or failing.",
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped:
        _SKIPPED_NODE_IDS.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    if session.config.getoption("--forbid-skips") and _SKIPPED_NODE_IDS and exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if terminalreporter.config.getoption("--forbid-skips") and _SKIPPED_NODE_IDS:
        terminalreporter.write_sep("=", f"forbidden skips: {len(_SKIPPED_NODE_IDS)}")
        for node_id in sorted(_SKIPPED_NODE_IDS):
            terminalreporter.write_line(node_id)
