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
_LEASE_PLATES = frozenset(
    {"6ขผ-3918", "1นจ-3508", "6ขจ-3513", "5ขง-5712", "1นจ-1468", "6ขผ-8150", "7ขถ-9660", "ไม่ระบุ"}
)


class MetaValidationError(ValueError):
    """A `meta_json` value fell outside the GL-resolved dropdown set, or the
    GL code did not resolve to a recognised sub-category at all."""


def classify_special_gl(gl_group: str | None) -> str | None:
    """Return `gl_group` unchanged if it is one of the 6 special groups
    (spec §4a / ADR-0005), else None (a normal main-page GL)."""
    return gl_group if gl_group in SPECIAL_GL_GROUPS else None


def validate_entertainment_meta(gl_account: str, meta: dict[str, Any]) -> None:
    """`ประเภทการรับรอง` switches on the 030 (External) / 031 (Internal) GL
    suffix. A missing key is a no-op (nothing chosen yet)."""
    value = meta.get("ประเภทการรับรอง")
    if value is None:
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
    suffix) decides which of `ประเภทรถ` / `ทะเบียนรถ` are dropdowns vs
    locked/greyed; `สถานที่ใช้งาน` (plant) is a dropdown for every
    sub-category and `กิจกรรม` is always free text.

    Returns a CLEANED dict with any locked column forced to None, even if the
    caller supplied a stale value for it (a locked column must never persist).
    """
    suffix = gl_account[-3:]
    plant = meta.get("สถานที่ใช้งาน")
    if plant is not None and plant not in _LEASE_PLANTS:
        raise MetaValidationError(f"'{plant}' is not a valid สถานที่ใช้งาน")

    cleaned: dict[str, Any] = {"สถานที่ใช้งาน": plant, "กิจกรรม": meta.get("กิจกรรม")}

    if suffix == _LEASE_VEHICLE_SUFFIX:
        vehicle_type = meta.get("ประเภทรถ")
        if vehicle_type is not None and vehicle_type not in _LEASE_VEHICLE_TYPES:
            raise MetaValidationError(f"'{vehicle_type}' is not a valid vehicle ประเภทรถ")
        plate = meta.get("ทะเบียนรถ")
        if plate is not None and plate not in _LEASE_PLATES:
            raise MetaValidationError(f"'{plate}' is not a valid ทะเบียนรถ")
        cleaned["ประเภทรถ"] = vehicle_type
        cleaned["ทะเบียนรถ"] = plate
    elif suffix == _LEASE_MACHINERY_SUFFIX:
        machinery_type = meta.get("ประเภทรถ")
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
