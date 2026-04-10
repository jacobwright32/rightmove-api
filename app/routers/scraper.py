import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import DATA_DIR, RATE_LIMIT_SCRAPE, SCRAPER_FRESHNESS_DAYS
from ..database import get_db
from ..export import save_property_parquet
from ..models import Property, Sale
from ..parsing import parse_date_to_iso, parse_price_to_int
from ..rate_limit import limiter
from ..schemas import AreaScrapeResponse, ScrapePropertyResponse, ScrapeResponse, ScrapeUrlRequest
from ..config import SCRAPER_MAX_WORKERS as _MW
from ..scraper.scraper import (
    PropertyData,
    _detail_pool,
    get_postcode_page_urls,
    get_single_house_details,
    normalise_postcode_for_url,
    scrape_for_sale_listings,
    scrape_postcode_from_listing,
    scrape_postcode_with_details,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scrape", tags=["scraping"])


def _scrape_postcode_properties(
    postcode: str,
    *,
    mode: str = "house_prices",
    max_properties: int = 50,
    pages: int = 1,
    link_count: Optional[int] = None,
    floorplan: bool = False,
) -> tuple[list, int]:
    """Scrape properties for a postcode using fast or slow path.

    Returns (properties, detail_pages_visited).
    """
    if mode == "for_sale":
        props = scrape_for_sale_listings(
            postcode, max_properties=max_properties, pages=pages,
        )
        return props, 0

    use_detail_pages = floorplan or link_count is not None
    if use_detail_pages:
        props = scrape_postcode_with_details(
            postcode,
            max_properties=max_properties,
            pages=pages,
            extract_floorplan=floorplan,
            link_count=link_count,
        )
        return props, len(props)
    else:
        props = scrape_postcode_from_listing(
            postcode, max_properties=max_properties, pages=pages,
        )
        return props, 0


def _normalise_price(price: str) -> str:
    """Normalise a price string to consistent '£N,NNN' format."""
    # Strip any existing £-like characters, commas, and whitespace
    cleaned = price.replace("\u00a3", "").replace("\u00c2", "").replace(",", "").strip()
    # Extract first contiguous digit sequence (commas already stripped, so "250000" matches whole)
    match = re.search(r"(\d+)", cleaned)
    if match:
        amount = int(match.group(1))
        return f"\u00a3{amount:,}"
    return price


def _is_postcode_fresh(db: Session, postcode: str, mode: str = "house_prices") -> tuple[bool, int]:
    """Check if a postcode has fresh data within the configured freshness window.

    Only considers properties relevant to the given mode:
    - house_prices: properties with sale records (ignores for-sale listings)
    - for_sale: properties with listing_status='for_sale'

    Returns (is_fresh, property_count).
    """
    from datetime import datetime, timedelta, timezone

    clean = postcode.upper().replace("-", " ").strip()
    query = db.query(Property).filter(Property.postcode == clean)

    if mode == "for_sale":
        query = query.filter(Property.listing_status == "for_sale")
    else:
        # House prices mode: only consider properties that have sales
        query = query.filter(
            (Property.listing_status.is_(None)) | (Property.listing_status != "for_sale")
        )

    props = query.all()
    if not props:
        return False, 0

    # Check the most recent update time
    latest_update = max(
        (p.updated_at for p in props if p.updated_at),
        default=None,
    )
    if latest_update is None:
        return False, len(props)

    # Make comparison timezone-aware if needed
    if latest_update.tzinfo is None:
        latest_update = latest_update.replace(tzinfo=timezone.utc)

    cutoff = datetime.now(timezone.utc) - timedelta(days=SCRAPER_FRESHNESS_DAYS)
    return latest_update >= cutoff, len(props)


def _upsert_property(db: Session, data: PropertyData) -> Property:
    """Insert or update a property and its sales in the database."""
    existing = db.query(Property).filter(Property.address == data.address).first()
    logger.debug("%s property: %s", "Updated" if existing else "Inserted", data.address)

    norm_ptype = data.property_type.upper() if data.property_type else ""

    if existing:
        prop = existing
        prop.postcode = data.postcode if data.postcode is not None else prop.postcode
        prop.property_type = norm_ptype if norm_ptype else prop.property_type
        prop.bedrooms = data.bedrooms if data.bedrooms is not None else prop.bedrooms
        prop.bathrooms = data.bathrooms if data.bathrooms is not None else prop.bathrooms
        prop.extra_features = (
            json.dumps(data.extra_features) if data.extra_features is not None else prop.extra_features
        )
        prop.floorplan_urls = (
            json.dumps(data.floorplan_urls) if data.floorplan_urls is not None else prop.floorplan_urls
        )
        prop.url = data.url if data.url is not None else prop.url
    else:
        prop = Property(
            address=data.address,
            postcode=data.postcode,
            property_type=norm_ptype,
            bedrooms=data.bedrooms,
            bathrooms=data.bathrooms,
            extra_features=json.dumps(data.extra_features) if data.extra_features is not None else None,
            floorplan_urls=json.dumps(data.floorplan_urls) if data.floorplan_urls is not None else None,
            url=data.url,
        )
        db.add(prop)

    # Populate listing fields if this is from a for-sale scrape
    if data.asking_price is not None:
        from datetime import datetime, timezone
        prop.listing_status = "for_sale"
        prop.listing_price = data.asking_price
        prop.listing_price_display = data.asking_price_display
        prop.listing_url = data.url
        prop.listing_checked_at = datetime.now(timezone.utc)

    db.flush()  # Get the property ID

    # Add sales, skipping duplicates
    for sale_data in data.sales:
        # Normalize date (strip leading zeros: "04 Nov" -> "4 Nov")
        norm_date = re.sub(r"\b0(\d)", r"\1", sale_data.date_sold)
        # Normalize price to consistent format: "£397,000"
        norm_price = _normalise_price(sale_data.price)

        exists = (
            db.query(Sale)
            .filter(
                Sale.property_id == prop.id,
                Sale.date_sold == norm_date,
                Sale.price == norm_price,
            )
            .first()
        )
        if exists:
            continue

        # Use savepoint so a constraint violation only rolls back this sale
        try:
            nested = db.begin_nested()
            sale = Sale(
                property_id=prop.id,
                date_sold=norm_date,
                price=norm_price,
                price_numeric=parse_price_to_int(norm_price),
                date_sold_iso=parse_date_to_iso(norm_date),
                price_change_pct=sale_data.price_change_pct,
                property_type=sale_data.property_type,
                tenure=sale_data.tenure.upper() if sale_data.tenure else "",
            )
            db.add(sale)
            nested.commit()
        except IntegrityError:
            nested.rollback()

    return prop


@router.post("/postcode/{postcode}", response_model=ScrapeResponse)
@limiter.limit(RATE_LIMIT_SCRAPE)
def scrape_postcode(
    request: Request,
    postcode: str,
    mode: str = Query(default="house_prices", description="Scrape mode: 'house_prices' or 'for_sale'"),
    max_properties: int = Query(default=50, ge=1, le=500),
    pages: int = Query(default=1, ge=1, le=50, description="Number of listing pages to scrape"),
    link_count: Optional[int] = Query(
        default=None, ge=0,
        description="Detail pages to visit (0 = all, None = fast mode)",
    ),
    floorplan: bool = Query(default=False, description="Extract floorplan image URLs (requires detail page visits)"),
    extra_features: bool = Query(default=False, description="Extract key features (requires detail page visits)"),
    save_parquet: bool = Query(default=False, description="Save each property to parquet as it's scraped"),
    skip_existing: bool = Query(default=True, description="Skip if postcode already has fresh data"),
    force: bool = Query(default=False, description="Force re-scrape even if data is fresh"),
    db: Session = Depends(get_db),
):
    """Scrape properties for a given postcode.

    **Modes:**
    - `house_prices` (default): Scrapes historical sale data from house prices pages.
    - `for_sale`: Scrapes properties currently listed for sale with asking prices.

    **Fast path** (default): Extracts data from listing page embedded data.
    Single HTTP request per page.

    **Slow path** (when `link_count`, `floorplan`, or `extra_features` is set):
    Visits individual detail pages for richer data including key features,
    full sale history, and optionally floorplan URLs.

    Set `skip_existing=false` or `force=true` to re-scrape postcodes that already have data.
    """
    if mode not in ("house_prices", "for_sale"):
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}'. Must be 'house_prices' or 'for_sale'.")

    # Check if we should skip this postcode
    if skip_existing and not force:
        is_fresh, prop_count = _is_postcode_fresh(db, postcode, mode)
        if is_fresh:
            logger.info("Skipping %s: already has %d properties (fresh data)", postcode, prop_count)
            return ScrapeResponse(
                message=f"Postcode {postcode} already scraped ({prop_count} properties, data is less than {SCRAPER_FRESHNESS_DAYS} days old)",
                properties_scraped=0,
                pages_scraped=0,
                detail_pages_visited=0,
                skipped=True,
                mode=mode,
            )

    t0 = time.monotonic()
    properties, detail_pages_visited = _scrape_postcode_properties(
        postcode,
        mode=mode,
        max_properties=max_properties,
        pages=pages,
        link_count=link_count if (extra_features or floorplan or link_count is not None) else None,
        floorplan=floorplan,
    )

    if not properties:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {postcode}. "
            "Check the postcode format (e.g. E1W-1AT or E1W1AT).",
        )

    scraped_count = 0
    for prop_data in properties:
        if prop_data.address:
            prop = _upsert_property(db, prop_data)
            db.flush()
            if save_parquet:
                save_property_parquet(prop)
            scraped_count += 1

    db.commit()

    elapsed = time.monotonic() - t0
    logger.info("Postcode %s scraped in %.1fs: %d properties (%s mode)", postcode, elapsed, scraped_count, mode)

    label = "for-sale listings" if mode == "for_sale" else "properties"
    return ScrapeResponse(
        message=f"Scraped {scraped_count} {label} for postcode {postcode}",
        properties_scraped=scraped_count,
        pages_scraped=pages,
        detail_pages_visited=detail_pages_visited,
        mode=mode,
    )


