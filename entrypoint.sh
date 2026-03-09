#!/bin/bash
set -e

echo "==> Pre-seeding enrichment data..."
python -c "from app.preseed import preseed_data; preseed_data()" || echo "Pre-seed skipped (non-fatal)"

echo "==> Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
