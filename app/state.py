"""Runtime state shared across app modules."""

import socket

LAN_IP: str = "127.0.0.1"
WIZARD_COMPLETED: bool = False
LAN_BIND_ALLOWED: bool = True


def _discover_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def init() -> None:
    global LAN_IP
    LAN_IP = _discover_lan_ip()
