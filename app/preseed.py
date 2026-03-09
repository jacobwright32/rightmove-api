"""Pre-download enrichment data caches on startup.

Large datasets (NaPTAN ~96MB, ONS ~120MB) download lazily on first request,
causing 30-120s delays. This module pre-seeds them so the app is ready to go.

Skip with SKIP_PRESEED=true environment variable.
"""

import logging
import os

logger = logging.getLogger(__name__)

_STEPS = [
    ("ONS Postcode Directory", "app.enrichment.ons_postcode", "_ensure_data"),
    ("Transport (NaPTAN)", "app.enrichment.transport", "_init_trees"),
    ("Schools (GIAS)", "app.enrichment.schools", "_init_trees"),
    ("Healthcare (NHS)", "app.enrichment.healthcare", "_init_trees"),
    ("Supermarkets (Geolytix)", "app.enrichment.supermarkets", "_init_trees"),
    ("IMD Deprivation", "app.enrichment.imd", "_ensure_data"),
    ("Broadband (Ofcom)", "app.enrichment.broadband", "_ensure_data"),
]


def preseed_data():
    """Download and cache all enrichment datasets. Non-fatal on failure."""
    if os.getenv("SKIP_PRESEED", "false").lower() == "true":
        logger.info("SKIP_PRESEED=true, skipping data pre-seed")
        return

    logger.info("Pre-seeding %d enrichment datasets...", len(_STEPS))
    for label, module_path, func_name in _STEPS:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            logger.info("  Loading %s...", label)
            fn()
            logger.info("  %s OK", label)
        except Exception:
            logger.warning("  %s FAILED (non-fatal)", label, exc_info=True)

    logger.info("Pre-seed complete")
