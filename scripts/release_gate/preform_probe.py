from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def read_json_url(url: str, *, timeout_seconds: float = 10.0) -> Any:
    with urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_preform(preform_url: str) -> dict[str, Any]:
    base = preform_url.rstrip("/")
    probes: dict[str, Any] = {"base_url": base, "reachable": False}
    try:
        probes["devices"] = read_json_url(f"{base}/devices/")
        probes["reachable"] = True
    except (OSError, URLError, json.JSONDecodeError) as exc:
        probes["error"] = str(exc)
    return probes


def is_virtual_device(device: dict[str, Any]) -> bool:
    if bool(device.get("is_virtual")):
        return True
    haystack = " ".join(
        str(device.get(key, ""))
        for key in ("id", "device_id", "name", "device_name", "model", "status")
    ).lower()
    return "virtual" in haystack or "debug" in haystack
