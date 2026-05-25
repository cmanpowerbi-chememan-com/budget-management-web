# Fabric Notebook: 02nb_bronze_to_silver
# Bronze → Silver: rename, cast, sign-flip, filter
# Paste each ## CELL block as a separate notebook cell

# =============================================================================
## CELL 1 — Imports
# =============================================================================
from pyspark.sql.functions import col, lit, to_date, when, length, left, right, current_date, current_timestamp

# =============================================================================
## CELL 2 — Helpers
# =============================================================================

def sc(df, src, tgt, cast_type=None):
    """Safe column: rename + cast. Returns lit(None) if src not in df."""
    if src in df.columns:
        c = col(src)
        return c.cast(cast_type).alias(tgt) if cast_type else c.alias(tgt)
    return lit(None).cast(cast_type or "string").alias(tgt)


def sign_flip(df, src, tgt, precision=23, scale=2):
    """SAP trailing-minus sign flip: '1234.56-' → -1234.56"""
    dtype = f"decimal({precision},{scale})"
    if src not in df.columns:
        return lit(None).cast(dtype).alias(tgt)
    c = col(src)
    return (
        when(right(c, lit(1)) == "-",
             lit(-1) * left(c, length(c) - 1).cast(dtype))
        .otherwise(c.cast(dtype))
        .alias(tgt)
    )


# =============================================================================
## CELL 3 — bronze_ACDOCA → silver_sap_gl_trans
# =============================================================================

df = spark.table("bronze_ACDOCA").filter(col("RLDNR") == "0L")

silver_gl = df.select(
    # Keys
    sc(df, "RLDNR",              "ledger"),
    sc(df, "BELNR",              "accounting_doc_number"),
    sc(df, "RBUKRS",             "company_code"),
    sc(df, "GJAHR",              "fiscal_year"),
    sc(df, "DOCLN",              "posting_item_number"),
    sc(df, "BUZEI",              "line_item_number"),
    # Reference fields
    sc(df, "BTTYPE",             "business_trans_type"),
    sc(df, "FINSC_BTTYPE_T_TXT", "business_trans_type_desc"),
    sc(df, "AWTYP",              "ref_procedure"),
    sc(df, "AWSYS",              "logical_system"),
    sc(df, "AWORG",              "ref_org_unit"),
    sc(df, "AWREF",              "ref_doc_number"),
    sc(df, "AWITEM",             "ref_doc_line_item"),
    sc(df, "AWITGRP",            "ref_doc_group"),
    sc(df, "BKPF_AWKEY",         "ref_object_key"),
    # Dates
    sc(df, "BUDAT",              "posting_date",   "date"),
    sc(df, "BLDAT",              "doc_date",        "date"),
    sc(df, "BKPF_XBLNR",        "ref_doc_number2"),
    # Currency
    sc(df, "RWCUR",              "trans_curr"),
    sc(df, "RHCUR",              "company_curr"),
    sc(df, "RKCUR",              "group_curr"),
    sc(df, "BKPF_BKTXT",        "doc_text"),
    # Exchange rates (sign-flip)
    sign_flip(df, "BKPF_KURSF", "exchange_rate",       precision=13, scale=5),
    sign_flip(df, "BKPF_KURS2", "group_exchange_rate",  precision=13, scale=5),
    sc(df, "BKPF_KUTY2",        "group_exchange_rate_type"),
    # Document info
    sc(df, "BLART",              "doc_type"),
    sc(df, "T003T_LTEXT",        "doc_type_desc"),
    sc(df, "BKPF_WWERT",        "translation_date"),
    sc(df, "BKPF_TCODE",        "trans_code"),
    sc(df, "BKPF_XREF1_HD",     "ref_key1"),
    sc(df, "BKPF_XREF2_HD",     "ref_key2"),
    # GL
    sc(df, "KTOPL",              "chart_of_accounts"),
    sc(df, "RACCT",              "gl_account_number"),
    sc(df, "GKONT",              "offset_gl_account_number"),
    sc(df, "GKOAR",              "offset_account_type"),
    sc(df, "BSCHL",              "posting_key"),
    sc(df, "BSTAT",              "doc_status"),
    sc(df, "LINETYPE",           "item_category"),
    sc(df, "KTOSL",              "trans_key"),
    sc(df, "USNAM",              "user_name"),
    sc(df, "TIMESTAMP",          "utc_timestamp"),
    sc(df, "GLACCOUNT_TYPE",     "gl_account_type"),
    sc(df, "SGTXT",              "item_text"),
    sc(df, "ZUONR",              "assignment_number"),
    # Purchasing
    sc(df, "RBEST",              "purchase_order_category"),
    sc(df, "EBELN",              "purchase_order_number"),
    sc(df, "EBELP",              "purchase_doc_item_number"),
    # Sales
    sc(df, "KDAUF",              "sales_order_number"),
    sc(df, "KDPOS",              "sales_order_item_number"),
    # Logistics
    sc(df, "MATNR",              "material_number"),
    sc(df, "WERKS",              "plant"),
    sc(df, "LIFNR",              "vendor_number"),
    sc(df, "KUNNR",              "customer_number"),
    # Controlling
    sc(df, "KOKRS",              "controlling_area"),
    sc(df, "PRCTR",              "profit_center"),
    sc(df, "RCNTR",              "cost_center"),
    # Asset
    sc(df, "ANLN1",              "asset_main_number"),
    sc(df, "ANLN2",              "asset_sub_number"),
    sc(df, "BZDAT",              "asset_value_date",    "date"),
    sc(df, "ANBWA",              "asset_trans_type"),
    # Clearing
    sc(df, "XOPVW",              "open_item_flag"),
    sc(df, "AUGDT",              "clearing_date",       "date"),
    sc(df, "AUGBL",              "clearing_doc_number"),
    sc(df, "AUGGJ",              "clearing_fiscal_year"),
    # Tax / account
    sc(df, "MWSKZ",              "tax_on_sales"),
    sc(df, "KOART",              "account_type"),
    sc(df, "DRCRK",              "debit_credit_ind"),
    sc(df, "UMSKZ",              "special_gl_ind"),
    # Payment
    sc(df, "BSEG_ZTERM",         "payment_term_key"),
    sc(df, "ZTERM_T052U_TEXT1",  "payment_term_desc"),
    sc(df, "BSEG_ZFBDT",        "baseline_date",       "date"),
    # Quantities
    sc(df, "CO_MEINH",           "co_unit_measure"),
    sc(df, "CO_MEGBTR",          "co_quantity",         "decimal(23,3)"),
    sc(df, "RUNIT",              "base_unit_measure"),
    sc(df, "MSL",                "quantity",            "decimal(23,3)"),
    # Reversal flags
    sc(df, "XREVERSING",         "reversing_flag"),
    sc(df, "XREVERSED",          "reversed_flag"),
    sc(df, "XTRUEREV",           "true_reversal_flag"),
    sc(df, "AWTYP_REV",          "reversal_ref_trans"),
    sc(df, "AWORG_REV",          "reversal_ref_org"),
    sc(df, "AWREF_REV",          "reversal_ref_doc_number"),
    # Amounts (sign-flip)
    sign_flip(df, "TSL", "balance_trans_amount"),
    sign_flip(df, "WSL", "trans_amount"),
    sign_flip(df, "HSL", "company_curr_amount"),
    sign_flip(df, "KSL", "group_curr_amount"),
    # Control cols
    sc(df, "_load_dt",   "_load_dt"),
    sc(df, "_load_dttm", "_load_dttm"),
    sc(df, "_file_name", "_file_name"),
)

