import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ..config import (
    SCRAPER_DELAY_BETWEEN_REQUESTS,
    SCRAPER_REQUEST_TIMEOUT,
    SCRAPER_RETRY_ATTEMPTS,
    SCRAPER_RETRY_BACKOFF,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}

BASE_URL = "https://www.rightmove.co.uk"
POSTCODE_PATTERN = r"(?:[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})"


def _request_with_retry(url: str, **kwargs) -> Optional[requests.Response]:
    """Make an HTTP GET request with exponential backoff retry logic."""
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", SCRAPER_REQUEST_TIMEOUT)

    for attempt in range(1, SCRAPER_RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, **kwargs)
            if resp.status_code == 429:
                wait = SCRAPER_RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning("Rate limited (429) on %s, waiting %.1fs (attempt %d/%d)",
                               url, wait, attempt, SCRAPER_RETRY_ATTEMPTS)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < SCRAPER_RETRY_ATTEMPTS:
                wait = SCRAPER_RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning("Request failed for %s: %s. Retrying in %.1fs (attempt %d/%d)",
                               url, e, wait, attempt, SCRAPER_RETRY_ATTEMPTS)
                time.sleep(wait)
            else:
                logger.error("Request failed for %s after %d attempts: %s",
                             url, SCRAPER_RETRY_ATTEMPTS, e)
    return None


@dataclass
class SaleRecord:
    date_sold: str = ""
    price: str = ""
    price_change_pct: str = ""
    property_type: str = ""
    tenure: str = ""


@dataclass
class PropertyData:
    address: str = ""
    postcode: str = ""
    property_type: str = ""
    bedrooms: int = 0
    bathrooms: int = 0
    extra_features: list[str] = field(default_factory=list)
    floorplan_urls: list[str] = field(default_factory=list)
    url: str = ""
    sales: list[SaleRecord] = field(default_factory=list)


def extract_postcode(address: str) -> str:
    """Extract a UK postcode from an address string."""
    match = re.search(POSTCODE_PATTERN, address, re.IGNORECASE)
    return match.group(0).strip().upper() if match else ""


def normalise_postcode_for_url(postcode: str) -> str:
    """Convert a postcode like 'AB10 1AA' or 'AB10-1AA' to 'AB101AA' for Rightmove URLs."""
    return re.sub(r"[\s\-]", "", postcode.upper())


# ---------------------------------------------------------------------------
# React Router Turbo Stream parser
# ---------------------------------------------------------------------------

def _parse_turbo_stream(html: str) -> Optional[list]:
    """Extract the main data array from React Router's Turbo Stream format.

    Rightmove uses React Router v7 which embeds route loader data in
    window.__reactRouterContext.streamController.enqueue() calls. The main
    data chunk is a JSON array (not P-prefixed) with 50+ elements.
    """
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        text = script.string or ""
        matches = re.findall(
            r'streamController\.enqueue\("(.+?)"\)', text, re.DOTALL
        )
        for m in matches:
            # Decode JS string escaping via json.loads (handles UTF-8 properly,
            # unlike unicode_escape which corrupts multi-byte chars like £)
            try:
                unescaped = json.loads('"' + m + '"')
            except (json.JSONDecodeError, ValueError):
                unescaped = m

            # Skip promise-resolution chunks (P123:...)
            if unescaped.startswith("P"):
                continue

            try:
                flat = json.loads(unescaped)
            except (json.JSONDecodeError, ValueError):
                continue

            if isinstance(flat, list) and len(flat) > 50:
                return flat

    return None


def _resolve_ref(flat: list, ref_val):
    """Resolve a single Turbo Stream reference value."""
    if ref_val == -5 or ref_val == -6:
        return None
    if isinstance(ref_val, bool):
        return ref_val
    if isinstance(ref_val, int) and 0 <= ref_val < len(flat):
        return flat[ref_val]
    return ref_val


def _resolve_object(flat: list, obj: dict) -> dict:
    """Resolve a Turbo Stream object with _N keys into a regular dict."""
    result = {}
    for ref_key, ref_val in obj.items():
        key_idx = int(ref_key.lstrip("_"))
        key_name = flat[key_idx] if key_idx < len(flat) and isinstance(flat[key_idx], str) else ref_key

        raw = _resolve_ref(flat, ref_val)
        if isinstance(raw, dict):
            result[key_name] = _resolve_object(flat, raw)
        elif isinstance(raw, list):
            result[key_name] = _resolve_list(flat, raw)
        else:
            result[key_name] = raw
    return result


