"""Formlabs Dashboard Web API client.

Connects to api.formlabs.com via OAuth to poll printer fleet status,
print history, resin cartridges, and tanks. Runs as a background task
that caches data in memory for the REST API to serve.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp
import certifi

logger = logging.getLogger("formlabsAFA.dashboard")

BASE_URL = "https://api.formlabs.com"


@dataclass
class PrinterStatus:
    serial: str
    alias: str | None
    machine_type: str
    status: str
    material: str | None
    current_print: dict | None
    resin_level_ml: float | None
    tank_serial: str | None
    tank_layers_printed: int | None
    group_name: str | None
    group_id: str | None
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class CartridgeInfo:
    serial: str
    material: str | None
    display_name: str
    initial_volume_ml: float
    volume_dispensed_ml: float
    remaining_ml: float
    printer_serial: str | None
    is_empty: bool


class DashboardClient:
    """Async client for the Formlabs Dashboard Web API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
    ):
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

        # Cached data
        self.printers: dict[str, PrinterStatus] = {}
        self.cartridges: dict[str, CartridgeInfo] = {}
        self.recent_prints: list[dict] = []

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        return ssl.create_default_context(cafile=certifi.where())

    async def _ensure_token(self) -> str:
        """Get a valid OAuth token, refreshing if expired."""
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at
        ):
            return self._access_token

        logger.info("Requesting Dashboard API access token")
        async with self._session.post(
            f"{BASE_URL}/developer/v1/o/token/",
            ssl=self._ssl_context(),
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        ) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(f"Dashboard auth failed ({resp.status}): {text}")
            data = await resp.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 86400)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        logger.info("Dashboard API token acquired (expires in %ds)", expires_in)
        return self._access_token

    async def _get(self, path: str) -> dict | list:
        """Authenticated GET request to Dashboard API."""
        token = await self._ensure_token()
        async with self._session.get(
            f"{BASE_URL}{path}",
            ssl=self._ssl_context(),
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if not resp.ok:
                text = await resp.text()
                logger.warning("Dashboard API %s failed (%d): %s", path, resp.status, text[:200])
                return {}
            return await resp.json()

    async def poll_printers(self) -> None:
        """Fetch all printers and their status from Dashboard."""
        data = await self._get("/developer/v1/printers/")
        if not isinstance(data, list):
            return

        for p in data:
            serial = p.get("serial", "")
            ps = p.get("printer_status", {})
            tank = p.get("tank_status", {}).get("tank") or {}
            cartridges = p.get("cartridge_status") or []
            group = p.get("group") or {}

            # Get resin level from first cartridge
            resin_ml = None
            if cartridges and isinstance(cartridges, list) and len(cartridges) > 0:
                cart_entry = cartridges[0]
                if isinstance(cart_entry, dict):
                    cart = cart_entry.get("cartridge", {}) or {}
                    initial = cart.get("initial_volume_ml", 0) or 0
                    dispensed = cart.get("volume_dispensed_ml", 0) or 0
                    resin_ml = max(0, initial - dispensed)

            current_print = None
            cp = ps.get("current_print_run")
            if cp:
                current_print = {
                    "name": cp.get("name", ""),
                    "status": cp.get("status", ""),
                    "progress_pct": 0,
                    "estimated_remaining_ms": cp.get("estimated_time_remaining_ms", 0),
                }
                layer_count = cp.get("layer_count", 0)
                current_layer = cp.get("currently_printing_layer", 0)
                if layer_count > 0:
                    current_print["progress_pct"] = round(100 * current_layer / layer_count)

            self.printers[serial] = PrinterStatus(
                serial=serial,
                alias=p.get("alias"),
                machine_type=p.get("machine_type_id", ""),
                status=ps.get("status", "offline"),
                material=tank.get("material"),
                current_print=current_print,
                resin_level_ml=resin_ml,
                tank_serial=tank.get("serial"),
                tank_layers_printed=tank.get("layers_printed"),
                group_name=group.get("name"),
                group_id=str(group.get("id", "")),
            )

        logger.debug("Polled %d printers from Dashboard", len(self.printers))

    async def poll_cartridges(self) -> None:
        """Fetch all resin cartridges from Dashboard."""
        data = await self._get("/developer/v1/cartridges/")
        results = data.get("results", []) if isinstance(data, dict) else []

        for c in results:
            serial = c.get("serial", "")
            initial = c.get("initial_volume_ml", 0)
            dispensed = c.get("volume_dispensed_ml", 0)
            self.cartridges[serial] = CartridgeInfo(
                serial=serial,
                material=c.get("material"),
                display_name=c.get("display_name", ""),
                initial_volume_ml=initial,
                volume_dispensed_ml=dispensed,
                remaining_ml=max(0, initial - dispensed),
                printer_serial=c.get("inside_printer"),
                is_empty=c.get("is_empty", False),
            )

        logger.debug("Polled %d cartridges from Dashboard", len(self.cartridges))

    async def poll_recent_prints(self, limit: int = 50) -> None:
        """Fetch recent print history."""
        data = await self._get(f"/developer/v1/prints/?per_page={limit}")
        results = data.get("results", []) if isinstance(data, dict) else []
        self.recent_prints = results
        logger.debug("Polled %d recent prints from Dashboard", len(results))

    def get_printer_dict(self, serial: str) -> dict | None:
        """Get printer status as a JSON-serializable dict."""
        ps = self.printers.get(serial)
        if not ps:
            return None
        return {
            "serial": ps.serial,
            "alias": ps.alias,
            "machine_type": ps.machine_type,
            "status": ps.status,
            "current_print": ps.current_print,
            "material": ps.material,
            "resin_level_ml": ps.resin_level_ml,
            "tank_serial": ps.tank_serial,
            "tank_layers_printed": ps.tank_layers_printed,
            "group": ps.group_name,
            "last_updated": ps.last_updated.isoformat(),
        }

    def get_all_printers(self) -> list[dict]:
        """All printers as JSON-serializable list."""
        return [self.get_printer_dict(s) for s in self.printers]

    def get_all_cartridges(self) -> list[dict]:
        """All cartridges as JSON-serializable list."""
        return [
            {
                "serial": c.serial,
                "material": c.material,
                "display_name": c.display_name,
                "initial_volume_ml": c.initial_volume_ml,
                "volume_dispensed_ml": c.volume_dispensed_ml,
                "remaining_ml": c.remaining_ml,
                "printer": c.printer_serial,
                "is_empty": c.is_empty,
            }
            for c in self.cartridges.values()
        ]


async def dashboard_poller(
    client: DashboardClient,
    interval_seconds: float = 30.0,
) -> None:
    """Background task that polls Dashboard API on a regular interval."""
    logger.info("Dashboard poller started (interval=%ds)", interval_seconds)
    while True:
        try:
            await client.poll_printers()
            await client.poll_cartridges()
            await client.poll_recent_prints()
        except Exception as e:
            logger.warning("Dashboard poll failed: %s", e)
        await asyncio.sleep(interval_seconds)
