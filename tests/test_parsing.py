"""Tests for price and date parsing utilities."""


from app.parsing import parse_date_to_iso, parse_price_to_int


class TestParsePriceToInt:
    def test_standard_format(self):
        assert parse_price_to_int("£450,000") == 450000

    def test_no_symbol(self):
        assert parse_price_to_int("450,000") == 450000

    def test_no_commas(self):
        assert parse_price_to_int("£450000") == 450000

    def test_million(self):
        assert parse_price_to_int("£1,200,000") == 1200000

    def test_small_price(self):
        assert parse_price_to_int("£50,000") == 50000

    def test_empty_string(self):
        assert parse_price_to_int("") is None

    def test_none(self):
        assert parse_price_to_int(None) is None

    def test_no_digits(self):
        assert parse_price_to_int("£") is None

    def test_mojibake_pound(self):
        """Handle double-encoded UTF-8 £ symbol."""
        assert parse_price_to_int("\u00c2\u00a3450,000") == 450000


class TestParseDateToIso:
    def test_standard_format(self):
        assert parse_date_to_iso("4 Nov 2023") == "2023-11-04"

    def test_leading_zero(self):
        assert parse_date_to_iso("04 Nov 2023") == "2023-11-04"

    def test_double_digit_day(self):
        assert parse_date_to_iso("15 Mar 2021") == "2021-03-15"

    def test_january(self):
        assert parse_date_to_iso("1 Jan 2020") == "2020-01-01"

    def test_december(self):
        assert parse_date_to_iso("31 Dec 2019") == "2019-12-31"

    def test_empty_string(self):
        assert parse_date_to_iso("") is None

    def test_none(self):
        assert parse_date_to_iso(None) is None

    def test_invalid_month(self):
        assert parse_date_to_iso("4 Xyz 2023") is None

    def test_invalid_format(self):
        assert parse_date_to_iso("2023-11-04") is None

    def test_invalid_date(self):
        assert parse_date_to_iso("31 Feb 2023") is None

    def test_whitespace(self):
        assert parse_date_to_iso("  4 Nov 2023  ") == "2023-11-04"
