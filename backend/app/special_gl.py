"""GL-conditional special-GL detail validation (spec §4a) — pure, no I/O.

The 6 special-GL groups (ADR-0005, `docs/reference/gl-master.md`) are entered
through a per-group detail subform instead of a plain main-page cell. Two of
them (Entertainment, Lease & Rental) additionally switch their `meta_json`
dropdown OPTIONS by the GL account's suffix — that option list is resolved
here from the GL code, never trusted from the client and never stored per
row (only the chosen value is). Travelling Expense is handled structurally
via `budget_trip` (see write_model.py), not through `meta_json`. The
remaining 3 groups (Professional & Legal Fee, Public Relation & Donation,
Training & Seminar) are NOT GL-conditional per the spec — free-form
`meta_json`, no option-set enforced here.
"""
from typing import Any

SPECIAL_GL_GROUPS: frozenset[str] = frozenset(
    {
        "Entertainment",
        "Lease & Rental",
        "Professional & Legal Fee",
        "Public Relation & Donation",
        "Training & Seminar",
        "Travelling Expense",
    }
)

# --- Entertainment (spec §4a) -----------------------------------------------
_ENTERTAINMENT_EXTERNAL_GLS = frozenset({"5211900030", "6211900030"})
_ENTERTAINMENT_INTERNAL_GLS = frozenset({"6211900031"})
_ENTERTAINMENT_EXTERNAL_VALUES = frozenset({"Customer", "Business partner", "หน่วยงานราชการ", "อื่นๆ"})
_ENTERTAINMENT_INTERNAL_VALUES = frozenset({"พนักงานบริษัท", "กรรมการบริษัท"})

# --- Lease & Rental (spec §4a) ----------------------------------------------
_LEASE_VEHICLE_SUFFIX = "060"
_LEASE_MACHINERY_SUFFIX = "030"
_LEASE_NONVEHICLE_SUFFIXES = frozenset({"010", "020", "040", "050", "999"})

_LEASE_VEHICLE_TYPES = frozenset({"Car", "Van", "Trucks"})
_LEASE_MACHINERY_TYPES = frozenset(
    {
        "Mobile Scalper", "Dumper", "Tractors", "Backhoe", "Forklift", "Tractor",
        "Excavator", "Loader", "Crane", "Water Truck", "Road Sweeper Truck",
    }
)
_LEASE_PLANTS = frozenset({"BK", "TK", "KK", "PB", "RY"})
# The plate dropdown (7 known plates + the "อื่นๆ" sentinel) is a frontend
# CONVENIENCE SHORTCUT, not an allowlist (jakkaritw 2026-07-17): picking
# "อื่นๆ" opens a free-text input and the TYPED plate is what persists, so
# the server accepts any non-empty sane-length string (see
# `_is_valid_free_text_plate`) — but never the sentinel strings themselves.
# Kept here as the fixture-parity anchor for the frontend dropdown
# (test_special_gl_fixture_parity.py) — NOT used to validate.
_LEASE_PLATES = frozenset(
    {"6ขผ-3918", "1นจ-3508", "6ขจ-3513", "5ขง-5712", "1นจ-1468", "6ขผ-8150", "7ขถ-9660", "อื่นๆ"}
)
# "อื่นๆ" = current dropdown sentinel; "ไม่ระบุ" = its pre-2026-07-17 name
# (rejected too so a stale client can never persist it as a plate).
_PLATE_SENTINELS = frozenset({"อื่นๆ", "ไม่ระบุ"})
_MAX_LEN_PLATE = 50  # sane free-text bound; the value lives inside meta_json (no column limit)


class MetaValidationError(ValueError):
    """A `meta_json` value fell outside the GL-resolved dropdown set, or the
    GL code did not resolve to a recognised sub-category at all."""


def _is_valid_free_text_plate(plate: Any) -> bool:
    """ทะเบียนรถ is free text for Vehicles (jakkaritw 2026-07-17): any
    non-empty string within `_MAX_LEN_PLATE` — the 7 known plates pass
    naturally, and so does whatever the user typed after picking "อื่นๆ".
    The sentinel strings themselves ("อื่นๆ", legacy "ไม่ระบุ") are NOT a
    plate — picking one without typing the real plate is invalid."""
    if not isinstance(plate, str):
        return False
    stripped = plate.strip()
    return bool(stripped) and stripped not in _PLATE_SENTINELS and len(plate) <= _MAX_LEN_PLATE


def classify_special_gl(gl_group: str | None) -> str | None:
    """Return `gl_group` unchanged if it is one of the 6 special groups
    (spec §4a / ADR-0005), else None (a normal main-page GL)."""
    return gl_group if gl_group in SPECIAL_GL_GROUPS else None


