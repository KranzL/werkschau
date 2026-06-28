from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from typing import Any


class GhError(RuntimeError):
    pass


_MAX_RETRIES = 8
_MAX_TOTAL_WAIT_SECONDS = 7200

_log = logging.getLogger("werkschau.gh_api")


def gh_api(
    path: str,
    *,
    paginate: bool = False,
    fields: dict[str, str] | None = None,
    method: str = "GET",
) -> Any:
    cmd = ["gh", "api", "-X", method]
    if paginate:
        cmd.append("--paginate")
    for key, value in (fields or {}).items():
        cmd.extend(["-f", f"{key}={value}"])
    cmd.append(path)

    total_wait = 0
    for attempt in range(_MAX_RETRIES):
        t0 = time.perf_counter()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise GhError(
                "gh CLI not found on PATH. Install from https://cli.github.com and run `gh auth login`."
            ) from exc
        except subprocess.CalledProcessError as exc:
            _log.debug("gh_api path=%s status=failed exit=%d duration=%.3fs", path, exc.returncode, time.perf_counter() - t0)
            combined = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip()
            lower = combined.lower()
            sleep_for = _retry_delay(path, combined, lower, attempt)
            if sleep_for is None:
                raise GhError(
                    f"gh api {path} failed (exit {exc.returncode}): {combined[:500]}"
                ) from exc
            if total_wait + sleep_for > _MAX_TOTAL_WAIT_SECONDS:
                raise GhError(
                    f"gh api {path}: aborting after {total_wait}s of rate-limit waits"
                ) from exc
            print(
                f"[rate-limit] {path}: sleeping {sleep_for}s (attempt {attempt + 1}/{_MAX_RETRIES})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(sleep_for)
            total_wait += sleep_for
            continue
        _log.debug("gh_api path=%s status=ok duration=%.3fs", path, time.perf_counter() - t0)
        return _parse_output(result.stdout, paginate)

    raise GhError(f"gh api {path}: exceeded {_MAX_RETRIES} retries")


def _retry_delay(path: str, stderr_combined: str, stderr_lower: str, attempt: int) -> int | None:
    if "secondary rate limit" in stderr_lower or "abuse detection" in stderr_lower:
        return min(60 * (2 ** attempt), 600)
    if "rate limit exceeded" in stderr_lower or ("403" in stderr_combined and "rate" in stderr_lower):
        return max(_seconds_until_rate_reset(path), 5) + 5
    if "could not resolve host" in stderr_lower or "connection reset" in stderr_lower or "timeout" in stderr_lower:
        return min(5 * (2 ** attempt), 120)
    return None


def _parse_output(text: str, paginate: bool) -> Any:
    text = text.strip()
    if not text:
        return [] if paginate else None
    if not paginate:
        return json.loads(text)
    decoder = json.JSONDecoder()
    out: list[Any] = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, list):
            out.extend(obj)
        else:
            out.append(obj)
        idx = end
    return out


def rate_limit_status() -> dict[str, dict[str, int]]:
    try:
        result = subprocess.run(
            ["gh", "api", "/rate_limit"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return data.get("resources") or {}


def _seconds_until_rate_reset(path: str) -> int:
    category = "search" if "/search" in path else "graphql" if "/graphql" in path else "core"
    resources = rate_limit_status()
    reset_ts = (resources.get(category) or {}).get("reset")
    if not reset_ts:
        return 60
    return max(0, int(reset_ts) - int(time.time()))