def _resolve_list(flat: list, lst: list) -> list:
    """Resolve a Turbo Stream list of references."""
    result = []
    for item in lst:
        raw = _resolve_ref(flat, item)
        if isinstance(raw, dict):
            result.append(_resolve_object(flat, raw))
        elif isinstance(raw, list):
            result.append(_resolve_list(flat, raw))
        else:
            result.append(raw)
    return result


# ---------------------------------------------------------------------------
# Postcode listing page
# ---------------------------------------------------------------------------

def _extract_urls_from_stream(flat: list, max_items: int) -> list[str]:
    """Extract property detail URLs from a parsed turbo stream flat array."""
    detail_urls: list[str] = []
    for i, item in enumerate(flat):
        if item == "properties" and i + 1 < len(flat):
            prop_refs = flat[i + 1]
            if not isinstance(prop_refs, list):
                break
            for ref in prop_refs:
                raw = _resolve_ref(flat, ref)
                if isinstance(raw, dict):
                    prop = _resolve_object(flat, raw)
                    detail_url = prop.get("detailUrl", "")
                    if detail_url:
                        if not detail_url.startswith("http"):
                            detail_url = BASE_URL + detail_url
                        detail_urls.append(detail_url)
                        if len(detail_urls) >= max_items:
                            break
            break
    return detail_urls


def _extract_properties_from_stream(
    flat: list, postcode: str, max_items: int,
) -> list[PropertyData]:
    """Extract PropertyData objects from a parsed turbo stream flat array."""
    properties: list[PropertyData] = []
    for i, item in enumerate(flat):
        if item == "properties" and i + 1 < len(flat):
            prop_refs = flat[i + 1]
            if not isinstance(prop_refs, list):
                break
            for ref in prop_refs:
                raw = _resolve_ref(flat, ref)
                if not isinstance(raw, dict):
                    continue
                prop_dict = _resolve_object(flat, raw)
                prop_data = _listing_dict_to_property(prop_dict, postcode)
                if prop_data:
                    properties.append(prop_data)
                if len(properties) >= max_items:
                    break
            break
    return properties


def _fetch_listing_page(normalised: str, page: int) -> Optional[list]:
    """Fetch a single listing page and return the parsed turbo stream data."""
    url = f"{BASE_URL}/house-prices/{normalised}.html"
    if page > 1:
        url += f"?page={page}"
    logger.info("Fetching listing page: %s", url)

    resp = _request_with_retry(url)
    if resp is None:
        return None

    return _parse_turbo_stream(resp.text)


def get_postcode_page_urls(
    postcode: str, max_properties: int = 50, pages: int = 1,
) -> list[str]:
    """Fetch property detail URLs for a postcode from Rightmove house prices.

    Parses the React Router Turbo Stream data embedded in the page HTML
    to extract property detail URLs. Supports multi-page pagination.
    """
    normalised = normalise_postcode_for_url(postcode)
    all_urls: list[str] = []

    for page in range(1, pages + 1):
        flat = _fetch_listing_page(normalised, page)
        if flat is None:
            break

        remaining = max_properties - len(all_urls)
        page_urls = _extract_urls_from_stream(flat, remaining)
        if not page_urls:
            break
        all_urls.extend(page_urls)
        if len(all_urls) >= max_properties:
            break

    logger.info("Found %d property links for postcode %s", len(all_urls), postcode)
    return all_urls


def scrape_postcode_from_listing(
    postcode: str, max_properties: int = 50, pages: int = 1,
) -> list[PropertyData]:
    """Scrape property data directly from the postcode listing page.

    This extracts basic property info and latest transaction from the listing
    page's Turbo Stream data, avoiding the need to visit each detail page.
    Supports multi-page pagination.
    """
    normalised = normalise_postcode_for_url(postcode)
    all_properties: list[PropertyData] = []

    for page in range(1, pages + 1):
        flat = _fetch_listing_page(normalised, page)
        if flat is None:
            break

        remaining = max_properties - len(all_properties)
        page_props = _extract_properties_from_stream(flat, postcode, remaining)
        if not page_props:
            break
        all_properties.extend(page_props)
        if len(all_properties) >= max_properties:
            break

    logger.info(
        "Extracted %d properties from %d page(s) for postcode %s",
        len(all_properties),
        min(pages, len(all_properties) or 1),
        postcode,
    )
    return all_properties


