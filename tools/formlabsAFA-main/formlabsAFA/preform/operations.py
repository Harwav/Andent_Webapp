from __future__ import annotations

import asyncio
import enum
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger("formlabsAFA.preform.operations")


@enum.unique
class OperationState(enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class OperationResult:
    state: OperationState
    result: dict
    operation_id: str


@dataclass
class _TrackedOperation:
    progress: float
    future: asyncio.Future[OperationState]
    progress_callback: Callable[[float], None]


class OperationTracker:
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self._session = session
        self._base_url = base_url
        self._operations: dict[str, _TrackedOperation] = {}
        self._poll_task: asyncio.Task | None = None

    async def wait(
        self,
        operation_id: str,
        progress_callback: Callable[[float], None] = lambda _: None,
    ) -> OperationResult:
        future: asyncio.Future[OperationState] = asyncio.Future()
        self._operations[operation_id] = _TrackedOperation(
            progress=0.0,
            future=future,
            progress_callback=progress_callback,
        )
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())

        state = await future

        async with self._session.get(
            f"{self._base_url}/operations/{operation_id}"
        ) as resp:
            resp_json = await resp.json()
            return OperationResult(state, resp_json.get("result"), operation_id)

    async def wait_on_response(
        self,
        response: aiohttp.ClientResponse,
        progress_callback: Callable[[float], None] = lambda _: None,
    ) -> OperationResult:
        resp_json = await response.json()
        operation_id = resp_json["operationId"]
        return await self.wait(operation_id, progress_callback)

    async def _poll_loop(self) -> None:
        while self._operations:
            try:
                async with self._session.get(
                    f"{self._base_url}/operations/"
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                ops_by_id = {
                    op["id"]: op
                    for op in data["operations"]
                    if op["id"] in self._operations
                }

                for op_id, op_data in ops_by_id.items():
                    tracked = self._operations[op_id]
                    status = op_data["status"]
                    progress = op_data.get("progress", 0.0)

                    if status == "IN_PROGRESS" and progress > tracked.progress:
                        tracked.progress = progress
                        tracked.progress_callback(progress)
                    elif status in ("SUCCEEDED", "FAILED"):
                        tracked.future.set_result(OperationState(status))
                        del self._operations[op_id]

            except Exception:
                logger.exception("Error polling operations")

            await asyncio.sleep(0.1)

        self._poll_task = None
