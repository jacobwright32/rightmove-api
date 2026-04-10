"""Comprehensive tests for app.feature_parser — ~155 tests."""

import json

import pytest

from app.constants import FEATURE_PARSER_KEYS
from app.feature_parser import (
    parse_all_features,
    parse_allocated_parking,
    parse_chain_free,
    parse_condition,
    parse_conservation_area,
    parse_council_tax_band,
    parse_cul_de_sac,
    parse_distance_to_station,
    parse_double_glazed,
    parse_duplex,
    parse_epc_rating,
    parse_extended,
    parse_floor_level,
    parse_furnished,
    parse_garden,
    parse_garden_facing,
    parse_ground_rent,
    parse_has_air_conditioning,
    parse_has_annexe,
    parse_has_bay_window,
    parse_has_bike_storage,
    parse_has_cellar,
    parse_has_cloakroom,
    parse_has_concierge,
    parse_has_conservatory,
    parse_has_dining_room,
    parse_has_ensuite,
    parse_has_entrance_hall,
    parse_has_ev_charger,
    parse_has_fireplace,
    parse_has_fitted_wardrobes,
    parse_has_gated,
    parse_has_gym,
    parse_has_high_ceilings,
    parse_has_integrated_appliances,
    parse_has_intercom,
    parse_has_laminate_flooring,
    parse_has_lift,
    parse_has_loft,
    parse_has_open_plan,
    parse_has_outbuilding,
    parse_has_roof_terrace,
    parse_has_separate_living_room,
    parse_has_shower_room,
    parse_has_side_access,
    parse_has_solar_panels,
    parse_has_study,
    parse_has_swimming_pool,
    parse_has_utility_room,
    parse_has_video_entry,
    parse_has_views,
    parse_has_walk_in_wardrobe,
    parse_has_wet_room,
    parse_has_white_goods,
    parse_has_wooden_floors,
    parse_heating,
    parse_kitchen_type,
    parse_lease,
    parse_listed_building,
    parse_new_build,
    parse_own_front_door,
    parse_parking,
    parse_penthouse,
    parse_period_property,
    parse_potential_to_extend,
    parse_private_entrance,
    parse_property_era,
    parse_purpose_built,
    parse_receptions,
    parse_refurbished,
    parse_service_charge,
    parse_split_level,
    parse_sq_ft,
    parse_underground_parking,
)

# ── EPC Rating ──────────────────────────────────────────────────────────────


class TestParseEpcRating:
    def test_standard(self):
        assert parse_epc_rating(["EPC Rating C"]) == "C"

    def test_with_colon(self):
        assert parse_epc_rating(["EPC: D"]) == "D"

    def test_energy_keyword(self):
        assert parse_epc_rating(["Energy Efficiency Rating B"]) == "B"

    def test_band(self):
        assert parse_epc_rating(["EPC Band F"]) == "F"

    def test_case_insensitive(self):
        assert parse_epc_rating(["epc rating a"]) == "A"

    def test_with_score(self):
        assert parse_epc_rating(["EPC Rating E (42)"]) == "E"

    def test_no_match(self):
        assert parse_epc_rating(["Two bathrooms"]) is None

    def test_empty(self):
        assert parse_epc_rating([]) is None


# ── Council Tax Band ────────────────────────────────────────────────────────


class TestParseCouncilTaxBand:
    def test_standard(self):
        assert parse_council_tax_band(["Council Tax Band D"]) == "D"

    def test_with_colon(self):
        assert parse_council_tax_band(["Council Tax: Band A"]) == "A"

    def test_no_match(self):
        assert parse_council_tax_band(["Two bedrooms"]) is None

    def test_band_h(self):
        assert parse_council_tax_band(["Council Tax Band H"]) == "H"


# ── Chain Free ──────────────────────────────────────────────────────────────


class TestParseChainFree:
    def test_no_onward_chain(self):
        assert parse_chain_free(["No Onward Chain"]) is True

    def test_chain_free(self):
        assert parse_chain_free(["Chain Free"]) is True

    def test_no_forward_chain(self):
        assert parse_chain_free(["No Forward Chain"]) is True

    def test_chain_free_hyphen(self):
        assert parse_chain_free(["Chain-Free"]) is True

    def test_end_of_chain(self):
        assert parse_chain_free(["End of chain"]) is False

    def test_no_match(self):
        assert parse_chain_free(["Two bedrooms"]) is None