def validate_entertainment_meta(gl_account: str, meta: dict[str, Any]) -> None:
    """`ประเภทการรับรอง` switches on the 030 (External) / 031 (Internal) GL
    suffix. Nothing chosen yet is a no-op — whether the key is MISSING
    (never touched) or an explicit `''` (bug-entertainment-blank-type-400:
    the frontend's blank placeholder option, or a stale client resetting a
    prior selection) — both mean the same thing to the user, so both must
    be treated identically. Before this fix only `None` was a no-op; `''`
    fell through to the allowed-value check below and raised a raw English
    `MetaValidationError` straight to the UI. The frontend now also blocks
    an empty save client-side (`model.ts`'s `firstUnselectedRequiredField`)
    — this stays permissive server-side as defense-in-depth for any older
    client, never a scary error for "nothing selected"."""
    value = meta.get("ประเภทการรับรอง")
    if not value:
        return
    if gl_account in _ENTERTAINMENT_EXTERNAL_GLS:
        allowed = _ENTERTAINMENT_EXTERNAL_VALUES
    elif gl_account in _ENTERTAINMENT_INTERNAL_GLS:
        allowed = _ENTERTAINMENT_INTERNAL_VALUES
    else:
        raise MetaValidationError(f"{gl_account} is not a recognised Entertainment GL")
    if value not in allowed:
        raise MetaValidationError(f"'{value}' is not a valid ประเภทการรับรอง for GL {gl_account}")


def validate_lease_meta(gl_account: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Validate + clean Lease & Rental's 4 cols. The rental sub-category (GL
    suffix) decides which of `ประเภทรถ` / `ทะเบียนรถ` are enterable vs
    locked/greyed; `สถานที่ใช้งาน` (plant) is a dropdown for every
    sub-category, `กิจกรรม` is always free text, and `ทะเบียนรถ` (Vehicles
    only) is free text — any non-empty sane-length plate, not just the 8
    dropdown shortcuts (jakkaritw 2026-07-17).

    `สถานที่ใช้งาน` and `ประเภทรถ` treat nothing-chosen-yet as a no-op the
    same way `validate_entertainment_meta` does (bug-lease-blank-dropdown-400:
    identical None-vs-'' shape to bug-entertainment-blank-type-400, fixed in
    3852f1b) — whether the key is MISSING (never touched) or an explicit `''`
    (the frontend's blank placeholder option), both mean "nothing chosen yet".
    `ทะเบียนรถ` keeps its OWN stricter rule below (2026-07-17 free-text
    decision, unrelated to this bug): an explicit `''`/whitespace there IS a
    genuinely invalid plate, not "nothing chosen" — it is NOT widened.

    Returns a CLEANED dict with any locked column forced to None, even if the
    caller supplied a stale value for it (a locked column must never persist);
    a blank chosen value normalizes to None the same way a never-touched
    column does.
    """
    suffix = gl_account[-3:]
    plant = meta.get("สถานที่ใช้งาน") or None
    if plant is not None and plant not in _LEASE_PLANTS:
        raise MetaValidationError(f"'{plant}' is not a valid สถานที่ใช้งาน")

    cleaned: dict[str, Any] = {"สถานที่ใช้งาน": plant, "กิจกรรม": meta.get("กิจกรรม")}

    if suffix == _LEASE_VEHICLE_SUFFIX:
        vehicle_type = meta.get("ประเภทรถ") or None
        if vehicle_type is not None and vehicle_type not in _LEASE_VEHICLE_TYPES:
            raise MetaValidationError(f"'{vehicle_type}' is not a valid vehicle ประเภทรถ")
        plate = meta.get("ทะเบียนรถ")
        if plate is not None and not _is_valid_free_text_plate(plate):
            raise MetaValidationError(f"'{plate}' is not a valid ทะเบียนรถ — must be a non-empty plate string (max {_MAX_LEN_PLATE} chars)")
        cleaned["ประเภทรถ"] = vehicle_type
        cleaned["ทะเบียนรถ"] = plate
    elif suffix == _LEASE_MACHINERY_SUFFIX:
        machinery_type = meta.get("ประเภทรถ") or None
        if machinery_type is not None and machinery_type not in _LEASE_MACHINERY_TYPES:
            raise MetaValidationError(f"'{machinery_type}' is not a valid machinery ประเภทรถ")
        cleaned["ประเภทรถ"] = machinery_type
        cleaned["ทะเบียนรถ"] = None  # locked/grey for Machinery
    elif suffix in _LEASE_NONVEHICLE_SUFFIXES:
        cleaned["ประเภทรถ"] = None  # locked/grey
        cleaned["ทะเบียนรถ"] = None  # locked/grey
    else:
        raise MetaValidationError(f"{gl_account} is not a recognised Lease & Rental GL suffix")

    return cleaned
