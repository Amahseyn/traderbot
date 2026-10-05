import pytest

from lab.job_resolvers import JobPayloadError, parse_run_bound_utc


def test_parse_run_bound_utc_accepts_z_suffix():
    assert parse_run_bound_utc("2024-06-01T12:00:00Z") == 1717243200


def test_parse_run_bound_utc_rejects_garbage():
    with pytest.raises(JobPayloadError):
        parse_run_bound_utc("not-a-date")