def _listing_dict_to_property(d: dict, postcode: str) -> Optional[PropertyData]:
    """Convert a resolved listing property dict into a PropertyData."""
    address = d.get("address", "")
    if not address:
        return None

    detail_url = d.get("detailUrl", "")
    if detail_url and not detail_url.startswith("http"):
        detail_url = BASE_URL + detail_url

    prop = PropertyData(
        address=address,
        postcode=extract_postcode(address),
        property_type=d.get("propertyType") or "",
        bedrooms=d.get("bedrooms") or 0,
        bathrooms=d.get("bathrooms") or 0,
        url=detail_url,
    )

    # If no postcode extracted from address, use the one provided
    if not prop.postcode:
        clean = normalise_postcode_for_url(postcode)
        if len(clean) >= 5:
            prop.postcode = clean[:-3] + " " + clean[-3:]
        else:
            prop.postcode = clean

    # Extract transactions from listing data
    transactions = d.get("transactions", [])
    if isinstance(transactions, list):
        for txn in transactions:
            if isinstance(txn, dict):
                sale = SaleRecord(
                    date_sold=str(txn.get("dateSold", "")),
                    price=_format_price(txn.get("price", txn.get("displayPrice"))),
                    price_change_pct=str(txn.get("priceChangePercentage", txn.get("priceChange", "")) or ""),
                    property_type=str(txn.get("propertyType", "") or ""),
                    tenure=str(txn.get("tenure", "") or ""),
                )
                if sale.date_sold or sale.price:
                    prop.sales.append(sale)

    # Also check latestTransaction if transactions was empty
    if not prop.sales:
        latest = d.get("latestTransaction")
        if isinstance(latest, dict):
            sale = SaleRecord(
                date_sold=str(latest.get("dateSold", "")),
                price=_format_price(latest.get("price", latest.get("displayPrice"))),
                tenure=str(latest.get("tenure", "") or ""),
            )
            if sale.date_sold or sale.price:
                prop.sales.append(sale)

    return prop


def _format_price(price) -> str:
    """Format a price value (could be int or string) to a display string."""
    if price is None:
        return ""
    if isinstance(price, (int, float)):
        return f"\u00a3{price:,.0f}"
    return str(price)


# ---------------------------------------------------------------------------
# Single property detail page
# ---------------------------------------------------------------------------

def get_single_house_details(
    url: str, extract_floorplan: bool = False,
) -> Optional[PropertyData]:
    """Scrape details for a single property from its Rightmove detail page.

    Uses the HTML table for sale history and Turbo Stream data for property
    attributes. Optionally extracts floorplan image URLs.
    """
    logger.info("Scraping property: %s", url)

    resp = _request_with_retry(url)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    prop = PropertyData(url=url)

    # 1. Address from <h1>
    h1 = soup.find("h1")
    if h1:
        prop.address = h1.get_text(strip=True)

    # 2. Sales history from HTML table
    # Columns: Date sold | Price change % | Price | Tenure
    prop.sales = _extract_sales_from_table(soup)

    # 3. Property details from Turbo Stream data
    flat = _parse_turbo_stream(resp.text)
    if flat:
        _extract_detail_from_stream(flat, prop)

    # 4. Key features from HTML (h2 "Key features" + sibling ul)
    _extract_key_features(soup, prop)

    # 5. Property details from dt/dd pairs as fallback
    if not prop.bedrooms and not prop.bathrooms:
        _extract_details_from_dt_dd(soup, prop)

    # 6. Floorplan URLs (optional)
    if extract_floorplan:
        prop.floorplan_urls = extract_floorplan_urls(soup, flat)

    # Extract postcode from address
    if not prop.postcode and prop.address:
        prop.postcode = extract_postcode(prop.address)

    if not prop.address and not prop.sales:
        logger.warning("Could not extract any data from %s", url)
        return None

    return prop


