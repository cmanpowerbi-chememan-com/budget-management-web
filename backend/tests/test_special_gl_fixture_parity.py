"""Parity check: `app.special_gl`'s hardcoded GL-conditional dropdown sets
(Entertainment, Lease & Rental) must match
`docs/reference/special-gl-dropdown-fixture.json` exactly — the SAME file the
frontend's `glDropdownConstants.test.ts` loads, so a change on either side
that silently drifts from the other fails a test immediately (A9 never-cut:
"the UI never submits what the server rejects"). Lives under docs/reference/
(tracked in git) rather than docs/13Template Special/ (gitignored — large
Excel source dumps, per .gitignore's comment) so CI can actually read it.
"""
import json
from pathlib import Path

from app.special_gl import (
    _ENTERTAINMENT_EXTERNAL_GLS,
    _ENTERTAINMENT_EXTERNAL_VALUES,
    _ENTERTAINMENT_INTERNAL_GLS,
    _ENTERTAINMENT_INTERNAL_VALUES,
    _LEASE_MACHINERY_SUFFIX,
    _LEASE_MACHINERY_TYPES,
    _LEASE_NONVEHICLE_SUFFIXES,
    _LEASE_PLANTS,
    _LEASE_PLATES,
    _LEASE_VEHICLE_SUFFIX,
    _LEASE_VEHICLE_TYPES,
)
from app.write_model import TRAVEL_GL_BY_TYPE_SIDE

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "docs" / "reference" / "special-gl-dropdown-fixture.json"


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_file_exists_and_parses():
    fixture = _load_fixture()
    assert "entertainment" in fixture
    assert "lease_rental" in fixture


def test_entertainment_gls_and_values_match_fixture():
    fixture = _load_fixture()["entertainment"]
    assert _ENTERTAINMENT_EXTERNAL_GLS == frozenset(fixture["external_gls"])
    assert _ENTERTAINMENT_INTERNAL_GLS == frozenset(fixture["internal_gls"])
    assert _ENTERTAINMENT_EXTERNAL_VALUES == frozenset(fixture["external_values"])
    assert _ENTERTAINMENT_INTERNAL_VALUES == frozenset(fixture["internal_values"])


def test_lease_rental_suffixes_and_options_match_fixture():
    fixture = _load_fixture()["lease_rental"]
    assert _LEASE_VEHICLE_SUFFIX == fixture["vehicle_suffix"]
    assert _LEASE_MACHINERY_SUFFIX == fixture["machinery_suffix"]
    assert _LEASE_NONVEHICLE_SUFFIXES == frozenset(fixture["nonvehicle_suffixes"])
    assert _LEASE_VEHICLE_TYPES == frozenset(fixture["vehicle_types"])
    assert _LEASE_MACHINERY_TYPES == frozenset(fixture["machinery_types"])
    assert _LEASE_PLANTS == frozenset(fixture["plants"])
    assert _LEASE_PLATES == frozenset(fixture["plates"])


def test_travel_gl_by_type_side_matches_fixture():
    fixture = _load_fixture()["travelling"]["gl_by_type_side"]
    assert TRAVEL_GL_BY_TYPE_SIDE == fixture
