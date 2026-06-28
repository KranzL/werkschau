from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import werkschau.gh_api
from werkschau.cache import _response_cache_key, _responses_root, set_cached_response


@pytest.fixture(autouse=True)
def reset_cache_enabled():
    werkschau.gh_api._CACHE_ENABLED = True
    yield
    werkschau.gh_api._CACHE_ENABLED = True


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WERKSCHAU_CACHE_DIR", str(tmp_path))
    yield


def _mock_run(data):
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.stdout = json.dumps(data)
    mock.returncode = 0
    return mock


def test_get_cache_miss_then_hit(tmp_path):
    data = {"id": 1, "name": "test"}
    with patch("werkschau.gh_api.subprocess.run", return_value=_mock_run(data)) as mock_run:
        result1 = werkschau.gh_api.gh_api("/repos/foo/bar")
        result2 = werkschau.gh_api.gh_api("/repos/foo/bar")
    assert result1 == data
    assert result2 == data
    assert mock_run.call_count == 1


def test_get_cache_hit_no_subprocess(tmp_path):
    data = {"login": "alice"}
    key = _response_cache_key("GET", "/users/alice", False, None)
    set_cached_response(key, _responses_root(), data)
    with patch("werkschau.gh_api.subprocess.run") as mock_run:
        result = werkschau.gh_api.gh_api("/users/alice")
    assert result == data
    mock_run.assert_not_called()


def test_post_always_calls_subprocess_and_doesnt_cache(tmp_path):
    data = {"merged": True}
    with patch("werkschau.gh_api.subprocess.run", return_value=_mock_run(data)) as mock_run:
        result = werkschau.gh_api.gh_api("/repos/foo/bar/merges", method="POST")
    assert result == data
    assert mock_run.call_count == 1
    resp_dir = tmp_path / "responses"
    assert not resp_dir.exists() or list(resp_dir.glob("*.json")) == []


def test_disable_cache_bypasses_cache_hit(tmp_path):
    data = {"login": "alice"}
    key = _response_cache_key("GET", "/users/alice", False, None)
    set_cached_response(key, _responses_root(), data)
    werkschau.gh_api.disable_cache()
    fresh_data = {"login": "alice_fresh"}
    with patch("werkschau.gh_api.subprocess.run", return_value=_mock_run(fresh_data)) as mock_run:
        werkschau.gh_api.gh_api("/users/alice")
    assert mock_run.call_count == 1


def test_no_cache_bypasses_read_and_write(tmp_path):
    werkschau.gh_api.disable_cache()
    data = {"id": 42}
    with patch("werkschau.gh_api.subprocess.run", return_value=_mock_run(data)) as mock_run:
        result = werkschau.gh_api.gh_api("/repos/acme/widget")
    assert result == data
    assert mock_run.call_count == 1
    resp_dir = tmp_path / "responses"
    assert not resp_dir.exists() or list(resp_dir.glob("*.json")) == []


def test_stale_cache_entry_is_treated_as_miss(tmp_path):
    key = _response_cache_key("GET", "/users/bob", False, None)
    resp_dir = _responses_root()
    resp_dir.mkdir(parents=True, exist_ok=True)
    stale_envelope = {"stored_at": time.time() - 999999, "data": {"login": "bob_old"}}
    (resp_dir / f"{key}.json").write_text(json.dumps(stale_envelope))
    fresh_data = {"login": "bob_fresh"}
    with patch("werkschau.gh_api.subprocess.run", return_value=_mock_run(fresh_data)) as mock_run:
        result = werkschau.gh_api.gh_api("/users/bob")
    assert result == fresh_data
    assert mock_run.call_count == 1
    fresh_file = resp_dir / f"{key}.json"
    assert fresh_file.exists()
    new_envelope = json.loads(fresh_file.read_text())
    assert new_envelope["data"] == fresh_data


def test_empty_list_not_written_to_cache(tmp_path):
    empty_mock = MagicMock(spec=subprocess.CompletedProcess)
    empty_mock.stdout = "[]"
    empty_mock.returncode = 0
    with patch("werkschau.gh_api.subprocess.run", return_value=empty_mock):
        result = werkschau.gh_api.gh_api("/users/alice/events", paginate=True)
    assert result == []
    resp_dir = tmp_path / "responses"
    assert not resp_dir.exists() or list(resp_dir.glob("*.json")) == []


def test_none_result_not_written_to_cache(tmp_path):
    none_mock = MagicMock(spec=subprocess.CompletedProcess)
    none_mock.stdout = ""
    none_mock.returncode = 0
    with patch("werkschau.gh_api.subprocess.run", return_value=none_mock):
        result = werkschau.gh_api.gh_api("/nonexistent")
    assert result is None
    resp_dir = tmp_path / "responses"
    assert not resp_dir.exists() or list(resp_dir.glob("*.json")) == []
