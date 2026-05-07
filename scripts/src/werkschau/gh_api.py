from __future__ import annotations

import json
import subprocess
from typing import Any


class GhError(RuntimeError):
    pass


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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise GhError(
            "gh CLI not found on PATH. Install from https://cli.github.com and run `gh auth login`."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise GhError(
            f"gh api {path} failed (exit {exc.returncode}): {exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    text = result.stdout.strip()
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
