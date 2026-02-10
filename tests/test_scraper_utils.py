"""Tests for scraper utility functions."""

import pytest

from app.scraper.rightmove import (
    PropertyData,
    SaleRecord,
    extract_postcode,
    normalise_postcode_for_url,
    _format_price,
    _resolve_ref,
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