def _extract_sales_from_table(soup: BeautifulSoup) -> list[SaleRecord]:
    """Extract sale history from the HTML table.

    Rightmove detail pages have tables with either 4 or 5 columns:
    5-col: Date sold | Price change % | Price | Property | Tenure
    4-col: Date sold | Price change % | Price | Tenure
    """
    sales: list[SaleRecord] = []
    tables = soup.find_all("table")
    if not tables:
        return sales

    table = tables[0]
    rows = table.find_all("tr")
    if not rows:
        return sales

    # Detect column count from header row
    header_cells = rows[0].find_all(["th", "td"])
    num_cols = len(header_cells)
    has_property_col = num_cols >= 5

    for row in rows[1:]:  # Skip header row
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        if has_property_col and len(cells) >= 5:
            # 5-col: Date sold | Price change % | Price | Property | Tenure
            sale = SaleRecord(
                date_sold=cells[0].get_text(strip=True),
                price_change_pct=cells[1].get_text(strip=True),
                price=cells[2].get_text(strip=True),
                property_type=cells[3].get_text(strip=True),
                tenure=cells[4].get_text(strip=True),
            )
        else:
            # 4-col: Date sold | Price change % | Price | Tenure
            sale = SaleRecord(
                date_sold=cells[0].get_text(strip=True),
                price_change_pct=cells[1].get_text(strip=True),
                price=cells[2].get_text(strip=True),
                tenure=cells[3].get_text(strip=True) if len(cells) > 3 else "",
            )

        if sale.date_sold or sale.price:
            sales.append(sale)

    return sales


def _extract_detail_from_stream(flat: list, prop: PropertyData) -> None:
    """Extract property attributes from the detail page's Turbo Stream data."""
    # Find key fields by scanning for their string names
    for i, item in enumerate(flat):
        if not isinstance(item, str) or i + 1 >= len(flat):
            continue

        next_val = flat[i + 1]

        if item == "address" and not prop.address:
            if isinstance(next_val, str):
                prop.address = next_val
            elif isinstance(next_val, dict):
                resolved = _resolve_object(flat, next_val)
                # Address might be nested
                prop.address = resolved.get("displayAddress", str(resolved))

        elif item == "propertyType" and not prop.property_type:
            if isinstance(next_val, str) and next_val not in ("propertyLinkable",):
                prop.property_type = next_val

        elif item == "bedrooms" and not prop.bedrooms:
            if isinstance(next_val, int) and next_val > 0:
                prop.bedrooms = next_val

        elif item == "bathrooms" and not prop.bathrooms and isinstance(next_val, int) and next_val > 0:
            prop.bathrooms = next_val

    # If we still don't have sales, try extracting transactions from stream
    if not prop.sales:
        for i, item in enumerate(flat):
            if item == "transactions" and i + 1 < len(flat):
                txn_refs = flat[i + 1]
                if isinstance(txn_refs, list):
                    resolved = _resolve_list(flat, txn_refs)
                    for txn in resolved:
                        if isinstance(txn, dict):
                            sale = SaleRecord(
                                date_sold=str(txn.get("dateSold", "")),
                                price=_format_price(
                                    txn.get("price", txn.get("displayPrice"))
                                ),
                                tenure=str(txn.get("tenure", "") or ""),
                            )
                            if sale.date_sold or sale.price:
                                prop.sales.append(sale)
                break


def _extract_key_features(soup: BeautifulSoup, prop: PropertyData) -> None:
    """Extract key features from h2 'Key features' + sibling ul."""
    for h2 in soup.find_all("h2"):
        if "key features" in h2.get_text(strip=True).lower():
            sibling_ul = h2.find_next_sibling("ul")
            if sibling_ul:
                prop.extra_features = [
                    li.get_text(strip=True)
                    for li in sibling_ul.find_all("li")
                    if li.get_text(strip=True)
                ]
            break


def _extract_details_from_dt_dd(soup: BeautifulSoup, prop: PropertyData) -> None:
    """Extract property details from dt/dd pairs (fallback)."""
    dt_tags = soup.find_all("dt")
    dd_tags = soup.find_all("dd")

    for dt, dd in zip(dt_tags, dd_tags):
        key = dt.get_text(strip=True).lower()
        value = dd.get_text(strip=True)

        if "bedroom" in key:
            num = re.search(r"(\d+)", value)
            if num:
                prop.bedrooms = int(num.group(1))
        elif "bathroom" in key:
            num = re.search(r"(\d+)", value)
            if num:
                prop.bathrooms = int(num.group(1))
        elif "property type" in key or key == "type":
            prop.property_type = value


