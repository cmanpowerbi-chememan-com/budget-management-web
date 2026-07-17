"""Unit tests for app.special_gl — GL-conditional special-GL dropdown
validation (spec §4a). Pure, no I/O.
"""
import pytest

from app.special_gl import (
    SPECIAL_GL_GROUPS,
    MetaValidationError,
    classify_special_gl,
    validate_entertainment_meta,
    validate_lease_meta,
)


# ---------------------------------------------------------------------------
# classify_special_gl
# ---------------------------------------------------------------------------

def test_classify_special_gl_recognises_all_six_groups():
    for name in (
        "Entertainment", "Lease & Rental", "Professional & Legal Fee",
        "Public Relation & Donation", "Training & Seminar", "Travelling Expense",
    ):
        assert classify_special_gl(name) == name


def test_classify_special_gl_returns_none_for_a_normal_gl_group():
    assert classify_special_gl("Bank Charge") is None
    assert classify_special_gl(None) is None


def test_special_gl_groups_constant_has_exactly_six_entries():
    assert len(SPECIAL_GL_GROUPS) == 6


# ---------------------------------------------------------------------------
# Entertainment — 030 external / 031 internal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gl_account", ["5211900030", "6211900030"])
def test_entertainment_external_gl_accepts_external_values(gl_account):
    validate_entertainment_meta(gl_account, {"ประเภทการรับรอง": "Customer"})
    validate_entertainment_meta(gl_account, {"ประเภทการรับรอง": "Business partner"})
    validate_entertainment_meta(gl_account, {"ประเภทการรับรอง": "หน่วยงานราชการ"})
    validate_entertainment_meta(gl_account, {"ประเภทการรับรอง": "อื่นๆ"})


def test_entertainment_internal_gl_accepts_internal_values():
    validate_entertainment_meta("6211900031", {"ประเภทการรับรอง": "พนักงานบริษัท"})
    validate_entertainment_meta("6211900031", {"ประเภทการรับรอง": "กรรมการบริษัท"})


def test_entertainment_internal_gl_rejects_an_external_only_value():
    """An External-only value on the Internal-only GL (6211900031) is invalid."""
    with pytest.raises(MetaValidationError):
        validate_entertainment_meta("6211900031", {"ประเภทการรับรอง": "Customer"})


def test_entertainment_external_gl_rejects_an_internal_only_value():
    with pytest.raises(MetaValidationError):
        validate_entertainment_meta("5211900030", {"ประเภทการรับรอง": "พนักงานบริษัท"})


def test_entertainment_unrecognised_gl_raises():
    with pytest.raises(MetaValidationError):
        validate_entertainment_meta("9999999999", {"ประเภทการรับรอง": "Customer"})


def test_entertainment_missing_value_key_is_a_noop():
    # No dropdown chosen yet (e.g. still drafting) — nothing to validate.
    validate_entertainment_meta("5211900030", {})


# ---------------------------------------------------------------------------
# Lease & Rental — suffix drives dropdown vs free vs grey
# ---------------------------------------------------------------------------

def test_lease_vehicle_suffix_accepts_vehicle_type_and_plate():
    cleaned = validate_lease_meta(
        "5211200060",
        {"ประเภทรถ": "Car", "ทะเบียนรถ": "6ขผ-3918", "สถานที่ใช้งาน": "BK", "กิจกรรม": "ส่งของ"},
    )
    assert cleaned["ประเภทรถ"] == "Car"
    assert cleaned["ทะเบียนรถ"] == "6ขผ-3918"
    assert cleaned["สถานที่ใช้งาน"] == "BK"
    assert cleaned["กิจกรรม"] == "ส่งของ"


def test_lease_vehicle_suffix_rejects_a_machinery_type():
    with pytest.raises(MetaValidationError):
        validate_lease_meta("6211200060", {"ประเภทรถ": "Excavator"})


def test_lease_machinery_suffix_accepts_machinery_type_and_greys_out_plate():
    cleaned = validate_lease_meta("5211200030", {"ประเภทรถ": "Excavator", "ทะเบียนรถ": "6ขผ-3918"})
    assert cleaned["ประเภทรถ"] == "Excavator"
    assert cleaned["ทะเบียนรถ"] is None  # locked/grey for Machinery — never persisted


def test_lease_nonvehicle_suffixes_grey_out_both_type_and_plate():
    for suffix_gl in ("5211200010", "6211200020", "5211200040", "6211200050", "5211200999"):
        cleaned = validate_lease_meta(suffix_gl, {"ประเภทรถ": "Car", "ทะเบียนรถ": "6ขผ-3918", "สถานที่ใช้งาน": "TK"})
        assert cleaned["ประเภทรถ"] is None
        assert cleaned["ทะเบียนรถ"] is None
        assert cleaned["สถานที่ใช้งาน"] == "TK"


def test_lease_plant_dropdown_applies_to_all_subcategories():
    with pytest.raises(MetaValidationError):
        validate_lease_meta("5211200010", {"สถานที่ใช้งาน": "NOT-A-PLANT"})


def test_lease_unrecognised_suffix_raises():
    with pytest.raises(MetaValidationError):
        validate_lease_meta("5211200070", {})


def test_lease_meta_with_no_values_yet_is_valid_all_none():
    cleaned = validate_lease_meta("5211200060", {})
    assert cleaned == {"สถานที่ใช้งาน": None, "กิจกรรม": None, "ประเภทรถ": None, "ทะเบียนรถ": None}


# ---------------------------------------------------------------------------
# Lease & Rental — ทะเบียนรถ is FREE TEXT (jakkaritw 2026-07-17): the 7 known
# plates are a convenience dropdown, NOT an allowlist. Picking the "อื่นๆ"
# sentinel opens a free-text input and the TYPED plate is what persists —
# the sentinel strings themselves ("อื่นๆ", legacy "ไม่ระบุ") must never be
# stored as a plate.
# ---------------------------------------------------------------------------

def test_lease_vehicle_plate_accepts_free_text_outside_the_known_list():
    cleaned = validate_lease_meta("5211200060", {"ทะเบียนรถ": "9กท-1234"})
    assert cleaned["ทะเบียนรถ"] == "9กท-1234"


def test_lease_vehicle_plate_still_accepts_the_known_dropdown_plates():
    for plate in ("6ขผ-3918", "1นจ-3508", "7ขถ-9660"):
        cleaned = validate_lease_meta("5211200060", {"ทะเบียนรถ": plate})
        assert cleaned["ทะเบียนรถ"] == plate


def test_lease_vehicle_plate_rejects_dropdown_sentinel_strings():
    """"อื่นๆ" (and legacy "ไม่ระบุ") mean the user picked the free-text
    option but never typed the real plate — reject, never persist."""
    for sentinel in ("อื่นๆ", "ไม่ระบุ", " อื่นๆ "):
        with pytest.raises(MetaValidationError):
            validate_lease_meta("5211200060", {"ทะเบียนรถ": sentinel})


def test_lease_vehicle_plate_rejects_empty_and_whitespace_only():
    for bad in ("", "   "):
        with pytest.raises(MetaValidationError):
            validate_lease_meta("5211200060", {"ทะเบียนรถ": bad})


def test_lease_vehicle_plate_rejects_over_max_length():
    with pytest.raises(MetaValidationError):
        validate_lease_meta("5211200060", {"ทะเบียนรถ": "ก" * 51})


def test_lease_vehicle_plate_rejects_non_string():
    with pytest.raises(MetaValidationError):
        validate_lease_meta("5211200060", {"ทะเบียนรถ": 1234})
