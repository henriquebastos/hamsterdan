"""Explicit-only probe used by tests/test_pytest_policy.py."""

import pytest


def test_missing_evidence() -> None:
    pytest.skip("missing")
