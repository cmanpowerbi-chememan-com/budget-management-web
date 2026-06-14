# Fabric Notebook: 02nb_b_s_bronze_sap_m_cost_center
# Purpose: bronze_sap_m_cost_center → silver_sap_m_cost_center
# Mapping spec: 05CMAN-DataPlatform_Mapping_Specification_V0.0.4.xlsx
#               sheet "Silver-Master table cost_center_master"
# Paste each ## CELL block as a separate notebook cell

# =============================================================================
## CELL 1 — Imports
# =============================================================================
from pyspark.sql.functions import col, lit, to_date

# =============================================================================
## CELL 2 — Helpers
# =============================================================================

def sc(df, src, tgt, cast_type=None):
    """Safe column: rename + cast. SAP date strings are yyyyMMdd — cast("date") fails on them."""
    if src in df.columns:
        c = col(src)
        if cast_type == "date":
            return to_date(c, "yyyyMMdd").alias(tgt)
        return c.cast(cast_type).alias(tgt) if cast_type else c.alias(tgt)
    return lit(None).cast(cast_type or "string").alias(tgt)

# =============================================================================
## CELL 3 — Transform: bronze_sap_m_cost_center → silver_sap_m_cost_center
# =============================================================================

df = spark.table("bronze_sap_m_cost_center")

silver_cc = df.select(
    sc(df, "KOKRS",       "controlling_area_code"),
    sc(df, "KOSTL",       "cost_center_id"),
    sc(df, "CSKT_KTEXT",  "cost_center_name"),
    sc(df, "CSKT_LTEXT",  "cost_center_desc"),
    sc(df, "CSKT_MCTXT",  "cost_center_search_term"),
    sc(df, "DATBI",       "valid_from_date",                        "date"),
    sc(df, "DATAB",       "valid_to_date",                          "date"),
    sc(df, "BKZKP",       "actual_primary_posting_flag"),
    sc(df, "PKZKP",       "plan_primary_cost_flag"),
    sc(df, "BUKRS",       "company_code"),
    sc(df, "GSBER",       "business_area_code"),
    sc(df, "KOSAR",       "cost_center_category_code"),
    sc(df, "TKT05_KTEXT", "cost_center_category_name"),
    sc(df, "VERAK",       "person_responsible_id"),
    sc(df, "WAERS",       "currency_code"),
    sc(df, "PRCTR",       "profit_center_id"),
    sc(df, "ERSDA",       "record_created_date",                    "date"),
    sc(df, "USNAM",       "created_by"),
    sc(df, "BKZKS",       "actual_secondary_cost_flag"),
    sc(df, "BKZER",       "actual_revenue_posting_flag"),
    sc(df, "BKZOB",       "commitment_update_flag"),
    sc(df, "PKZKS",       "plan_secondary_cost_flag"),
    sc(df, "PKZER",       "plan_revenue_flag"),
    sc(df, "VMETH",       "allow_allocation_method_flag"),
    sc(df, "MGEFL",       "recording_consumption_quantity_flag"),
    sc(df, "KHINR",       "hierarchy_area_code"),
    # Control cols
    sc(df, "_load_dt",    "_load_dt"),
    sc(df, "_load_dttm",  "_load_dttm"),
    sc(df, "_file_name",  "_file_name"),
)

# =============================================================================
## CELL 4 — Write & Verify
# =============================================================================

silver_cc.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("silver_sap_m_cost_center")

bronze_cnt = spark.table("bronze_sap_m_cost_center").count()
silver_cnt = spark.table("silver_sap_m_cost_center").count()
print(f"bronze_sap_m_cost_center : {bronze_cnt:,} rows")
print(f"silver_sap_m_cost_center : {silver_cnt:,} rows")
assert silver_cnt == bronze_cnt, f"Row count mismatch! bronze={bronze_cnt} silver={silver_cnt}"
print("Row counts match")

# =============================================================================
## CELL 5 — Verify: row count / column types / null counts / distinct counts
# =============================================================================
from pyspark.sql import functions as F

bronze = spark.table("bronze_sap_m_cost_center")
silver = spark.table("silver_sap_m_cost_center")

