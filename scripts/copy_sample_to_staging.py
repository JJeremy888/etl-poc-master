"""Copy sample data files to staging_data/ with correct names.

Mapping:
  sample_data/sample_cnt.csv -> staging_data/cnt.csv
  sample_data/sample_cvg.csv -> staging_data/cvg.csv
  sample_data/sample_rol.csv -> staging_data/rol.csv
  sample_data/sample_add.csv -> staging_data/add.csv
"""
import shutil
from pathlib import Path


def copy_sample_to_staging(project_root: Path | None = None) -> None:
    """Copy sample data CSV files into staging_data/ directory."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    sample_dir = project_root / "sample_data"
    staging_dir = project_root / "staging_data"
    staging_dir.mkdir(exist_ok=True)

    mappings = {
        "sample_cnt.csv": "cnt.csv",
        "sample_cvg.csv": "cvg.csv",
        "sample_rol.csv": "rol.csv",
        "sample_add.csv": "add.csv",
    }

    for source_name, target_name in mappings.items():
        source = sample_dir / source_name
        target = staging_dir / target_name
        if not source.exists():
            print(f"  [SKIP] {source} not found")
            continue
        shutil.copy2(source, target)
        print(f"  [OK] {source_name} -> staging_data/{target_name}")

    print("Done. Staging data populated.")


if __name__ == "__main__":
    copy_sample_to_staging()
