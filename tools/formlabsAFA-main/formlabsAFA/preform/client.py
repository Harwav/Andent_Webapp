from __future__ import annotations

import logging
from typing import Any

import aiohttp

from formlabsAFA.preform.operations import (
    OperationResult,
    OperationState,
    OperationTracker,
)

logger = logging.getLogger("formlabsAFA.preform.client")


class PreFormError(Exception):
    def __init__(self, message: str, details: str = "", payload: Any = None):
        self.message = message
        self.details = details
        self.payload = payload
        full = f"{message}: {details}" if details else message
        super().__init__(full)


class PreFormClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str = "localhost",
        port: int = 44388,
    ):
        self._session = session
        self.base_url = f"http://{host}:{port}"
        self.ops = OperationTracker(session, self.base_url)

    # -- Error handling --

    async def _raise_for_status(
        self,
        message: str,
        response: aiohttp.ClientResponse,
        payload: Any = None,
    ) -> None:
        if response.ok:
            return
        try:
            error_json = await response.json()
            details = error_json.get("error", {}).get("message", str(response))
        except Exception:
            details = str(response)
        raise PreFormError(message, details, payload)

    def _raise_for_operation(
        self, message: str, result: OperationResult
    ) -> None:
        if result.state == OperationState.FAILED:
            details = ""
            if isinstance(result.result, dict):
                details = (
                    result.result.get("error", {}).get("message", str(result.result))
                )
            raise PreFormError(message, details)

    # -- Scene management --

    async def create_scene(self, material_payload: dict) -> str:
        async with self._session.post(
            f"{self.base_url}/scene/", json=material_payload
        ) as resp:
            await self._raise_for_status("Error creating scene", resp, material_payload)
            data = await resp.json()
            return data["id"]

    async def delete_scene(self, scene_id: str) -> None:
        async with self._session.delete(
            f"{self.base_url}/scene/{scene_id}/"
        ) as resp:
            await self._raise_for_status("Error deleting scene", resp)

    async def get_scene(self, scene_id: str) -> dict:
        async with self._session.get(
            f"{self.base_url}/scene/{scene_id}/"
        ) as resp:
            await self._raise_for_status("Error getting scene", resp)
            return await resp.json()

    # -- Model operations --

    async def scan_to_model(
        self, scene_id: str, payload: dict
    ) -> OperationResult:
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/scan-to-model/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error in scan-to-model", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error in scan-to-model", result)
            return result

    async def import_model(
        self,
        scene_id: str,
        file: str,
        repair_behavior: str = "IGNORE",
        name: str | None = None,
        orientation: dict | None = None,
    ) -> OperationResult:
        payload: dict[str, Any] = {"file": file, "repair_behavior": repair_behavior}
        if name is not None:
            payload["name"] = name
        if orientation is not None:
            payload["orientation"] = orientation
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/import-model/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error importing model", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error importing model", result)
            return result

    async def delete_model(self, scene_id: str, model_id: str) -> None:
        async with self._session.delete(
            f"{self.base_url}/scene/{scene_id}/models/{model_id}/"
        ) as resp:
            await self._raise_for_status("Error deleting model", resp)

    async def update_model(
        self, scene_id: str, model_id: str, payload: dict
    ) -> dict:
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/models/{model_id}/",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error updating model", resp, payload)
            return await resp.json()

    # -- Layout --

    async def auto_layout(
        self,
        scene_id: str,
        models: list[str] | str,
        model_spacing_mm: float,
        layout_bounds: dict,
        lock_rotation: bool = True,
    ) -> OperationResult:
        payload = {
            "models": models,
            "model_spacing_mm": model_spacing_mm,
            "lock_rotation": lock_rotation,
            "custom_bounds": layout_bounds,
        }
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/auto-layout/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error in auto-layout", resp, payload)
            return await self.ops.wait_on_response(resp)

    async def get_interferences(
        self, scene_id: str, collision_offset_mm: float = 1.0
    ) -> dict:
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/interferences/",
            json={"collision_offset_mm": collision_offset_mm},
        ) as resp:
            await self._raise_for_status("Error getting interferences", resp)
            return await resp.json()

    # -- Print validation --

    async def get_print_validation(self, scene_id: str) -> OperationResult:
        async with self._session.get(
            f"{self.base_url}/scene/{scene_id}/print-validation/?async=true"
        ) as resp:
            await self._raise_for_status("Error getting print validation", resp)
            return await self.ops.wait_on_response(resp)

    # -- Support --

    async def auto_support(
        self, scene_id: str, model_ids: list[str], only_minima: bool = True
    ) -> OperationResult:
        payload = {
            "models": model_ids,
            "only_minima": only_minima,
            "raft_type": "MINI_RAFTS_ON_BP",
        }
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/auto-support/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error in auto-support", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error in auto-support", result)
            return result

    # -- Labels --

    async def add_label(
        self,
        scene_id: str,
        model_id: str,
        label: str,
        position: dict,
        orientation: dict,
        font_size_mm: float = 4.0,
        depth_mm: float = 1.0,
    ) -> OperationResult:
        payload = {
            "model_id": model_id,
            "orientation": orientation,
            "position": position,
            "label": label,
            "font_size_mm": font_size_mm,
            "depth_mm": depth_mm,
        }
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/label/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error adding label", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error adding label", result)
            return result

    # -- Save / Load / Print --

    async def save_form(self, scene_id: str, path: str) -> OperationResult:
        payload = {"file": path}
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/save-form/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error saving .form file", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error saving .form file", result)
            return result

    async def load_form(self, path: str) -> OperationResult:
        payload = {"file": path}
        async with self._session.post(
            f"{self.base_url}/load-form/?async=true", json=payload
        ) as resp:
            await self._raise_for_status("Error loading .form file", resp, payload)
            result = await self.ops.wait_on_response(resp)
            self._raise_for_operation("Error loading .form file", result)
            return result

    async def print_scene(
        self, scene_id: str, printer: str, job_name: str
    ) -> OperationResult:
        payload = {"printer": printer, "job_name": job_name}
        async with self._session.post(
            f"{self.base_url}/scene/{scene_id}/print/?async=true",
            json=payload,
        ) as resp:
            await self._raise_for_status("Error printing", resp, payload)
            return await self.ops.wait_on_response(resp)

    # -- Auth --

    async def dashboard_login(self, username: str, password: str) -> None:
        payload = {"username": username, "password": password}
        async with self._session.post(
            f"{self.base_url}/login/", json=payload
        ) as resp:
            await self._raise_for_status("Failed to log in to Dashboard", resp)
