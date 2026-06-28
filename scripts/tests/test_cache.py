from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from werkschau.cache import (
    _cache_root,
    _default_ttl,
    _response_cache_key,
    _responses_root,
    get_cached_commit,
    get_cached_response,
    set_cached_commit,
    set_cached_response,
)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("WERKSCHAU_CACHE_DIR", str(tmp_path))
    yield


def test_cache_miss_returns_none(tmp_path):
    root = tmp_path / "responses"
    result = get_cached_response("nonexistent_key", root)
    assert result is None


def test_set_then_get_fresh_ttl_returns_data(tmp_path):
    root = tmp_path / "responses"
    data = {"foo": "bar", "nums": [1, 2, 3]}
    set_cached_response("mykey", root, data)
    result = get_cached_response("mykey", root, ttl=3600)
    assert result == data


def test_stale_entry_returns_none_and_deletes_file(tmp_path):
    root = tmp_path / "responses"
    data = {"x": 1}
    set_cached_response("stalekey", root, data)
    file_path = root / "stalekey.json"
    assert file_path.exists()
    envelope = json.loads(file_path.read_text())
    envelope["stored_at"] = time.time() - 7200
    file_path.write_text(json.dumps(envelope))
    result = get_cached_response("stalekey", root, ttl=3600)
    assert result is None
    assert not file_path.exists()


def test_infinite_ttl_returns_data_regardless_of_age(tmp_path):
    root = tmp_path / "responses"
    data = {"old": True}
    set_cached_response("infinitekey", root, data)
    file_path = root / "infinitekey.json"
    envelope = json.loads(file_path.read_text())
    envelope["stored_at"] = time.time() - 999999
    file_path.write_text(json.dumps(envelope))
    result = get_cached_response("infinitekey", root, ttl=-1)
    assert result == data


def test_paginate_flag_produces_distinct_keys():
    key_false = _response_cache_key("GET", "/users/alice", False, None)
    key_true = _response_cache_key("GET", "/users/alice", True, None)
    assert key_false != key_true
    assert len(key_false) == 64
    assert len(key_true) == 64


def test_fields_dict_produces_distinct_keys():
    key_a = _response_cache_key("GET", "/users/alice", False, {"a": "1"})
    key_b = _response_cache_key("GET", "/users/alice", False, {"b": "2"})
    assert key_a != key_b


def test_get_set_cached_commit_roundtrip(tmp_path):
    data = {"sha": "abc123", "files": []}
    set_cached_commit("myorg", "myrepo", "abc123", data)
    result = get_cached_commit("myorg", "myrepo", "abc123")
    assert result == data
    cache_dir = _cache_root()
    expected_file = cache_dir / "myorg--myrepo--abc123.json"
    assert expected_file.exists()
    resp_dir = _responses_root()
    if resp_dir.exists():
        for f in resp_dir.glob("*.json"):
            assert "abc123" not in f.name


def test_backward_compat_raw_json(tmp_path):
    raw_data = {"sha": "deadbeef", "tree": {"sha": "abc"}}
    cache_dir = _cache_root()
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_file = cache_dir / "myorg--myrepo--deadbeef.json"
    raw_file.write_text(json.dumps(raw_data))
    result = get_cached_commit("myorg", "myrepo", "deadbeef")
    assert result == raw_data


def test_cache_dir_override_redirects_both_roots(tmp_path, monkeypatch):
    custom = tmp_path / "custom_cache"
    monkeypatch.setenv("WERKSCHAU_CACHE_DIR", str(custom))
    cache_dir = _cache_root()
    resp_dir = _responses_root()
    assert cache_dir == custom
    assert resp_dir == custom / "responses"


def test_default_ttl_without_env_var(monkeypatch):
    monkeypatch.delenv("WERKSCHAU_CACHE_TTL", raising=False)
    assert _default_ttl() == 86400


def test_default_ttl_with_env_var(monkeypatch):
    monkeypatch.setenv("WERKSCHAU_CACHE_TTL", "300")
    assert _default_ttl() == 300


def test_set_cached_response_file_mode(tmp_path):
    root = tmp_path / "responses"
    set_cached_response("permkey", root, {"secret": True})
    file_path = root / "permkey.json"
    assert file_path.exists()
    assert stat.S_IMODE(os.stat(file_path).st_mode) == 0o600


def test_set_cached_response_dir_mode_new(tmp_path):
    root = tmp_path / "newdir"
    set_cached_response("dirkey", root, {"x": 1})
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700


def test_set_cached_response_dir_mode_preexisting(tmp_path):
    root = tmp_path / "preexisting"
    root.mkdir(mode=0o755)
    set_cached_response("dirkey2", root, {"x": 2})
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
