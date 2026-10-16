"""Option B — CLI Entry Point.

Usage:
  python -m option_b.main --validate --transform --output
  python -m option_b.main --validate
  python -m option_b.main --revalidate --record-key KEY --table TABLE
"""
import argparse
import sys
import uuid
from pathlib import Path

from pyspark.sql import SparkSession


def create_spark_session() -> SparkSession:
    """Create SparkSession in local mode for POC."""
    return (
        SparkSession.builder
        .master("local[1]")
        .appName("option_b_engine")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .config("spark.python.worker.faulthandler.enabled", "true")
        .config("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true")
        .config("spark.python.worker.reuse", "false")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .getOrCreate()
    )


def main():
    parser = argparse.ArgumentParser(description="Option B Config-Driven Validation Engine")
    parser.add_argument("--validate", action="store_true", help="Run validation phase")
    parser.add_argument("--transform", action="store_true", help="Run transformation phase")
    parser.add_argument("--output", action="store_true", help="Run output phase")
    parser.add_argument("--revalidate", action="store_true", help="Run targeted revalidation")
    parser.add_argument("--record-key", type=str, help="Record key for targeted revalidation")
    parser.add_argument("--table", type=str, help="Table for targeted revalidation")
    parser.add_argument("--template-dir", type=str, default="templates/v1", help="Template directory")
    parser.add_argument("--output-dir", type=str, default="output", help="Output directory")
    
    args = parser.parse_args()
    
    if not (args.validate or args.transform or args.output or args.revalidate):
        parser.print_help()
        sys.exit(1)
    
    # Initialize Spark
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        from option_b.config.template_loader import load_template
        from option_b.engine.validation_orchestrator import run_validation
        from option_b.engine.transformation_executor import transform
        from option_b.audit.execution_audit import record_audit_trail
        
        # Load template
        print(f"[TEMPLATE] Loading template from: {args.template_dir}")
        template = load_template(args.template_dir)
        print(f"[TEMPLATE] Loaded: {len(template['validation_rules'])} rules, "
              f"{len(template['transformation_mappings'])} mappings, version {template['version']}")
        
        staging_config = {"staging_dir": "staging_data", "format": "csv"}
        run_id = str(uuid.uuid4())[:8]
        tables_processed = []
        record_counts = {}
        outputs_produced = []
        
        if args.revalidate:
            # Targeted revalidation mode
            from option_b.error.targeted_revalidation import revalidate
            if not args.record_key or not args.table:
                print("ERROR: --revalidate requires --record-key and --table")
                sys.exit(1)
            result = revalidate(spark, template, staging_config, args.table, args.record_key, args.output_dir)
            print(f"[REVAL] {result['message']}")
            sys.exit(0)
        
        validated_dfs = {}
        
        if args.validate:
            validated_dfs = run_validation(spark, template, staging_config, args.output_dir)
            tables_processed = list(validated_dfs.keys())
            for t, df in validated_dfs.items():
                record_counts[t] = df.count()
        
        if args.transform and validated_dfs:
            transformed_df = transform(template, validated_dfs)
            if transformed_df is not None:
                if args.output:
                    # Import flat file adapter (registers itself)
                    import option_b.output.flat_file_adapter  # noqa: F401
                    import option_b.output.csv_file_adapter  # noqa: F401
                    from option_b.output.adapter_registry import get_adapter
                    
                    for oc in template.get("output_config", []):
                        adapter = get_adapter(oc["adapter_type"])
                        output_path = adapter.format_and_deliver(
                            transformed_df, oc, template["transformation_mappings"]
                        )
                        if output_path:
                            outputs_produced.append(output_path)
        
        # Write audit trail
        record_audit_trail(run_id, template["version"], "cli", tables_processed, record_counts, outputs_produced, args.output_dir)
        
        print(f"\n[DONE] Pipeline completed successfully.")
        
    except Exception as e:
        print(f"\n[ENGINE] FATAL: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
