"""Version constants persisted with each match for reproducibility."""

from __future__ import annotations

# App storage layout version introduced by migration 003_storage_v2.sql.
STORAGE_SCHEMA_VERSION = "2"

# Probe wire/semantics contract recorded at import time.
# Bump when structural_probe output used for storage decisions changes.
STRUCTURAL_PROBE_VERSION = "1"