# ── Parking ─────────────────────────────────────────────────────────────────


class TestParseParking:
    def test_garage(self):
        assert parse_parking(["Single Garage"]) == "Garage"

    def test_driveway(self):
        assert parse_parking(["Private Driveway"]) == "Driveway"

    def test_off_street(self):
        assert parse_parking(["Off-street parking"]) == "Off-street"

    def test_generic(self):
        assert parse_parking(["Parking space included"]) == "Parking"

    def test_no_match(self):
        assert parse_parking(["Two bedrooms"]) is None


# ── Garden ──────────────────────────────────────────────────────────────────


class TestParseGarden:
    def test_balcony(self):
        assert parse_garden(["Private Balcony"]) == "Balcony"

    def test_private_garden(self):
        assert parse_garden(["Private Rear Garden"]) == "Private Garden"

    def test_communal_garden(self):
        assert parse_garden(["Communal Garden"]) == "Communal Garden"

    def test_patio(self):
        assert parse_garden(["Patio area"]) == "Patio"

    def test_generic_garden(self):
        assert parse_garden(["Rear Garden"]) == "Garden"

    def test_roof_terrace(self):
        assert parse_garden(["Roof terrace"]) == "Terrace"

    def test_no_match(self):
        assert parse_garden(["Two bedrooms"]) is None


# ── Heating ─────────────────────────────────────────────────────────────────


class TestParseHeating:
    def test_gas_central(self):
        assert parse_heating(["Gas Central Heating"]) == "Gas Central"

    def test_underfloor(self):
        assert parse_heating(["Underfloor Heating"]) == "Underfloor"

    def test_central(self):
        assert parse_heating(["Central Heating"]) == "Central Heating"

    def test_electric(self):
        assert parse_heating(["Electric Heating"]) == "Electric"

    def test_other(self):
        assert parse_heating(["Heating system"]) == "Other"

    def test_no_match(self):
        assert parse_heating(["Two bedrooms"]) is None


# ── Lease ───────────────────────────────────────────────────────────────────


class TestParseLease:
    def test_freehold(self):
        assert parse_lease(["Freehold"]) == ("Freehold", None)

    def test_leasehold_with_years(self):
        assert parse_lease(["Leasehold - 99 years remaining"]) == ("Leasehold", 99)

    def test_share_of_freehold(self):
        assert parse_lease(["Share of Freehold"]) == ("Share of Freehold", None)

    def test_year_lease_pattern(self):
        assert parse_lease(["125 year lease"]) == ("Leasehold", 125)

    def test_priority_share_over_freehold(self):
        t, y = parse_lease(["Share of Freehold", "Freehold"])
        assert t == "Share of Freehold"

    def test_no_match(self):
        assert parse_lease(["Two bedrooms"]) == (None, None)

    def test_leasehold_no_years(self):
        assert parse_lease(["Leasehold"]) == ("Leasehold", None)


# ── Furnished ───────────────────────────────────────────────────────────────


class TestParseFurnished:
    def test_furnished(self):
        assert parse_furnished(["Furnished"]) == "Furnished"

    def test_unfurnished(self):
        assert parse_furnished(["Unfurnished"]) == "Unfurnished"

    def test_part_furnished(self):
        assert parse_furnished(["Part Furnished"]) == "Part Furnished"

    def test_part_furnished_hyphen(self):
        assert parse_furnished(["Part-Furnished"]) == "Part Furnished"

    def test_flexible(self):
        assert parse_furnished(["Furnished or Unfurnished"]) == "Flexible"

    def test_no_match(self):
        assert parse_furnished(["Two bedrooms"]) is None


# ── Floor Level ─────────────────────────────────────────────────────────────


class TestParseFloorLevel:
    def test_ground(self):
        assert parse_floor_level(["Ground Floor Flat"]) == "Ground"

    def test_first(self):
        assert parse_floor_level(["First Floor"]) == "First"

    def test_second(self):
        assert parse_floor_level(["Second Floor Flat"]) == "Second"

    def test_third(self):
        assert parse_floor_level(["Third Floor"]) == "Third"

    def test_3rd(self):
        assert parse_floor_level(["3rd Floor Flat"]) == "Third"

    def test_upper(self):
        assert parse_floor_level(["4th Floor Apartment"]) == "Upper"

    def test_top(self):
        assert parse_floor_level(["Top Floor"]) == "Top"

    def test_basement(self):
        assert parse_floor_level(["Basement Flat"]) == "Basement"

    def test_lower_ground(self):
        assert parse_floor_level(["Lower Ground Floor"]) == "Ground"

    def test_no_match(self):
        assert parse_floor_level(["Two bedrooms"]) is None


