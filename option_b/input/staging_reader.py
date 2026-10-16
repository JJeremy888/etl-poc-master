"""Staging Reader — Read staging tables into DataFrames.

POC: reads from CSV files in staging_data/.
Production: would read from Glue Data Catalog / JDBC.
"""
from pathlib import Path
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import StructType


def read_staging_table(spark: SparkSession, table_name: str, config: dict) -> DataFrame:
    """Read a staging table. Config determines source type.
    
    POC config: {"staging_dir": "staging_data/", "format": "csv"}
    """
    staging_dir = Path(config.get("staging_dir", "staging_data"))
    file_format = config.get("format", "csv")
    
    filepath = staging_dir / f"{table_name.lower()}.{file_format}"
    
    if not filepath.exists():
        print(f"[STAGING] WARNING: Table {table_name} not found at {filepath} — returning empty DataFrame")
        return spark.createDataFrame([], StructType([]))
    
    df = spark.read.option("header", "true").option("inferSchema", "false").csv(str(filepath))
    
    row_count = df.count()
    if row_count == 0:
        print(f"[STAGING] WARNING: Table {table_name} is empty at {filepath}")
    else:
        print(f"[STAGING] Reading {table_name} from {filepath} — {row_count} records")
    
    return df


def read_all_staging_tables(spark: SparkSession, table_names: list[str], config: dict) -> dict[str, DataFrame]:
    """Read all required staging tables into a dict of DataFrames."""
    result = {}
    for table_name in table_names:
        result[table_name] = read_staging_table(spark, table_name, config)
    return result
