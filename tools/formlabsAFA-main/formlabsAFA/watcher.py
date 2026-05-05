from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import shutil
from pathlib import Path
from typing import Callable, Coroutine

import watchdog.events
import watchdog.observers

from formlabsAFA.context import AppContext

logger = logging.getLogger("formlabsAFA.watcher")


class _EventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(
        self,
        callback: Callable[[str], Coroutine],
        loop: asyncio.AbstractEventLoop,
        extensions: set[str],
    ):
        self._callback = callback
        self._loop = loop
        self._extensions = extensions
        self._futures: set[concurrent.futures.Future] = set()

    def _handle(self, path: str) -> None:
        name = Path(path).name
        if self._extensions and not any(
            name.casefold().endswith(ext) for ext in self._extensions
        ):
            return
        future = asyncio.run_coroutine_threadsafe(self._callback(name), self._loop)
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)

    def on_created(self, event: watchdog.events.FileSystemEvent) -> None:
        self._handle(event.src_path)

    def on_moved(self, event: watchdog.events.FileSystemEvent) -> None:
        self._handle(event.dest_path)


class FolderWatcher:
    def __init__(
        self,
        path: Path,
        callback: Callable[[str], Coroutine],
        loop: asyncio.AbstractEventLoop,
        extensions: set[str] | None = None,
    ):
        self._path = path
        self._handler = _EventHandler(callback, loop, extensions or set())
        self._observer = watchdog.observers.Observer()
        self._observer.schedule(self._handler, str(path))

    def start(self) -> None:
        self._observer.start()
        logger.info("Watching folder: %s", self._path)

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()


async def _on_new_stl(ctx: AppContext, filename: str) -> None:
    ctx.model_queue.add_model(filename)
    await _maybe_process_queue(ctx)


async def _maybe_process_queue(ctx: AppContext) -> None:
    from formlabsAFA.batch import BatchOrchestrator
    import time

    config = ctx.config.batch
    queue = ctx.model_queue

    while True:
        if queue.count == 0:
            return

        if not config.process_partial_batches and queue.count < config.initial_batch_size:
            return

        if (
            config.process_partial_batches
            and queue.count < config.initial_batch_size
        ):
            elapsed = time.time() - queue.last_model_time
            if elapsed < config.delay_between_checks_seconds:
                await asyncio.sleep(config.delay_between_checks_seconds - elapsed)
                continue  # Re-check queue after delay

        filenames = queue.drain_batch(config.initial_batch_size)
        if not filenames:
            return

        logger.info("Processing batch of %d models", len(filenames))
        orchestrator = BatchOrchestrator(ctx)
        await orchestrator.run_batches(filenames)
        # Loop continues to check for more models / requeued models


async def _on_reprocess_file(ctx: AppContext, filename: str) -> None:
    if not filename.endswith(".form"):
        return
    ws = ctx.workspace
    client = ctx.preform_client
    form_path = ws.batches_to_reprocess / filename

    batch_folder_name = Path(filename).stem
    batch_folder = ws.batches_to_reprocess / batch_folder_name
    if batch_folder.is_dir():
        return  # Already processed

    logger.info("Reprocessing rejected batch: %s", filename)

    load_result = await client.load_form(str(form_path))
    scene_id = load_result.result["id"]
    scene = await client.get_scene(scene_id)

    await asyncio.to_thread(os.makedirs, str(batch_folder), exist_ok=True)
    for model in scene["models"]:
        stl_name = f"{model['name']}.stl"
        src = ws.stl_completed / stl_name
        if src.exists():
            await asyncio.to_thread(shutil.copy, str(src), str(batch_folder / stl_name))
            logger.debug("Copied %s to reprocess folder", stl_name)

    await client.delete_scene(scene_id)


def setup_watchers(ctx: AppContext, loop: asyncio.AbstractEventLoop) -> list[FolderWatcher]:
    watchers = []

    input_watcher = FolderWatcher(
        ctx.workspace.stl_input,
        lambda name: _on_new_stl(ctx, name),
        loop,
        extensions={".stl"},
    )
    input_watcher.start()
    watchers.append(input_watcher)

    reprocess_watcher = FolderWatcher(
        ctx.workspace.batches_to_reprocess,
        lambda name: _on_reprocess_file(ctx, name),
        loop,
        extensions={".form"},
    )
    reprocess_watcher.start()
    watchers.append(reprocess_watcher)

    return watchers
