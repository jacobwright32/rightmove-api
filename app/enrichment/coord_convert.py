"""Pure Python conversion from British National Grid (OSGB36) to WGS84.

Uses the Helmert 7-parameter transformation via transverse Mercator projection.
Accuracy: ~5m, sufficient for distance calculations.
No external dependencies (no pyproj).
"""

import math

# Airy 1830 ellipsoid (OSGB36)
_AIRY_A = 6377563.396  # semi-major axis
_AIRY_B = 6356256.909  # semi-minor axis
_AIRY_E2 = 1 - (_AIRY_B ** 2) / (_AIRY_A ** 2)

# National Grid projection constants
_N0 = -100000.0  # northing of true origin
_E0 = 400000.0   # easting of true origin
_F0 = 0.9996012717  # scale factor on central meridian
_PHI0 = math.radians(49.0)  # latitude of true origin
_LAMBDA0 = math.radians(-2.0)  # longitude of true origin

# GRS80 ellipsoid (WGS84)
_GRS80_A = 6378137.0
_GRS80_B = 6356752.3141

# Helmert parameters: OSGB36 -> WGS84
_TX = 446.448
_TY = -125.157
_TZ = 542.060
_S = -20.4894e-6  # scale (ppm)
_RX = math.radians(0.1502 / 3600)
_RY = math.radians(0.2470 / 3600)
_RZ = math.radians(0.8421 / 3600)


def _meridional_arc(phi, phi0, a, b):
    """Compute meridional arc distance from phi0 to phi."""
    n = (a - b) / (a + b)
    n2 = n * n
    n3 = n2 * n

    dphi = phi - phi0
    sphi = phi + phi0

    ma = (1 + n + (5.0 / 4.0) * n2 + (5.0 / 4.0) * n3) * dphi
    mb = (3 * n + 3 * n2 + (21.0 / 8.0) * n3) * math.sin(dphi) * math.cos(sphi)
    mc = ((15.0 / 8.0) * n2 + (15.0 / 8.0) * n3) * math.sin(2 * dphi) * math.cos(2 * sphi)
    md = (35.0 / 24.0) * n3 * math.sin(3 * dphi) * math.cos(3 * sphi)

    return b * _F0 * (ma - mb + mc - md)


def _bng_to_osgb36(easting, northing):
    """Convert BNG easting/northing to OSGB36 lat/lon in radians."""
    a, b = _AIRY_A, _AIRY_B
    e2 = _AIRY_E2

    phi = _PHI0
    m = 0.0
    # Iteratively solve for latitude
    while True:
        phi = (northing - _N0 - m) / (a * _F0) + phi
        m = _meridional_arc(phi, _PHI0, a, b)
        if abs(northing - _N0 - m) < 0.00001:
            break

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    nu = a * _F0 / math.sqrt(1 - e2 * sin_phi ** 2)
    rho = a * _F0 * (1 - e2) / (1 - e2 * sin_phi ** 2) ** 1.5
    eta2 = nu / rho - 1

    de = easting - _E0

    VII = tan_phi / (2 * rho * nu)
    VIII = tan_phi / (24 * rho * nu ** 3) * (5 + 3 * tan_phi ** 2 + eta2 - 9 * tan_phi ** 2 * eta2)
    IX = tan_phi / (720 * rho * nu ** 5) * (61 + 90 * tan_phi ** 2 + 45 * tan_phi ** 4)
    X = 1 / (cos_phi * nu)
    XI = 1 / (6 * cos_phi * nu ** 3) * (nu / rho + 2 * tan_phi ** 2)
    XII = 1 / (120 * cos_phi * nu ** 5) * (5 + 28 * tan_phi ** 2 + 24 * tan_phi ** 4)
    XIIA = 1 / (5040 * cos_phi * nu ** 7) * (61 + 662 * tan_phi ** 2 + 1320 * tan_phi ** 4 + 720 * tan_phi ** 6)

    lat = phi - VII * de ** 2 + VIII * de ** 4 - IX * de ** 6
    lon = _LAMBDA0 + X * de - XI * de ** 3 + XII * de ** 5 - XIIA * de ** 7

    return lat, lon


def _helmert_transform(lat_rad, lon_rad, src_a, src_b):
    """Apply Helmert transformation from OSGB36 to WGS84."""
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    sin_lon = math.sin(lon_rad)
    cos_lon = math.cos(lon_rad)

    e2 = 1 - (src_b ** 2) / (src_a ** 2)
    nu = src_a / math.sqrt(1 - e2 * sin_lat ** 2)

    # Cartesian coordinates
    x = (nu + 0) * cos_lat * cos_lon  # height = 0
    y = (nu + 0) * cos_lat * sin_lon
    z = (nu * (1 - e2) + 0) * sin_lat

    # Apply Helmert
    x2 = _TX + (1 + _S) * x + (-_RZ) * y + _RY * z
    y2 = _TY + _RZ * x + (1 + _S) * y + (-_RX) * z
    z2 = _TZ + (-_RY) * x + _RX * y + (1 + _S) * z

    # Back to geodetic on GRS80/WGS84
    a2, b2 = _GRS80_A, _GRS80_B
    e2_2 = 1 - (b2 ** 2) / (a2 ** 2)
    p = math.sqrt(x2 ** 2 + y2 ** 2)
    lat2 = math.atan2(z2, p * (1 - e2_2))

    for _ in range(10):
        nu2 = a2 / math.sqrt(1 - e2_2 * math.sin(lat2) ** 2)
        lat2 = math.atan2(z2 + e2_2 * nu2 * math.sin(lat2), p)

    lon2 = math.atan2(y2, x2)
    return lat2, lon2


def bng_to_wgs84(easting, northing):
    """Convert British National Grid easting/northing to WGS84 (lat, lon) in degrees.

    Args:
        easting: BNG easting in metres
        northing: BNG northing in metres

    Returns:
        Tuple of (latitude, longitude) in decimal degrees, or (None, None) on error.
    """
    try:
        easting = float(easting)
        northing = float(northing)
    except (TypeError, ValueError):
        return None, None

    if easting < 0 or easting > 700000 or northing < 0 or northing > 1300000:
        return None, None

    lat_osgb, lon_osgb = _bng_to_osgb36(easting, northing)
    lat_wgs, lon_wgs = _helmert_transform(lat_osgb, lon_osgb, _AIRY_A, _AIRY_B)

    return round(math.degrees(lat_wgs), 6), round(math.degrees(lon_wgs), 6)
