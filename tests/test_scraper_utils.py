"""Tests for scraper utility functions."""


from app.scraper.scraper import (
    _extract_outcode,
    _for_sale_dict_to_property,
    _format_price,
    _resolve_ref,
    _tokenize_for_typeahead,
    extract_postcode,
    normalise_postcode_for_url,
)


class TestExtractPostcode:
    def test_full_postcode(self):
        assert extract_postcode("10 High Street, London SW20 8NE") == "SW20 8NE"

    def test_no_space(self):
        assert extract_postcode("10 High Street SW208NE") == "SW208NE"

    def test_no_postcode(self):
        assert extract_postcode("10 High Street, London") == ""

    def test_empty(self):
        assert extract_postcode("") == ""

    def test_short_outcode(self):
        assert extract_postcode("Flat 1, E1 6AA") == "E1 6AA"

    def test_long_outcode(self):
        assert extract_postcode("123 Road, EC1A 1BB") == "EC1A 1BB"


class TestNormalisePostcodeForUrl:
    def test_with_space(self):
        assert normalise_postcode_for_url("SW20 8NE") == "SW208NE"

    def test_with_dash(self):
        assert normalise_postcode_for_url("SW20-8NE") == "SW208NE"

    def test_lowercase(self):
        assert normalise_postcode_for_url("sw20 8ne") == "SW208NE"

    def test_already_normalised(self):
        assert normalise_postcode_for_url("SW208NE") == "SW208NE"


class TestFormatPrice:
    def test_integer(self):
        assert _format_price(450000) == "£450,000"

    def test_float(self):
        assert _format_price(450000.0) == "£450,000"

    def test_string(self):
        assert _format_price("£450,000") == "£450,000"

    def test_none(self):
        assert _format_price(None) == ""


class TestResolveRef:
    def test_null_markers(self):
        assert _resolve_ref([], -5) is None
        assert _resolve_ref([], -6) is None

    def test_boolean(self):
        assert _resolve_ref([], True) is True
        assert _resolve_ref([], False) is False

    def test_index_lookup(self):
        flat = ["a", "b", "c"]
        assert _resolve_ref(flat, 1) == "b"

    def test_out_of_bounds(self):
        flat = ["a"]
        assert _resolve_ref(flat, 5) == 5

    def test_string_passthrough(self):
        assert _resolve_ref([], "hello") == "hello"


class TestExtractOutcode:
    def test_full_postcode(self):
        assert _extract_outcode("SW20 8NE") == "SW20"

    def test_no_space(self):
        assert _extract_outcode("SW208NE") == "SW20"

    def test_outcode_only(self):
        assert _extract_outcode("SW20") == "SW20"

    def test_short_outcode(self):
        assert _extract_outcode("E1 6AA") == "E1"

    def test_long_outcode(self):
        assert _extract_outcode("EC1A 1BB") == "EC1A"

    def test_e1w(self):
        assert _extract_outcode("E1W 1AT") == "E1W"


class TestTokenizeForTypeahead:
    def test_full_postcode(self):
        assert _tokenize_for_typeahead("SW208NE") == "SW/20/8N/E"

    def test_with_spaces(self):
        assert _tokenize_for_typeahead("SW20 8NE") == "SW/20/8N/E"

    def test_outcode_only(self):
        assert _tokenize_for_typeahead("SW20") == "SW/20"

    def test_short_outcode(self):
        assert _tokenize_for_typeahead("E1") == "E1"

    def test_lowercase(self):
        assert _tokenize_for_typeahead("sw20 8ne") == "SW/20/8N/E"


class TestForSaleDictToProperty:
    def test_basic_property(self):
        d = {
            "displayAddress": "10 High Street, London SW20 8NE",
            "id": 12345,
            "price": {"amount": 450000, "displayPrices": [{"displayPrice": "Guide Price \u00a3450,000"}]},
            "bedrooms": 3,
            "bathrooms": 2,
            "propertySubType": "Semi-Detached",
        }
        prop = _for_sale_dict_to_property(d, "SW20 8NE")
        assert prop is not None
        assert prop.address == "10 High Street, London SW20 8NE"
        assert prop.asking_price == 450000
        assert prop.asking_price_display == "Guide Price \u00a3450,000"
        assert prop.bedrooms == 3
        assert prop.bathrooms == 2
        assert prop.listing_id == "12345"
        assert prop.postcode == "SW20 8NE"
        assert prop.property_type == "Semi-Detached"

    def test_missing_address_returns_none(self):
        d = {"id": 12345, "price": {"amount": 300000}}
        assert _for_sale_dict_to_property(d, "SW20 8NE") is None

    def test_missing_price(self):
        d = {"displayAddress": "10 High Street", "id": 12345}
        prop = _for_sale_dict_to_property(d, "SW20 8NE")
        assert prop is not None
        assert prop.asking_price is None
        assert prop.asking_price_display == ""

    def test_fallback_postcode(self):
        d = {"displayAddress": "10 High Street, London", "id": 99}
        prop = _for_sale_dict_to_property(d, "E1 6AA")
        assert prop is not None
        assert prop.postcode == "E1 6AA"