# ── Sq Ft ───────────────────────────────────────────────────────────────────


class TestParseSqFt:
    def test_standard(self):
        assert parse_sq_ft(["797 Sq Ft"]) == 797

    def test_with_comma(self):
        assert parse_sq_ft(["1,200 sq ft"]) == 1200

    def test_with_prefix(self):
        assert parse_sq_ft(["Over 700sq ft"]) == 700

    def test_sqm_conversion(self):
        result = parse_sq_ft(["74 sq m"])
        assert result == int(round(74 * 10.764))

    def test_no_match(self):
        assert parse_sq_ft(["Two bedrooms"]) is None


# ── Service Charge ──────────────────────────────────────────────────────────


class TestParseServiceCharge:
    def test_standard(self):
        assert parse_service_charge(["Service Charge - \u00a31,165 per annum"]) == 1165

    def test_with_pence(self):
        assert parse_service_charge(["Service Charge - \u00a3249.70 PA"]) == 249

    def test_maintenance(self):
        assert parse_service_charge(["Service/Maintenance - \u00a3800 pa"]) == 800

    def test_no_match(self):
        assert parse_service_charge(["Two bedrooms"]) is None


# ── Ground Rent ─────────────────────────────────────────────────────────────


class TestParseGroundRent:
    def test_standard(self):
        assert parse_ground_rent(["Ground Rent \u00a3250 per annum"]) == 250

    def test_with_pence(self):
        assert parse_ground_rent(["Ground rent: \u00a3350.50"]) == 350

    def test_no_match(self):
        assert parse_ground_rent(["Two bedrooms"]) is None


# ── Receptions ──────────────────────────────────────────────────────────────


class TestParseReceptions:
    def test_numeric(self):
        assert parse_receptions(["2 Reception Rooms"]) == 2

    def test_word(self):
        assert parse_receptions(["Two Reception Rooms"]) == 2

    def test_single(self):
        assert parse_receptions(["1 reception room"]) == 1

    def test_no_match(self):
        assert parse_receptions(["Two bedrooms"]) is None


# ── Distance to Station ────────────────────────────────────────────────────


class TestParseDistanceToStation:
    def test_standard(self):
        assert parse_distance_to_station(["0.2 Miles to Raynes Park Station"]) == 0.2

    def test_from(self):
        assert parse_distance_to_station(["0.4 Miles From Clapham Station"]) == 0.4

    def test_one_mile(self):
        assert parse_distance_to_station(["1 Mile to Station"]) == 1.0

    def test_no_match(self):
        assert parse_distance_to_station(["Close to shops"]) is None


# ── Boolean Parsers (parametrized) ──────────────────────────────────────────


