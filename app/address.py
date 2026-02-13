"""Address normalization for cross-source deduplication.

Builds a canonical key from address components so that the same property
imported from Land Registry and scraped from Rightmove produces an identical
key, enabling JOIN-based matching.

Key format: ``{SAON}|{PAON}|{STREET}|{POSTCODE}`` (uppercase, no-space postcode).
"""

import re
from typing import Optional


def normalise_address_key(
    paon: str,
    street: str,
    postcode: str,
    saon: str = "",
) -> str:
    """Build a canonical address key from Land Registry fields.

    Parameters
    ----------
    paon : str
        Primary Addressable Object Name (house number / name).
    street : str
        Street name.
    postcode : str
        Full postcode (spaces are stripped).
    saon : str, optional
        Secondary Addressable Object Name (flat number, etc.).

    Returns
    -------
    str
        Key like ``FLAT 1|22|HIGH STREET|SW200AF``.
    """
    parts = [
        saon.strip().upper(),
        paon.strip().upper(),
        street.strip().upper(),
        postcode.strip().upper().replace(" ", ""),
    ]
    return "|".join(parts)


def parse_rightmove_address_key(address: str) -> Optional[str]:
    """Extract a canonical address key from a Rightmove address string.

    Rightmove addresses look like:
        ``1, Atkinson Close, London SW20 0AF``
        ``Flat 3, 22 High Street, Wimbledon, London SW19 1AB``

    The postcode is always the last token.  The PAON (house number or name)
    is the first comma-separated segment.  The street is the second segment.
    We skip locality / town segments.

    Returns None if the address cannot be parsed.
    """
    if not address:
        return None

    # Extract postcode from end of string
    # UK postcode: A9 9AA | A99 9AA | A9A 9AA | AA9 9AA | AA99 9AA | AA9A 9AA
    pc_match = re.search(
        r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$",
        address.strip().upper(),
    )
    if not pc_match:
        return None

    postcode = pc_match.group(1).replace(" ", "")

    # Remove the postcode from the end to parse the rest
    before_pc = address[: pc_match.start()].strip().rstrip(",").strip()

    # Split on commas
    segments = [s.strip() for s in before_pc.split(",") if s.strip()]
    if not segments:
        return None

    # Detect if first segment is a SAON (flat/apartment) by checking if
    # the second segment starts with a number (the PAON).
    saon = ""
    paon = ""
    street = ""

    if len(segments) >= 3:
        # Could be: "Flat 3", "22 High Street", "Wimbledon", "London"
        # Or: "22", "High Street", "London"
        first_upper = segments[0].upper()
        if re.match(r"(FLAT|APARTMENT|UNIT|ROOM)\b", first_upper):
            saon = segments[0].upper()
            # Second segment may be "22 High Street" or just "22"
            paon_street = segments[1].strip()
            paon_match = re.match(r"^(\d+\w?)\b\s*(.*)", paon_street)
            if paon_match:
                paon = paon_match.group(1).upper()
                street = paon_match.group(2).upper()
            else:
                paon = paon_street.upper()
        else:
            # First segment is likely PAON or "PAON STREET"
            paon_match = re.match(r"^(\d+\w?)\b\s*(.*)", first_upper)
            if paon_match and not paon_match.group(2):
                # Just a number like "22" — next segment is the street
                paon = paon_match.group(1)
                street = segments[1].upper() if len(segments) > 1 else ""
            elif paon_match and paon_match.group(2):
                # "22 High Street"
                paon = paon_match.group(1)
                street = paon_match.group(2)
            else:
                # Named house: "The Willows", next is street
                paon = first_upper
                street = segments[1].upper() if len(segments) > 1 else ""
    elif len(segments) == 2:
        # "1", "Atkinson Close" or "1 Atkinson Close", "London"
        first_upper = segments[0].upper()
        paon_match = re.match(r"^(\d+\w?)\b\s*(.*)", first_upper)
        if paon_match and not paon_match.group(2):
            paon = paon_match.group(1)
            street = segments[1].upper()
        elif paon_match and paon_match.group(2):
            paon = paon_match.group(1)
            street = paon_match.group(2)
        else:
            paon = first_upper
            street = segments[1].upper()
    elif len(segments) == 1:
        # "1 Atkinson Close"
        first_upper = segments[0].upper()
        paon_match = re.match(r"^(\d+\w?)\b\s+(.*)", first_upper)
        if paon_match:
            paon = paon_match.group(1)
            street = paon_match.group(2)
        else:
            paon = first_upper

    # Clean up street — remove trailing locality/town words that slipped in
    # (shouldn't happen with comma splitting, but be safe)
    street = street.strip()

    return normalise_address_key(paon, street, postcode, saon)