silver_gl.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_sap_gl_trans")
print(f"silver_sap_gl_trans — {spark.table('silver_sap_gl_trans').count():,} rows")


# =============================================================================
## CELL 4 — bronze_sap_m_cost_center → silver_cost_center_master
# =============================================================================

df_cc = spark.table("bronze_sap_m_cost_center")

silver_cc = df_cc.select(
    sc(df_cc, "KOKRS",       "controlling_area_code"),
    sc(df_cc, "KOSTL",       "cost_center_id"),
    sc(df_cc, "CSKT_KTEXT",  "cost_center_name"),
    sc(df_cc, "CSKT_LTEXT",  "cost_center_desc"),
    sc(df_cc, "CSKT_MCTXT",  "cost_center_search_term"),
    sc(df_cc, "DATBI",       "valid_from_date",                    "date"),
    sc(df_cc, "DATAB",       "valid_to_date",                      "date"),
    sc(df_cc, "BKZKP",       "actual_primary_posting_flag"),
    sc(df_cc, "PKZKP",       "plan_primary_cost_flag"),
    sc(df_cc, "BUKRS",       "company_code"),
    sc(df_cc, "GSBER",       "business_area_code"),
    sc(df_cc, "KOSAR",       "cost_center_category_code"),
    sc(df_cc, "TKT05_KTEXT", "cost_center_category_name"),
    sc(df_cc, "VERAK",       "person_responsible_id"),
    sc(df_cc, "WAERS",       "currency_code"),
    sc(df_cc, "PRCTR",       "profit_center_id"),
    sc(df_cc, "ERSDA",       "record_created_date",                "date"),
    sc(df_cc, "USNAM",       "created_by"),
    sc(df_cc, "BKZKS",       "actual_secondary_cost_flag"),
    sc(df_cc, "BKZER",       "actual_revenue_posting_flag"),
    sc(df_cc, "BKZOB",       "commitment_update_flag"),
    sc(df_cc, "PKZKS",       "plan_secondary_cost_flag"),
    sc(df_cc, "PKZER",       "plan_revenue_flag"),
    sc(df_cc, "VMETH",       "allow_allocation_method_flag"),
    sc(df_cc, "MGEFL",       "recording_consumption_quantity_flag"),
    sc(df_cc, "KHINR",       "hierarchy_area_code"),
    # Control cols
    sc(df_cc, "_load_dt",    "_load_dt"),
    sc(df_cc, "_load_dttm",  "_load_dttm"),
    sc(df_cc, "_file_name",  "_file_name"),
)

silver_cc.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_cost_center_master")
print(f"silver_cost_center_master — {spark.table('silver_cost_center_master').count():,} rows")


# =============================================================================
## CELL 5 — Inspect bronze_sap_m_internal_order schema first
# =============================================================================

spark.table("bronze_sap_m_internal_order").printSchema()
spark.table("bronze_sap_m_internal_order").limit(3).show(truncate=False)


# =============================================================================
## CELL 6 — bronze_sap_m_internal_order → silver_internal_order_master
# (run AFTER cell 5 — adjust col names if different from AUFNR/KTEXT)
# =============================================================================

df_io = spark.table("bronze_sap_m_internal_order")

# Map the 2 key cols — adjust src names based on cell 5 output if needed
ORDER_COL     = "AUFNR"   # ← change if printSchema shows different name
SHORTTEXT_COL = "KTEXT"   # ← change if printSchema shows different name

silver_io = df_io.select(
    sc(df_io, ORDER_COL,      "order_number"),
    sc(df_io, SHORTTEXT_COL,  "order_short_text"),
    sc(df_io, "_load_dt",     "_load_dt"),
    sc(df_io, "_load_dttm",   "_load_dttm"),
    sc(df_io, "_file_name",   "_file_name"),
)

silver_io.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_internal_order_master")
print(f"silver_internal_order_master — {spark.table('silver_internal_order_master').count():,} rows")
