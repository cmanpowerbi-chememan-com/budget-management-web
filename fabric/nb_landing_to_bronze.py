# Fabric Notebook: nb_landing_to_bronze
# Read files from Files/00landing → write to Bronze Delta tables
# Run in: Fabric Notebook (attach lakehouse: lakehouse)

from pyspark.sql.functions import current_date, current_timestamp, col

# ── Config ────────────────────────────────────────────────────────────────────

WORKSPACE  = "budget_management_web"
LAKEHOUSE  = "lakehouse"
BASE_PATH  = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE}.Lakehouse"
LANDING    = f"{BASE_PATH}/Files/00landing"

FILES = [
    {
        "file":         "SAP_T_GL_TRANS_1000_RATIMA_TEST1.TXT",
        "delimiter":    "|",
        "header":       True,
        "target_table": "bronze_ACDOCA",
    },
    {
        "file":         "SAP_M_COST_CENTER.TXT",
        "delimiter":    "|",
        "header":       True,
        "target_table": "bronze_sap_m_cost_center",
    },
    {
        "file":         "SAP_M_INTERNAL_ORDER.TXT",
        "delimiter":    "|",
        "header":       True,
        "target_table": "bronze_sap_m_internal_order",
    },
]

# ── Functions ─────────────────────────────────────────────────────────────────

def read_from_landing(file_path: str, delimiter: str, header: bool):
    return (
        spark.read.format("csv")
        .option("header", header)
        .option("delimiter", delimiter)
        .option("inferSchema", False)          # all strings — safe for bronze
        .option("multiLine", False)
        .load(file_path)
        .withColumn("_load_dt",   current_date())
        .withColumn("_load_dttm", current_timestamp())
        .withColumn("_file_name", col("_metadata.file_name"))
        .withColumn("_file_path", col("_metadata.file_path"))
        .withColumn("_file_size", col("_metadata.file_size"))
        .withColumn("_file_mod",  col("_metadata.file_modification_time"))
    )


def load_to_bronze(df, target_table: str):
    (
        df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target_table)
    )
    count = spark.table(target_table).count()
    print(f"  ✓ {target_table}  →  {count:,} rows")


# ── Run ───────────────────────────────────────────────────────────────────────

for cfg in FILES:
    file_path = f"{LANDING}/{cfg['file']}"
    print(f"\nProcessing: {cfg['file']}")

    df = read_from_landing(file_path, cfg["delimiter"], cfg["header"])
    print(f"  Read OK  — {df.columns[:5]}...")  # preview first 5 col names

    load_to_bronze(df, cfg["target_table"])

print("\nAll files loaded to bronze.")
