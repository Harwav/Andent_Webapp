"""Windows desktop tray launcher for FormFlow."""
from __future__ import annotations

import ipaddress
import socket


def _initial_url(port: int, *, first_run: bool) -> str:
    if first_run:
        return f"http://localhost:{port}/setup"
    return f"http://localhost:{port}/"


def _select_lan_ip(candidates: list[str]) -> str:
    rfc1918 = (
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
    )
    for addr in candidates:
        try:
            ip = ipaddress.IPv4Address(addr)
            if any(ip in net for net in rfc1918):
                return addr
        except ValueError:
            continue
    return candidates[0] if candidates else "127.0.0.1"
