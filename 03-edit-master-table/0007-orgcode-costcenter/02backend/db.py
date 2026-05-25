"""Spark session and helper for Fabric Lakehouse Delta tables.

Identical across all entities in the master-table skill.
"""
import os
from functools import lru_cache
from pyspark.sql import SparkSession


@lru_cache(maxsize=1)
def spark() -> SparkSession:
    """Get the singleton Spark session bound to Fabric."""
    return (
        SparkSession.builder
        .appName("master-table-admin")
        .config(
            "spark.sql.catalog.fabric",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.databricks.delta.schema.autoMerge.enabled", "false")
        .getOrCreate()
    )


def exists(table: str, where_clause: str, params: dict) -> bool:
    """Return True if at least one row matches.

    Used for the Fail Fast duplicate check before MERGE.
    For composite PK, where_clause should include ALL pk columns.
    """
    sql = f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1"
    df = spark().sql(sql, **params)
    return df.count() > 0
