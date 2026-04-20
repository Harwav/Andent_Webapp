# === constants.py ===
import sys

# --- App Version ---
# v0.3.0: Implemented thread safety, resource cleanup, and performance optimizations
# v0.3.1: Fixed FPS file format compatibility (schema v3) and API field validation
# v0.3.2: Added print_setting field to FPS parser for API compatibility
# v0.3.3: Fixed layer thickness (use metadata 0.16mm not Core_Scene 0.12mm) and correct print_setting [SUPERSEDED BY v0.3.4]
# v0.3.4: Fixed 5 critical P0 issues - FPS validation unified (120um verified), auto_support removed (aligners-only), empty batch freeze prevented, bare exceptions replaced (6 fixes)
# v0.4.0: Added robust auto-update mechanism with GitHub Releases integration
# v0.4.1: Fixed macOS Tahoe/Sequoia Tcl/Tk crash (NSMenuItem), added dark mode, removed redundant startup dialog
# v0.4.2: Added Quick Settings sidebar, Recent Folders/Favorites, STL file validation before processing
# v0.4.3: Added Smart Batching (dimension-based batch optimization) with Settings toggle
# v0.4.4: Enhanced Configuration Sidebar with collapsible accordion sections for all settings
# v0.4.5: First-run setup wizard, Windows UI modernization (Segoe UI + DPI), fixed license email messaging, fixed PreFormServer version display
# v0.4.5.1: PreForm-style UI redesign - card panels, modern buttons, status pills, dark sidebar navigation
# v0.4.5.2: Fixed Virtual Printer Mode checkbox not working - settings.get() was passing True as from_history param instead of default
# v0.4.5.3: Code review fixes (15/16 issues) - shell injection, memory leaks, exception handling, thread naming, DPI awareness
# v0.4.5.4: UI polish - remove stuck printer tooltip, remove unnecessary scrolling from Config panel, remove mm unit labels
# v0.4.6: Infrastructure improvements - CHANGELOG.md, file organization, git hooks, fix-issues workflow
# v0.4.7: Batch file import (50-70% faster processing) + print validation before save/print
# v0.4.7.1: Microsoft Fluent Design System modernization - Windows 11 colors, typography, icons, animations
# v0.4.7.2: Modern Dashboard UI - soft backgrounds, tinted stat cards, shadow cards, increased spacing
# v0.4.7.3: UI Polish - centered stat numbers, thin scrollbars, consistent typography, section headers
# v0.4.7.4: 3D Buttons & Visual Depth - groove relief buttons with pressed state, enhanced card shadows, improved stat card centering, primary blue progress bar
# v0.4.7.5: Linear/Notion Minimal Design - flat buttons, no shadows, typography per DESIGN_PRINCIPLES.md, 48px blue hero stats
# v0.4.8: Infrastructure validation release - verified PreFormServer v0.9.9, licensing, auto-update, UI compliance
# v0.4.9: License simplification - single "Licensed" tier with all features, trial gets full access (50 STL limit)
# v0.4.10: PreFormServer setup streamlining - AppData location, ZIP installation, auto-start/stop, auto-recovery
# v0.4.11: Update UX improvements - persistent badge, auto-popup, structured changelog, prominent Install button
# v0.4.12: Code review fixes - license gating bypass, pause busy loop, POST retry duplication, report worker leak, negative stats guard, os.listdir exception handling
# v0.4.13: UI/UX modernization - warm grays, border radius tokens, shadow borders, 48px hero stats with trends, improved sidebar spacing
# v0.4.14: GUI Style Centralization - update notification colors with _LIGHT/_DARK variants, SPACING_LEGACY tokens, verify_theme_usage.py enforcement script
# v0.4.15: UI Polish - panel styling consistency, stats cards LabelFrame wrapper, input alignment, status bar separators, button hierarchy
# v0.4.16: PreFormServer version compatibility checking - validates API version at startup, shows warning/upgrade dialog if incompatible
# v0.4.17: Responsive UI scaling for lower resolution screens - auto-collapse sidebar, scaled fonts/spacing/controls
# v0.4.18: Processing speed optimizations - per-batch validation (immediate progress), async form export (no blocking between batches), scene pre-creation (overlap with auto-layout)
# v0.6.7: Smart batching tuned for aligner arches, async form export ownership/progress fixes, per-batch lifetime stats, optional print validation toggle, stage timing logs
APP_VERSION = "0.6.7"

# --- Update System Configuration ---
# GitHub repository for updates (PUBLIC repo for releases, private source code stays in FormFlow_Dent)
UPDATE_GITHUB_REPO = "Harwav/FormFlow_Dent_Releases"
# Tag prefixes for releases
FORMFLOW_RELEASE_TAG_PREFIX = "formflow-v"
PREFORMSERVER_RELEASE_TAG_PREFIX = "preformserver-v"
# Update check interval (hours)
UPDATE_CHECK_INTERVAL_HOURS = 24
# Delay before background update check (seconds)
UPDATE_CHECK_DELAY_SECONDS = 5
# Maximum number of backups to keep
UPDATE_BACKUP_COUNT = 3

# --- API Configuration ---
# Local server for processing STLs
LOCAL_SERVER_URL = "http://localhost:44388"

# --- PreFormServer Configuration ---
# Port for PreFormServer API
PREFORMSERVER_PORT = 44388
# Timeout for PreFormServer startup (seconds)
PREFORMSERVER_STARTUP_TIMEOUT_S = 30
# Timeout for PreFormServer shutdown (seconds)
PREFORMSERVER_SHUTDOWN_TIMEOUT_S = 10
# Minimum expected ZIP file size (10MB - PreFormServer is ~80MB)
PREFORMSERVER_MIN_ZIP_SIZE = 10 * 1024 * 1024
# Formlabs download page URL
PREFORMSERVER_DOWNLOAD_URL = "https://support.formlabs.com/s/article/Formlabs-API-downloads-and-release-notes"

