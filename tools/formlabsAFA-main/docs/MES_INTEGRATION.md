# MES Integration Guide

## Overview

formlabsAFA provides a two-way REST API for MES integration. The MES submits print jobs with metadata, and formlabsAFA reports back printer status, job progress, and material levels.

```
┌─────────┐    POST /jobs                ┌──────────────┐    poll every 30s   ┌──────────────┐
│   MES   │ ──────────────────────────▶  │  formlabsAFA │ ◀────────────────  │  Formlabs    │
│         │ ◀──────────────────────────  │   (API mode) │ ────────────────▶  │  Dashboard   │
└─────────┘    GET /printers, webhooks   └──────────────┘                    └──────────────┘
```

## Starting in API Mode

```bash
uv run python -m formlabsAFA config.toml --api --api-port 8000
```

## API Endpoints

### Jobs (MES → formlabsAFA)

**POST `/jobs`** — Submit STL files with metadata and priority
```json
{
  "stl_paths": ["/path/to/upper.stl", "/path/to/lower.stl"],
  "metadata": {"patient_id": "P-12345", "order_id": "ORD-2026-0042"},
  "priority": "normal",
  "callback_url": "https://mes.example.com/webhooks/formlabs"
}
```
Priority: `low`, `normal`, `high`, `rush`

**GET `/jobs/{model_id}`** — Get job status
```json
{"status": "OK", "model_status": {"value": "enqueued", "job_name": "b00001_20x_uuid.form", "printer_serial": "ABC123"}}
```

**GET `/queue`** — Current queue state

### Printers & Materials (formlabsAFA → MES)

Requires `[dashboard_api]` configured in config.toml.

**GET `/printers`** — All printers with live status
```json
[{
  "serial": "ABC123",
  "alias": "Form 4 - Bay 1",
  "status": "idle",
  "current_print": null,
  "material": "Grey V5",
  "resin_level_ml": 450,
  "tank_serial": "TANK-001",
  "group": "Production Floor"
}]
```

**GET `/printers/{serial}`** — Single printer detail

**GET `/materials`** — Resin cartridge inventory
```json
[{
  "serial": "CART-001",
  "material": "FLFMGR01",
  "display_name": "Grey V5",
  "initial_volume_ml": 1000,
  "volume_dispensed_ml": 550,
  "remaining_ml": 450,
  "printer": "ABC123"
}]
```

**GET `/health-check`** — Service health

### Legacy Endpoints (backward compatible)

- `POST /register-models` — simple file submission (no metadata)
- `POST /models-status` — bulk status query

## Status Lifecycle

```
registered → batched → hollowed → enqueued → completed
                                           → failed
                                → cancelled
```

## Webhooks

If a `callback_url` is provided in the job submission, formlabsAFA will POST status updates:

```json
{
  "event": "job.status_changed",
  "job_id": "a1b2c3d4-...",
  "status": "completed",
  "printer_serial": "ABC123",
  "form_file": "b00001_20x_uuid.form",
  "timestamp": "2026-04-14T11:43:04Z",
  "metadata": {"patient_id": "P-12345"}
}
```

## Dashboard API Setup

To enable printer/material monitoring:

1. Go to [dashboard.formlabs.com/#developer](https://dashboard.formlabs.com/#developer)
2. Create application credentials (Client ID + Client Secret)
3. Add to `config.toml`:

```toml
[dashboard_api]
enabled = true
client_id = "your_client_id"
client_secret = "your_client_secret"
poll_interval_seconds = 30
```

The poller authenticates via OAuth and refreshes the token automatically (24h expiry).

## Printer Upload

Jobs are sent to printers via PreForm Server. Configure in `config.toml`:

```toml
[printer]
serial_or_group_queue_id = "PRINTER-SERIAL"  # or Fleet Control queue ID
upload_to_printer = true
backup_printer_list = ["SERIAL-2", "SERIAL-3"]
```

For Fleet Control (multi-printer load balancing), use a group queue ID and set dashboard credentials.

## Network

| Service | Default Port | Config |
|---|---|---|
| formlabsAFA REST API | 8000 | `--api-port` |
| PreForm Server | 44388 | `[preform_server] port` |
| Formlabs Dashboard | HTTPS | `[dashboard_api]` |

The API binds to `0.0.0.0`. For production, use a reverse proxy with auth.