_BOOLEAN_CASES = [
    (parse_double_glazed, "Double Glazed", "Two bedrooms"),
    (parse_period_property, "Period Property", "Modern flat"),
    (parse_has_utility_room, "Utility Room", "Kitchen"),
    (parse_has_conservatory, "Conservatory", "Kitchen"),
    (parse_has_ensuite, "En-suite bathroom", "Family bathroom"),
    (parse_has_cloakroom, "Downstairs cloakroom", "Kitchen"),
    (parse_has_wooden_floors, "Wooden floors throughout", "Carpet"),
    (parse_has_gym, "Residents Gym", "Swimming pool"),
    (parse_has_lift, "Lift access", "Ground floor"),
    (parse_has_dining_room, "Separate Dining Room", "Kitchen"),
    (parse_has_ev_charger, "EV Charging Point", "Parking"),
    (parse_has_fireplace, "Open Fireplace", "Radiator"),
    (parse_has_study, "Study", "Bedroom"),
    (parse_has_shower_room, "Separate Shower Room", "Bathroom"),
    (parse_has_fitted_wardrobes, "Fitted Wardrobes", "Shelves"),
    (parse_new_build, "New Build", "Period"),
    (parse_has_concierge, "24hr Concierge", "Reception"),
    (parse_has_swimming_pool, "Swimming Pool", "Garden"),
    (parse_has_air_conditioning, "Air Conditioning", "Fan"),
    (parse_has_solar_panels, "Solar Panels", "Roof"),
    (parse_has_loft, "Loft conversion", "Attic"),
    (parse_has_entrance_hall, "Entrance Hall", "Hallway"),
    (parse_has_white_goods, "White goods included", "Curtains"),
    (parse_has_bay_window, "Bay Window", "Sash window"),
    (parse_has_intercom, "Intercom system", "Doorbell"),
    (parse_split_level, "Split Level", "Open plan"),
    (parse_has_cellar, "Cellar", "Attic"),
    (parse_has_roof_terrace, "Roof Terrace", "Balcony only"),
    (parse_has_high_ceilings, "High Ceilings", "Low ceiling"),
    (parse_has_open_plan, "Open-plan living", "Separate rooms"),
    (parse_has_gated, "Gated development", "Open estate"),
    (parse_purpose_built, "Purpose-built flat", "Converted flat"),
    (parse_refurbished, "Recently Refurbished", "Original condition"),
    (parse_duplex, "Duplex apartment", "Studio"),
    (parse_penthouse, "Penthouse suite", "Ground floor flat"),
    (parse_own_front_door, "Own front door", "Shared entrance"),
    (parse_private_entrance, "Private entrance", "Communal entrance"),
    (parse_has_bike_storage, "Bike storage", "Car parking"),
    (parse_cul_de_sac, "Quiet cul-de-sac", "Main road"),
    (parse_conservation_area, "Conservation Area", "New development"),
    (parse_has_annexe, "Self-contained annexe", "Extension"),
    (parse_has_views, "River views", "Brick wall view"),
    (parse_underground_parking, "Underground parking", "Street parking"),
    (parse_allocated_parking, "Allocated parking space", "Street parking"),
    (parse_listed_building, "Grade II Listed Building", "New build"),
    (parse_extended, "Extended kitchen", "Original layout"),
    (parse_has_outbuilding, "Garden room", "Shed"),
    (parse_potential_to_extend, "Potential to extend STPP", "Compact"),
    (parse_has_walk_in_wardrobe, "Walk-in wardrobe", "Fitted wardrobes"),
    (parse_has_wet_room, "Wet room", "Shower room"),
    (parse_has_integrated_appliances, "Integrated appliances", "Freestanding oven"),
    (parse_has_side_access, "Side access gate", "Front door"),
    (parse_has_video_entry, "Video entry system", "Key fob"),
    (parse_has_separate_living_room, "sitting room", "Kitchen"),
    (parse_has_laminate_flooring, "Laminate flooring", "Carpet"),
]


class TestBooleanParsers:
    @pytest.mark.parametrize(
        "parser,positive,negative",
        _BOOLEAN_CASES,
        ids=[f[0].__name__ for f in _BOOLEAN_CASES],
    )
    def test_positive(self, parser, positive, negative):
        assert parser([positive]) is True

    @pytest.mark.parametrize(
        "parser,positive,negative",
        _BOOLEAN_CASES,
        ids=[f[0].__name__ for f in _BOOLEAN_CASES],
    )
    def test_negative(self, parser, positive, negative):
        assert parser([negative]) is None


# ── Categorical Parsers ─────────────────────────────────────────────────────


class TestParseCategorical:
    # garden_facing
    def test_south_facing(self):
        assert parse_garden_facing(["South Facing Garden"]) == "South"

    def test_west_facing(self):
        assert parse_garden_facing(["West Facing"]) == "West"

    def test_east_facing(self):
        assert parse_garden_facing(["East Facing Garden"]) == "East"

    def test_north_facing(self):
        assert parse_garden_facing(["North Facing"]) == "North"

    def test_facing_no_match(self):
        assert parse_garden_facing(["Garden"]) is None

    # property_era
    def test_victorian(self):
        assert parse_property_era(["Victorian Terraced House"]) == "Victorian"

    def test_edwardian(self):
        assert parse_property_era(["Edwardian Semi"]) == "Edwardian"

    def test_georgian(self):
        assert parse_property_era(["Georgian Townhouse"]) == "Georgian"

    def test_art_deco(self):
        assert parse_property_era(["Art Deco Mansion Block"]) == "Art Deco"

    def test_era_no_match(self):
        assert parse_property_era(["Modern Flat"]) is None

    # condition
    def test_immaculate(self):
        assert parse_condition(["Immaculate throughout"]) == "Immaculate"

    def test_excellent(self):
        assert parse_condition(["Excellent Condition"]) == "Excellent"

    def test_good(self):
        assert parse_condition(["Good Condition"]) == "Good"

    def test_fair(self):
        assert parse_condition(["Fair Condition"]) == "Fair"

    def test_condition_no_match(self):
        assert parse_condition(["Two bedrooms"]) is None

    # kitchen_type
    def test_open_plan_kitchen(self):
        assert parse_kitchen_type(["Open-plan kitchen"]) == "Open Plan"

    def test_kitchen_diner(self):
        assert parse_kitchen_type(["Kitchen/Diner"]) == "Kitchen Diner"

    def test_eat_in(self):
        assert parse_kitchen_type(["Eat-in Kitchen"]) == "Eat-in"

    def test_separate_kitchen(self):
        assert parse_kitchen_type(["Separate Kitchen"]) == "Separate"

    def test_kitchen_no_match(self):
        assert parse_kitchen_type(["Two bedrooms"]) is None