# --- PreFormServer Version Compatibility ---
# Uses BUILD version (e.g., "3.54.0.602") not API spec version (e.g., "0.9.11")
# The GET / endpoint returns build version, not API spec version
# Fallback versions used when GitHub fetch fails
PREFORMSERVER_BUILD_MIN_VERSION_FALLBACK = "3.55.0"  # Fallback minimum if GitHub unavailable (maps to API 0.9.11)
PREFORMSERVER_BUILD_MAX_VERSION = None               # Maximum supported (None = no limit)
# Strict mode blocks app if incompatible; False shows warning only
VERSION_CHECK_STRICT = False  # Warn but allow user to continue

# --- Network Robustness ---
# Timeout to handle large .form file uploads and long processing
HTTP_TIMEOUT_SECONDS = 600
# Number of retries for transient connection errors
HTTP_MAX_RETRIES = 5
# Base for exponential backoff calculation
HTTP_BACKOFF_BASE = 1.0

# --- Job Management ---
# Max wait time for a single asynchronous operation to complete
MAX_JOB_WAIT = 900

# --- Performance Configuration ---
# Maximum number of parallel volume calculations
MAX_VOLUME_WORKERS = 8
# Maximum cache size for volume calculations (number of entries)
MAX_VOLUME_CACHE_SIZE = 10000
# GUI update interval in milliseconds
GUI_UPDATE_INTERVAL_MS = 100
# Batch size for volume calculations
VOLUME_CALC_BATCH_SIZE = 100

# --- File System Limits ---
# Maximum filename length for Windows compatibility
MAX_FILENAME_LENGTH = 255
# Maximum path length (Windows=260, macOS/Linux=1024)
MAX_PATH_LENGTH = 260 if sys.platform == "win32" else 1024

# --- STL Validation ---
# Minimum valid binary STL size (80-byte header + 4-byte triangle count)
STL_MIN_FILE_SIZE = 84
# Maximum file size to process (500MB)
STL_MAX_FILE_SIZE = 500 * 1024 * 1024
# File size threshold for warning (50MB)
STL_WARN_LARGE_SIZE = 50 * 1024 * 1024

# --- Quick Settings Sidebar ---
# Default sidebar width in pixels
SIDEBAR_DEFAULT_WIDTH = 220
# Expanded sidebar width for full configuration (v0.4.4, P0-3: increased for text fit)
SIDEBAR_EXPANDED_WIDTH = 300
# Collapsed sidebar width (v0.4.8: increased from 40 to 56 for arrow button visibility)
SIDEBAR_COLLAPSED_WIDTH = 56
# Maximum recent folders to remember
MAX_RECENT_FOLDERS = 10
# v0.4.17: Auto-collapse threshold (effective width in pixels)
SIDEBAR_AUTO_COLLAPSE_WIDTH = 1100
# v0.5.2: Auto-collapse threshold for height (effective height in pixels)
SIDEBAR_AUTO_COLLAPSE_HEIGHT = 600

# --- UI Scaling (v0.4.17) ---
# Feature flag for responsive UI scaling
ENABLE_UI_SCALING = True
# Minimum window size (base values, scaled by UI scale factor)
MIN_WINDOW_WIDTH_BASE = 900
MIN_WINDOW_HEIGHT_BASE = 600

# --- Batch Import (v0.4.7) ---
# Maximum files per batch API call
BATCH_IMPORT_LIMIT = 10
# Feature flag for batch import (set to False to revert to parallel mode)
ENABLE_BATCH_IMPORT = True
# Batch request timeout (longer than single file due to multiple files)
BATCH_REQUEST_TIMEOUT_S = 120
# Retry policy for batch operations
BATCH_MAX_RETRIES = 1
# Enable individual retry for failed files in batch
BATCH_RETRY_INDIVIDUAL_FILES = True

# --- Smart Batching ---
# Build plate dimensions (width_mm, depth_mm) for each printer family
BUILD_PLATES = {
    "Form 4": (200.0, 125.0),
    "Form 4B": (200.0, 125.0),
    "Form 4L": (335.0, 200.0),
    "Form 4BL": (335.0, 200.0),
    "Form 3": (145.0, 145.0),
    "Form 3B": (145.0, 145.0),
    "Form 3L": (335.0, 200.0),
    "Form 3BL": (335.0, 200.0),
}
# Default build plate (Form 4)
DEFAULT_BUILD_PLATE = (200.0, 125.0)
# Packing efficiency factor (0.85 = 85% of build plate area usable)
# Increased from 0.72 to allow more models to fit - the original value was too conservative
# and resulted in smart batching fitting fewer models than manual arrangement
PACKING_EFFICIENCY = 0.92
# Maximum batch size safety cap
MAX_BATCH_SIZE_CAP = 20

# --- License Features ---
# Available license features
LICENSE_FEATURE_FORM_EXPORT = "form_export"
LICENSE_FEATURE_HOLLOWING = "hollowing"
LICENSE_FEATURE_AUTO_SUPPORT = "auto_support"
LICENSE_FEATURE_ADVANCED_STATS = "advanced_stats"
LICENSE_FEATURE_REPORT_EXPORT = "report_export"
LICENSE_FEATURE_PHYSICAL_PRINTERS = "physical_printers"

# License types (v0.4.21: Single tier, no more tier distinctions)
LICENSE_TYPE_LICENSED = "licensed"   # All features
