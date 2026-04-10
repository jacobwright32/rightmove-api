"""Benchmark scraper performance: sequential vs concurrent postcode scraping.

Usage:
    python scripts/benchmark_scrape.py [--postcodes N] [--area PARTIAL]

Defaults to 20 postcodes from SW20.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SCRAPER_MAX_WORKERS
from app.scraper.scraper import normalise_postcode_for_url, scrape_postcode_from_listing


def _load_postcodes(area: str, limit: int) -> list[str]:
    """Load postcodes from local parquet files for a given area prefix."""
    import pyarrow.parquet as pq

    parquet_dir = Path(__file__).resolve().parent.parent / "data" / "postcodes"
    partial = area.upper().replace("-", "").replace(" ", "")

    all_pcs: list[str] = []
    for pf in sorted(parquet_dir.glob(f"{partial}*.parquet")):
        table = pq.read_table(pf, columns=["postcode"])
        all_pcs.extend(table.column("postcode").to_pylist())

    all_pcs.sort()
    return all_pcs[:limit]


def _scrape_one(pc: str) -> tuple[str, int, float]:
    """Scrape a single postcode and return (postcode, count, elapsed)."""
    t0 = time.monotonic()
    props = scrape_postcode_from_listing(normalise_postcode_for_url(pc))
    elapsed = time.monotonic() - t0
    return pc, len(props), elapsed


def run_sequential(postcodes: list[str]) -> tuple[float, list[tuple[str, int, float]]]:
    """Scrape postcodes one at a time. Returns (total_time, results)."""
    results = []
    t0 = time.monotonic()
    for pc in postcodes:
        results.append(_scrape_one(pc))
    total = time.monotonic() - t0
    return total, results


def run_concurrent(postcodes: list[str], workers: int) -> tuple[float, list[tuple[str, int, float]]]:
    """Scrape postcodes concurrently. Returns (total_time, results)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_scrape_one, pc): pc for pc in postcodes}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                pc = futures[future]
                print(f"  ERROR {pc}: {e}")
                results.append((pc, 0, 0.0))
    total = time.monotonic() - t0
    return total, results


def main():
    parser = argparse.ArgumentParser(description="Benchmark scraper speed")
    parser.add_argument("--postcodes", type=int, default=20, help="Number of postcodes to test")
    parser.add_argument("--area", default="SW20", help="Area prefix for postcode lookup")
    parser.add_argument("--workers", type=int, default=SCRAPER_MAX_WORKERS, help="Concurrent workers")
    parser.add_argument("--skip-sequential", action="store_true", help="Skip sequential benchmark")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    postcodes = _load_postcodes(args.area, args.postcodes)
    if not postcodes:
        print(f"No postcodes found for area '{args.area}'. Run generate_postcodes.py first.")
        sys.exit(1)

    print(f"Benchmarking {len(postcodes)} postcodes from {args.area} (workers={args.workers})")
    print("=" * 60)

    # --- Sequential ---
    if not args.skip_sequential:
        print(f"\nSequential ({len(postcodes)} postcodes)...")
        seq_time, seq_results = run_sequential(postcodes)
        seq_props = sum(r[1] for r in seq_results)
        seq_avg = seq_time / len(postcodes) if postcodes else 0
        print(f"  Total: {seq_time:.1f}s | Avg: {seq_avg:.2f}s/pc | Properties: {seq_props}")
    else:
        seq_time = None

    # --- Concurrent ---
    print(f"\nConcurrent ({len(postcodes)} postcodes, {args.workers} workers)...")
    con_time, con_results = run_concurrent(postcodes, args.workers)
    con_props = sum(r[1] for r in con_results)
    con_avg = con_time / len(postcodes) if postcodes else 0
    print(f"  Total: {con_time:.1f}s | Avg: {con_avg:.2f}s/pc | Properties: {con_props}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print(f"{'Mode':<15} {'Total (s)':>10} {'Avg/pc (s)':>12} {'Properties':>12}")
    print("-" * 60)
    if seq_time is not None:
        print(f"{'Sequential':<15} {seq_time:>10.1f} {seq_avg:>12.2f} {seq_props:>12}")
    print(f"{'Concurrent':<15} {con_time:>10.1f} {con_avg:>12.2f} {con_props:>12}")
    if seq_time is not None and con_time > 0:
        speedup = seq_time / con_time
        print(f"\nSpeedup: {speedup:.1f}x")


if __name__ == "__main__":
    main()