@router.post("/area/{partial}", response_model=AreaScrapeResponse)
@limiter.limit(RATE_LIMIT_SCRAPE)
def scrape_area(
    request: Request,
    partial: str,
    mode: str = Query(default="house_prices", description="Scrape mode: 'house_prices' or 'for_sale'"),
    pages: int = Query(default=1, ge=1, le=50),
    link_count: Optional[int] = Query(default=None, ge=0, description="Detail pages per postcode (0 = all)"),
    max_postcodes: int = Query(default=0, ge=0, description="Max postcodes to scrape (0 = all)"),
    floorplan: bool = Query(default=False, description="Extract floorplan image URLs (requires detail page visits)"),
    extra_features: bool = Query(default=False, description="Extract key features (requires detail page visits)"),
    save_parquet: bool = Query(default=False, description="Save each property to parquet as it's scraped"),
    skip_existing: bool = Query(default=True, description="Skip postcodes that already have fresh data"),
    force: bool = Query(default=False, description="Force re-scrape even if data is fresh"),
    db: Session = Depends(get_db),
):
    """Scrape all postcodes matching a partial (e.g. 'SW208N' finds SW20 8ND, SW20 8NE, ...).

    Reads postcodes from local parquet files (data/postcodes/{OUTCODE}.parquet)
    generated from the ONS Postcode Directory.

    Set `skip_existing=false` or `force=true` to re-scrape postcodes that already have data.
    """
    if mode not in ("house_prices", "for_sale"):
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}'. Must be 'house_prices' or 'for_sale'.")

    import pyarrow.parquet as pq

    partial_clean = partial.upper().replace("-", "").replace(" ", "")

    # Step 1: discover postcodes from local parquet files
    parquet_dir = DATA_DIR / "postcodes"

    # Accept letter-only area prefixes (e.g. "SW") or full/partial outcodes (e.g. "SW20", "SE17G")
    if not re.match(r"[A-Z]{1,2}", partial_clean):
        raise HTTPException(status_code=400, detail=f"Invalid postcode format: '{partial}'")

    all_postcodes: list[str] = []
    letters_only = re.match(r"^[A-Z]{1,2}$", partial_clean)

    if letters_only:
        # Area prefix like "SW" — glob all matching parquet files (SW1A, SW2, SW20, etc.)
        matching_files = sorted(parquet_dir.glob(f"{partial_clean}*.parquet"))
        for pf in matching_files:
            table = pq.read_table(pf, columns=["postcode"])
            all_postcodes.extend(table.column("postcode").to_pylist())
        all_postcodes.sort()
    else:
        # Has digits — try candidate outcodes from longest to shortest
        # e.g. "SE17G" could be outcode SE17 + incode G*, or SE1 + incode 7G*
        outcode_match = re.match(r"([A-Z]{1,2}\d[A-Z\d]?)", partial_clean)
        if not outcode_match:
            raise HTTPException(status_code=400, detail=f"Invalid postcode format: '{partial}'")

        longest = outcode_match.group(1)
        candidates = [longest]
        if len(longest) > 2:
            shorter = re.match(r"([A-Z]{1,2}\d)", partial_clean)
            if shorter and shorter.group(1) != longest:
                candidates.append(shorter.group(1))

        for outcode in candidates:
            parquet_path = parquet_dir / f"{outcode}.parquet"
            if not parquet_path.exists():
                continue
            table = pq.read_table(parquet_path, columns=["postcode"])
            raw = table.column("postcode").to_pylist()
            matches = sorted(pc for pc in raw if pc.replace(" ", "").startswith(partial_clean))
            if matches:
                all_postcodes = matches
                break

    if not all_postcodes:
        raise HTTPException(
            status_code=404,
            detail=f"No postcodes found matching '{partial}'.",
        )

    postcodes = all_postcodes if max_postcodes == 0 else all_postcodes[:max_postcodes]
    logger.info("Area scrape: found %d postcodes for '%s', scraping %d", len(all_postcodes), partial, len(postcodes))

    # --- For-sale mode: scrape each unique outcode once ---
    if mode == "for_sale":
        # Derive unique outcodes from the matched postcodes
        seen_outcodes: list[str] = []
        for pc in postcodes:
            oc = pc.replace(" ", "")[:-3] if len(pc.replace(" ", "")) >= 5 else pc.replace(" ", "")
            if oc not in seen_outcodes:
                seen_outcodes.append(oc)

        total_count = 0
        scraped_ocs: list[str] = []
        failed_ocs: list[str] = []
        for outcode in seen_outcodes:
            logger.info("Area scrape (for_sale): scraping outcode %s", outcode)
            try:
                properties, _ = _scrape_postcode_properties(
                    outcode, mode="for_sale", max_properties=500, pages=pages,
                )
                count = 0
                for prop_data in properties:
                    if prop_data.address:
                        prop = _upsert_property(db, prop_data)
                        db.flush()
                        if save_parquet:
                            save_property_parquet(prop)
                        count += 1
                db.commit()
                total_count += count
                scraped_ocs.append(outcode)
            except Exception as e:
                logger.error("Error scraping for-sale %s: %s", outcode, e, exc_info=True)
                db.rollback()
                failed_ocs.append(outcode)

        msg = f"Scraped {total_count} for-sale listings across {len(scraped_ocs)} outcodes"
        if failed_ocs:
            msg += f" ({len(failed_ocs)} failed)"
        return AreaScrapeResponse(
            message=msg,
            postcodes_scraped=scraped_ocs,
            postcodes_skipped=[],
            postcodes_failed=failed_ocs,
            total_properties=total_count,
        )

    # --- House prices mode: per-outcode phased approach ---
    # Groups postcodes by outcode (e.g. E1, E2, SW1, SW20), then for each:
    #   Phase 1: Collect detail URLs (fast, listing pages only)
    #   Phase 2: Blast detail pages concurrently with the full pool
    # This gives DB writes after each outcode instead of waiting for everything.
    t0 = time.monotonic()
    total = 0
    use_detail_pages = floorplan or extra_features or link_count is not None
    scraped_postcodes: list[str] = []
    skipped_postcodes: list[str] = []
    failed_postcodes: list[str] = []

    # Group postcodes by outcode (e.g. "SW20 8NE" -> "SW20", "E1 6AA" -> "E1")
    outcode_groups: dict[str, list[str]] = {}
    for pc in postcodes:
        clean = pc.replace(" ", "")
        oc = clean[:-3] if len(clean) >= 5 else clean
        outcode_groups.setdefault(oc, []).append(pc)

    sorted_outcodes = sorted(outcode_groups.keys())
    logger.info("Area scrape: %d outcodes to process for '%s'", len(sorted_outcodes), partial)

    for oc_idx, outcode in enumerate(sorted_outcodes, 1):
        oc_postcodes = outcode_groups[outcode]

        # Filter fresh/stale for this outcode
        oc_to_scrape: list[str] = []
        for pc in oc_postcodes:
            if skip_existing and not force:
                is_fresh, prop_count = _is_postcode_fresh(db, pc, mode)
                if is_fresh:
                    skipped_postcodes.append(pc)
                    continue
            oc_to_scrape.append(pc)

        if not oc_to_scrape:
            logger.info("Outcode %s: all %d postcodes fresh, skipping (%d/%d outcodes)",
                         outcode, len(oc_postcodes), oc_idx, len(sorted_outcodes))
            continue

        if not use_detail_pages:
            # Fast path: listing data only
            def _scrape_listing(pc: str) -> tuple[str, list]:
                pc_norm = normalise_postcode_for_url(pc)
                props = scrape_postcode_from_listing(pc_norm, max_properties=50, pages=pages)
                return pc, props

            with ThreadPoolExecutor(max_workers=min(10, _MW)) as listing_pool:
                futs = {listing_pool.submit(_scrape_listing, pc): pc for pc in oc_to_scrape}
                for fut in as_completed(futs):
                    pc = futs[fut]
                    try:
                        pc, properties = fut.result()
                        count = 0
                        for prop_data in properties:
                            if prop_data.address:
                                _upsert_property(db, prop_data)
                                count += 1
                        db.commit()
                        total += count
                        scraped_postcodes.append(pc)
                    except Exception as e:
                        logger.error("Error scraping %s: %s", pc, e, exc_info=True)
                        db.rollback()
                        failed_postcodes.append(pc)

            logger.info("Outcode %s: %d properties (%d/%d outcodes, %d total)",
                         outcode, total, oc_idx, len(sorted_outcodes), total)
        else:
            # Phase 1: Collect URLs for this outcode
            url_to_pc: dict[str, str] = {}

            def _collect_urls(pc: str) -> tuple[str, list[str]]:
                pc_norm = normalise_postcode_for_url(pc)
                max_props = 500 if link_count == 0 else 50
                urls = get_postcode_page_urls(pc_norm, max_properties=max_props, pages=pages)
                if link_count is not None and link_count > 0:
                    urls = urls[:link_count]
                return pc, urls

            with ThreadPoolExecutor(max_workers=min(10, _MW)) as url_pool:
                url_futs = {url_pool.submit(_collect_urls, pc): pc for pc in oc_to_scrape}
                for fut in as_completed(url_futs):
                    pc = url_futs[fut]
                    try:
                        pc, urls = fut.result()
                        if urls:
                            for u in urls:
                                url_to_pc[u] = pc
                        else:
                            scraped_postcodes.append(pc)
                    except Exception as e:
                        logger.error("Phase 1 %s: error for %s: %s", outcode, pc, e)
                        failed_postcodes.append(pc)

            logger.info("Outcode %s Phase 1: %d URLs from %d postcodes (%d/%d outcodes)",
                         outcode, len(url_to_pc), len(oc_to_scrape), oc_idx, len(sorted_outcodes))

            # Phase 2: Blast detail pages for this outcode
            detail_futs = {
                _detail_pool.submit(get_single_house_details, url, floorplan): url
                for url in url_to_pc
            }
            batch_count = 0
            oc_count = 0
            for fut in as_completed(detail_futs):
                url = detail_futs[fut]
                try:
                    prop = fut.result()
                    if prop and prop.address:
                        try:
                            db_prop = _upsert_property(db, prop)
                            if save_parquet:
                                save_property_parquet(db_prop)
                            total += 1
                            oc_count += 1
                            batch_count += 1
                            if batch_count >= 50:
                                db.commit()
                                batch_count = 0
                        except Exception as e:
                            logger.error("DB upsert failed for %s: %s", prop.address, e)
                            db.rollback()
                except Exception as e:
                    logger.warning("Detail page failed for %s: %s", url, e)

            if batch_count > 0:
                db.commit()

            # Mark this outcode's postcodes as scraped
            for pc in oc_to_scrape:
                if pc not in failed_postcodes and pc not in scraped_postcodes:
                    scraped_postcodes.append(pc)

            logger.info("Outcode %s Phase 2: %d properties saved (%d/%d outcodes, %d total)",
                         outcode, oc_count, oc_idx, len(sorted_outcodes), total)

    elapsed = time.monotonic() - t0
    logger.info("Area '%s' completed in %.1fs: %d properties, %d scraped, %d skipped, %d failed",
                partial, elapsed, total, len(scraped_postcodes), len(skipped_postcodes), len(failed_postcodes))

    msg = f"Scraped {total} properties across {len(scraped_postcodes)}/{len(all_postcodes)} postcodes for '{partial}'"
    if skipped_postcodes:
        msg += f" ({len(skipped_postcodes)} skipped — already fresh)"
    if failed_postcodes:
        msg += f" ({len(failed_postcodes)} failed)"

    return AreaScrapeResponse(
        message=msg,
        postcodes_scraped=scraped_postcodes,
        postcodes_skipped=skipped_postcodes,
        postcodes_failed=failed_postcodes,
        total_properties=total,
    )


@router.post("/property", response_model=ScrapePropertyResponse)
@limiter.limit(RATE_LIMIT_SCRAPE)
def scrape_single_property(
    request: Request,
    body: ScrapeUrlRequest,
    db: Session = Depends(get_db),
):
    """Scrape a single property by its URL."""
    parsed = urlparse(body.url)
    if not parsed.hostname or not parsed.hostname.endswith("rightmove.co.uk"):
        raise HTTPException(
            status_code=400,
            detail="URL must be a valid property source URL.",
        )

    data = get_single_house_details(body.url, extract_floorplan=body.floorplan)
    if not data or not data.address:
        raise HTTPException(
            status_code=404,
            detail="Could not extract property data from the given URL.",
        )

    prop = _upsert_property(db, data)
    db.commit()
    db.refresh(prop)

    return ScrapePropertyResponse(
        message=f"Scraped property: {data.address}",
        property=prop,
    )