# ---------------------------------------------------------------------------
# Floorplan extraction
# ---------------------------------------------------------------------------

def _extract_floorplan_urls_from_stream(flat: Optional[list]) -> list[str]:
    """Scan turbo stream data for floorplan image URLs."""
    if not flat:
        return []

    urls: list[str] = []
    for i, item in enumerate(flat):
        if not isinstance(item, str):
            continue
        # Look for keys that indicate floorplan data
        if "floorplan" in item.lower() and i + 1 < len(flat):
            # The next value might be a URL string, a list of URLs, or an object
            next_val = flat[i + 1]
            if isinstance(next_val, str) and (
                next_val.startswith("http") or next_val.startswith("/")
            ):
                urls.append(next_val)
            elif isinstance(next_val, list):
                resolved = _resolve_list(flat, next_val)
                for v in resolved:
                    if isinstance(v, str) and (
                        v.startswith("http") or v.startswith("/")
                    ):
                        urls.append(v)
                    elif isinstance(v, dict):
                        # Might have url/src keys
                        for k in ("url", "src", "href", "imageUrl"):
                            u = v.get(k, "")
                            if u and isinstance(u, str):
                                urls.append(u)
            elif isinstance(next_val, dict):
                resolved = _resolve_object(flat, next_val)
                for k in ("url", "src", "href", "imageUrl"):
                    u = resolved.get(k, "")
                    if u and isinstance(u, str):
                        urls.append(u)
        # Also catch direct URL strings containing "floorplan"
        if isinstance(item, str) and "floorplan" in item.lower() and (
            item.startswith("http") or item.startswith("/")
        ):
            urls.append(item)

    return urls


def _extract_floorplan_urls_from_html(soup: BeautifulSoup) -> list[str]:
    """Find floorplan image URLs from HTML img tags and links."""
    urls: list[str] = []

    # Look for img tags with floorplan in alt, class, or data attributes
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").lower()
        cls = " ".join(img.get("class") or []).lower()
        src = img.get("src") or ""

        if ("floorplan" in alt or "floorplan" in cls or "floorplan" in src.lower()) and src:
            urls.append(src)

    # Look for links to floorplan images
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True).lower()
        if "floorplan" in text or "floorplan" in href.lower():
            # Check if href points to an image
            if any(href.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
                urls.append(href)
            # Check for img inside the link
            inner_img = a_tag.find("img")
            if inner_img and inner_img.get("src"):
                urls.append(inner_img["src"])

    return urls


def extract_floorplan_urls(
    soup: BeautifulSoup, flat: Optional[list],
) -> list[str]:
    """Extract floorplan URLs from stream data with HTML fallback. Deduplicates."""
    urls = _extract_floorplan_urls_from_stream(flat)
    urls.extend(_extract_floorplan_urls_from_html(soup))

    # Deduplicate while preserving order
    seen = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# ---------------------------------------------------------------------------
# Postcode scrape with detail pages (slow path)
# ---------------------------------------------------------------------------

def scrape_postcode_with_details(
    postcode: str,
    max_properties: int = 50,
    pages: int = 1,
    extract_floorplan: bool = False,
    link_count: Optional[int] = None,
) -> list[PropertyData]:
    """Scrape a postcode by visiting individual detail pages for richer data.

    Fetches property URLs from listing pages, then visits each detail page.
    Use this when floorplan extraction or full detail data is needed.
    """
    urls = get_postcode_page_urls(postcode, max_properties=max_properties, pages=pages)

    if link_count is not None and link_count > 0:
        urls = urls[:link_count]

    properties: list[PropertyData] = []
    for i, url in enumerate(urls):
        if i > 0 and SCRAPER_DELAY_BETWEEN_REQUESTS > 0:
            time.sleep(SCRAPER_DELAY_BETWEEN_REQUESTS)
        prop = get_single_house_details(url, extract_floorplan=extract_floorplan)
        if prop:
            properties.append(prop)

    logger.info(
        "Scraped %d properties from %d detail pages for postcode %s",
        len(properties),
        len(urls),
        postcode,
    )
    return properties
