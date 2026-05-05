# formlabsAFA — Formlabs Automated Aligners on Frames

Drop STL files into a folder. formlabsAFA batches them onto frames (or auto-generated webbing), lays them out, and sends them to your Formlabs printer.

Built for dental labs running high-volume aligner model production on Formlabs SLA printers.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A Formlabs PreForm Server binary ([download](https://support.formlabs.com/s/article/Formlabs-API-downloads-and-release-notes))

## Setup

```bash
# Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/dombarry/formlabsAFA.git
cd formlabsAFA
uv sync
```

Place the PreForm Server binary in `PreForm_Server/`:

```
PreForm_Server/
├── PreFormServer.app        # macOS
└── PreFormServer.exe + *.dll  # Windows
```

## Configure

Edit `config.toml` — set your base path and printer:

```toml
[general]
base_path = "/absolute/path/to/formlabsAFA"

[printer]
upload_to_printer = false    # true to send to printer
```

See `config.toml` for all settings (material, hollowing, drain holes, layout bounds, etc).

## Run

```bash
uv run python -m formlabsAFA config.toml
```

With the REST API:

```bash
uv run python -m formlabsAFA config.toml --api
```

## Pipeline

1. **Merge** — Boolean-union multi-body STLs (fuses label letters into main arch)
2. **Chamfer** — Optional. Removes locating features to prevent flashing
3. **Import** — Scan-to-model with hollowing and drain holes via PreForm Server
4. **Orient** — All models set to z-up
5. **Layout** — Auto-layout within platform bounds, fallback strategies if models don't fit
6. **Frame or Webbing** — Either punch a pre-made frame or generate structural webbing between models (see below)
7. **Fixtures** — Optional. Insert fixture STL at each model position to restore locating features
8. **Save** — Export as `.form` file
9. **Upload** — Send to printer (if enabled)

## Frame Mode vs Webbing Mode

### Frame Mode (default)

Uses pre-made frame STL files from `frame_profiles/`. Models must land on the frame's horizontal spanners. Good for standardized production.

```toml
[webbing]
enabled = false

[frame]
profiles_dir = "frame_profiles"
```

### Webbing Mode

Generates structural webs dynamically between models. No pre-made frame needed — models pack freely via auto-layout, then thin beams connect neighbors. Typically fits more models per batch.

```toml
[webbing]
enabled = true
thickness_mm = 2.0          # web width
height_mm = 1.6             # web height (match tab height)
perimeter_rail = true       # border rail around outermost models
connect_front = true        # webs on -Y face
connect_back = false        # no webs on +Y (fixture side)
connect_left = true
connect_right = true
max_span_mm = 60.0          # skip webs longer than this
```

Webbing punches each model's true cross-section profile (including the inner U-cavity where fixtures sit) out of the web sheet, so fixtures are never obstructed.

## Workspace

Created automatically under `<base_path>/workspace/`:

```
workspace/
├── 1-stls-input/              # Drop STL files here
├── 2-stls-completed/          # Processed STLs
├── 3-batches-to-print/        # Generated .form files
├── 4-batches-printed/         # Uploaded to printer
├── 5-batches-to-reprocess/    # Drop .form files here to reprocess
└── logs/                      # Per-batch + global logs
```

## Logs

- `logs/formlabsAFA.log` — global log (always captures DEBUG)
- `logs/batch-{N}.log` — per-batch audit trail (ISO 8601 timestamps)
- Set `debug = true` in config for verbose console output

## REST API

When started with `--api`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health-check` | Returns `{"status": "OK"}` |
| `POST` | `/register-models` | Register STL files by path |
| `POST` | `/models-status` | Query processing status by model ID |
