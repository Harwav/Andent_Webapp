from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import tempfile
from pathlib import Path

import aiohttp
from rich.panel import Panel

from formlabsAFA.config import load_config
from formlabsAFA.context import AppContext, BatchCounter, WorkspacePaths
from formlabsAFA.db import Database
from formlabsAFA.frame_profile import FrameProfile, load_profiles
from formlabsAFA.log import console, setup_logging, tprint
from formlabsAFA.preform.client import PreFormClient
from formlabsAFA.preform.server import PreFormServer, find_preform_server_path
from formlabsAFA.queue import ModelQueue
from formlabsAFA.watcher import setup_watchers

logger = logging.getLogger("formlabsAFA")


async def main(config_path: Path, enable_api: bool = False, api_port: int = 8000) -> None:
    tprint(
        Panel.fit(
            "[bold cyan]formlabsAFA[/bold cyan]\n"
            "[dim]Formlabs Automated Aligners on Frames[/dim]",
            border_style="cyan",
        )
    )

    # 1. Load config
    config = load_config(config_path)
    tprint(f"[green]\u2714[/green] Loaded config from {config_path}")

    # 2. Setup logging + workspace
    workspace = WorkspacePaths(base=config.general.base_path / "workspace")
    workspace.ensure_dirs()
    log_level = "DEBUG" if config.general.debug else config.general.log_level
    setup_logging(log_level, workspace.logs)

    # 3. Database
    db = await Database.connect_or_initialize(
        config.general.base_path / "formlabsAFA.db"
    )
    tprint("[green]\u2714[/green] Database connected")

    # 4. PreForm Server
    tprint("[cyan]\u25b6[/cyan] Starting PreForm Server...")
    server_path = (
        find_preform_server_path(config.general.preform_server_path)
        if config.general.preform_server_path
        else find_preform_server_path()
    )
    preform_server = PreFormServer.start_or_connect(
        server_path, config.preform_server.port
    )
    tprint(
        f"[green]\u2714[/green] PreForm Server ready on port {config.preform_server.port}"
    )

    # 5. HTTP client
    loop = asyncio.get_running_loop()
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(
            sock_read=None,
            sock_connect=config.preform_server.connection_timeout_seconds,
        ),
        connector=aiohttp.TCPConnector(limit=20),
    )
    client = PreFormClient(
        session, config.preform_server.host, config.preform_server.port
    )

    # 6. Frame profiles — only loaded in frame mode
    profiles: dict[str, FrameProfile] = {}
    if config.build.mode == "frame":
        profiles_dir = Path(config.frame.profiles_dir)
        if not profiles_dir.is_absolute():
            profiles_dir = config.general.base_path / profiles_dir
        profiles = load_profiles(profiles_dir, config.free_layout.bounds)
        if not profiles:
            raise ValueError(
                f"build.mode='frame' but no frame profiles found in "
                f"{profiles_dir} — add at least one profile directory "
                f"containing profile.toml + frame.stl, or switch build.mode"
            )
        tprint(
            f"[green]\u2714[/green] Loaded {len(profiles)} frame profile(s): "
            + ", ".join(f"[bold]{name}[/bold]" for name in profiles)
        )
    else:
        tprint(f"[green]\u2714[/green] Mode '{config.build.mode}' — skipping frame profiles")

    # 6b. Fixture STL existence check (if enabled)
    if config.fixture.enabled:
        fixture_path = Path(config.fixture.stl_path)
        if not fixture_path.is_absolute():
            fixture_path = config.general.base_path / fixture_path
        if not fixture_path.is_file():
            raise ValueError(
                f"fixture.enabled=true but fixture STL not found at {fixture_path}"
            )

    # 7. Build context
    batch_counter = BatchCounter()
    ctx = AppContext(
        config=config,
        db=db,
        preform_client=client,
        preform_server=preform_server,
        frame_profiles=profiles,
        session=session,
        workspace=workspace,
        batch_counter=batch_counter,
        batch_semaphore=asyncio.BoundedSemaphore(config.batch.n_parallel_batches),
        chamfer_tmpdir=tempfile.TemporaryDirectory(),
    )
    import atexit
    atexit.register(ctx.chamfer_tmpdir.cleanup)

    # 8. Batch counter
    batch_counter.set_initial(workspace)

    # 9. Model queue
    model_queue = ModelQueue(workspace.stl_input)
    ctx.model_queue = model_queue  # type: ignore[attr-defined]
    model_queue.scan_input_folder()

    tprint(f"\n[cyan]\u25b6[/cyan] Monitoring: [bold]{workspace.stl_input}[/bold]")
    if model_queue.count > 0:
        tprint(f"  Found [bold]{model_queue.count}[/bold] existing models in queue")

    if not config.batch.process_partial_batches:
        tprint(
            f"  Batching starts at [bold]{config.batch.initial_batch_size}[/bold] models"
        )
    else:
        tprint("  Partial batches enabled \u2014 processing after short delay")

    # 10. Watchers
    watchers = setup_watchers(ctx, loop)

    # 11. Process existing queue
    if model_queue.count > 0:
        from formlabsAFA.watcher import _maybe_process_queue

        asyncio.create_task(_maybe_process_queue(ctx))

    # 12. Optional Dashboard API poller
    if config.dashboard_api.enabled:
        from formlabsAFA.dashboard import DashboardClient, dashboard_poller

        dashboard_client = DashboardClient(
            session, config.dashboard_api.client_id, config.dashboard_api.client_secret
        )
        ctx.dashboard_client = dashboard_client  # type: ignore[attr-defined]
        asyncio.create_task(dashboard_poller(
            dashboard_client, config.dashboard_api.poll_interval_seconds
        ))
        tprint(f"[green]\u2714[/green] Dashboard API poller started")

    # 13. Optional REST API
    if enable_api:
        from formlabsAFA.api import create_app
        import uvicorn

        app = create_app(ctx)
        api_config = uvicorn.Config(
            app, host="0.0.0.0", port=api_port, log_level="info"
        )
        api_server = uvicorn.Server(api_config)
        asyncio.create_task(api_server.serve())
        tprint(f"[green]\u2714[/green] REST API on port {api_port}")

    tprint("\n[green bold]Ready.[/green bold] Drop STL files into the input folder.\n")

    # 13. Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        tprint("\n[yellow]Shutdown signal received...[/yellow]")
        shutdown_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    for w in watchers:
        w.stop()
    await ctx.shutdown()

    tprint(
        Panel.fit(
            "[bold green]\u2714 formlabsAFA stopped[/bold green]",
            border_style="green",
        )
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="formlabsAFA",
        description="Formlabs Automated Aligners on Frames",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to config.toml config file",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Enable the optional REST API",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="Port for the REST API (default: 8000)",
    )
    args = parser.parse_args()

    if sys.platform not in ("win32", "cygwin"):
        try:
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass

    try:
        asyncio.run(main(args.config, args.api, args.api_port))
    except KeyboardInterrupt:
        tprint("\n[yellow]Interrupted[/yellow]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