# ── parse_all_features ──────────────────────────────────────────────────────


class TestParseAllFeatures:
    def test_none(self):
        result = parse_all_features(None)
        assert all(v is None for v in result.values())
        assert set(result.keys()) == set(FEATURE_PARSER_KEYS)

    def test_empty_string(self):
        result = parse_all_features("")
        assert all(v is None for v in result.values())

    def test_invalid_json(self):
        result = parse_all_features("not json")
        assert all(v is None for v in result.values())

    def test_empty_array(self):
        result = parse_all_features("[]")
        assert all(v is None for v in result.values())

    def test_realistic_v1(self):
        features = json.dumps(["EPC Rating C", "Gas Central Heating", "Double Glazed"])
        result = parse_all_features(features)
        assert result["epc_rating"] == "C"
        assert result["heating"] == "Gas Central"
        assert result["double_glazed"] is True

    def test_realistic_v2(self):
        features = json.dumps(["South Facing Garden", "Penthouse", "Roof Terrace"])
        result = parse_all_features(features)
        assert result["garden_facing"] == "South"
        assert result["penthouse"] is True
        assert result["roof_terrace"] is True

    def test_realistic_v3(self):
        features = json.dumps(["Extended kitchen", "Walk-in wardrobe", "Wet room"])
        result = parse_all_features(features)
        assert result["extended"] is True
        assert result["walk_in_wardrobe"] is True
        assert result["wet_room"] is True

    def test_non_list_json(self):
        result = parse_all_features('{"key": "value"}')
        assert all(v is None for v in result.values())


# ── Key Consistency ─────────────────────────────────────────────────────────


class TestKeyConsistency:
    def test_keys_match_constant(self):
        result = parse_all_features("[]")
        assert set(result.keys()) == set(FEATURE_PARSER_KEYS)

    def test_no_duplicate_keys(self):
        assert len(FEATURE_PARSER_KEYS) == len(set(FEATURE_PARSER_KEYS))

    def test_key_count(self):
        assert len(FEATURE_PARSER_KEYS) == 74

    def test_all_keys_are_strings(self):
        assert all(isinstance(k, str) for k in FEATURE_PARSER_KEYS)

    def test_no_empty_keys(self):
        assert all(k for k in FEATURE_PARSER_KEYS)

    def test_keys_are_snake_case(self):
        import re

        for k in FEATURE_PARSER_KEYS:
            assert re.match(r"^[a-z][a-z0-9_]*$", k), f"Key '{k}' not snake_case"


# ── Edge Cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_extended_excludes_potential(self):
        """'potential to extend' should NOT trigger extended parser."""
        assert parse_extended(["Potential to extend"]) is None

    def test_side_access_excludes_extension(self):
        """'side return extension' should NOT trigger side_access parser."""
        assert parse_has_side_access(["Side return extension"]) is None

    def test_cellar_excludes_basement_flat(self):
        """'Basement flat' should NOT trigger cellar parser."""
        assert parse_has_cellar(["Basement flat"]) is None

    def test_views_requires_type(self):
        """Standalone 'views' without type should NOT match."""
        assert parse_has_views(["Great views"]) is None

    def test_views_with_type(self):
        assert parse_has_views(["Views over the Thames"]) is True

    def test_study_short_feature(self):
        """Short standalone 'Study' matches."""
        assert parse_has_study(["Study"]) is True

    def test_epc_does_not_match_rating_letter(self):
        """Regression: 'EPC Rating C' must return 'C' not 'G'."""
        assert parse_epc_rating(["EPC Rating C"]) == "C"