mapping = [
    ("KOKRS",       "controlling_area_code",                 "string"),
    ("KOSTL",       "cost_center_id",                        "string"),
    ("CSKT_KTEXT",  "cost_center_name",                      "string"),
    ("CSKT_LTEXT",  "cost_center_desc",                      "string"),
    ("CSKT_MCTXT",  "cost_center_search_term",               "string"),
    ("DATBI",       "valid_from_date",                       "date"),
    ("DATAB",       "valid_to_date",                         "date"),
    ("BKZKP",       "actual_primary_posting_flag",           "string"),
    ("PKZKP",       "plan_primary_cost_flag",                "string"),
    ("BUKRS",       "company_code",                          "string"),
    ("GSBER",       "business_area_code",                    "string"),
    ("KOSAR",       "cost_center_category_code",             "string"),
    ("TKT05_KTEXT", "cost_center_category_name",             "string"),
    ("VERAK",       "person_responsible_id",                 "string"),
    ("WAERS",       "currency_code",                         "string"),
    ("PRCTR",       "profit_center_id",                      "string"),
    ("ERSDA",       "record_created_date",                   "date"),
    ("USNAM",       "created_by",                            "string"),
    ("BKZKS",       "actual_secondary_cost_flag",            "string"),
    ("BKZER",       "actual_revenue_posting_flag",           "string"),
    ("BKZOB",       "commitment_update_flag",                "string"),
    ("PKZKS",       "plan_secondary_cost_flag",              "string"),
    ("PKZER",       "plan_revenue_flag",                     "string"),
    ("VMETH",       "allow_allocation_method_flag",          "string"),
    ("MGEFL",       "recording_consumption_quantity_flag",   "string"),
    ("KHINR",       "hierarchy_area_code",                   "string"),
    ("_load_dt",    "_load_dt",                              "date"),
    ("_load_dttm",  "_load_dttm",                            "timestamp"),
    ("_file_name",  "_file_name",                            "string"),
]

silver_dtypes = dict(silver.dtypes)

# ── 1. Row count ──────────────────────────────────────────
b_cnt = bronze.count()
s_cnt = silver.count()
print("=" * 65)
print("1. ROW COUNT")
print(f"   bronze : {b_cnt:,}")
print(f"   silver : {s_cnt:,}")
print(f"   {'✅ match' if b_cnt == s_cnt else '❌ MISMATCH'}")

# ── 2. Column exist + type ────────────────────────────────
print("\n" + "=" * 65)
print("2. COLUMN EXIST + TYPE")
print(f"   {'silver column':<35} {'exist':>5}  {'actual type':<12} {'expect':<10} {'ok':>3}")
print("   " + "-" * 65)
for _, s_col, exp in mapping:
    exists  = s_col in silver_dtypes
    actual  = silver_dtypes.get(s_col, "—")
    type_ok = actual.startswith(exp) if exists else False
    flag    = "✅" if (exists and type_ok) else "❌"
    note    = "" if type_ok else "⚠️ type mismatch" if exists else "⚠️ missing"
    print(f"   {s_col:<35} {'✅' if exists else '❌':>5}  {actual:<12} {exp:<10} {flag}  {note}")

# ── 3. Non-null count per column ──────────────────────────
print("\n" + "=" * 65)
print("3. NON-NULL COUNT  (bronze → silver)")
print(f"   {'bronze col':<18}  {'silver col':<35} {'bronze':>7} {'silver':>7}  ok")
print("   " + "-" * 72)
for b_col, s_col, _ in mapping:
    b_nn = bronze.filter(F.col(b_col).isNotNull()).count()
    if s_col not in silver_dtypes:
        print(f"   {b_col:<18}  {s_col:<35} {b_nn:>7} {'—':>7}  ❌ col missing")
        continue
    s_nn = silver.filter(F.col(s_col).isNotNull()).count()
    ok   = "✅" if b_nn == s_nn else "❌"
    print(f"   {b_col:<18}  {s_col:<35} {b_nn:>7} {s_nn:>7}  {ok}")

# ── 4. Distinct count per column ─────────────────────────
print("\n" + "=" * 65)
print("4. DISTINCT COUNT  (bronze → silver)")
print(f"   {'bronze col':<18}  {'silver col':<35} {'bronze':>7} {'silver':>7}  ok")
print("   " + "-" * 72)
for b_col, s_col, _ in mapping:
    b_dc = bronze.select(F.col(b_col)).distinct().count()
    if s_col not in silver_dtypes:
        print(f"   {b_col:<18}  {s_col:<35} {b_dc:>7} {'—':>7}  ❌ col missing")
        continue
    s_dc = silver.select(F.col(s_col)).distinct().count()
    ok   = "✅" if b_dc == s_dc else "❌"
    print(f"   {b_col:<18}  {s_col:<35} {b_dc:>7} {s_dc:>7}  {ok}")
