"""Shared test fixtures for Option B test suite."""

import os
import tempfile
import shutil

import pytest

# Fix PySpark PermissionError on Windows with Python 3.14
# Must set temp dirs BEFORE importing SparkSession
_spark_tmp = os.path.join(
    os.path.dirname(__file__), "..", "..", "spark_tmp"
)
os.makedirs(_spark_tmp, exist_ok=True)
os.environ["TMPDIR"] = _spark_tmp
os.environ["TEMP"] = _spark_tmp
os.environ["TMP"] = _spark_tmp
tempfile.tempdir = _spark_tmp

from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark():
    """Session-scoped SparkSession for testing (local[2])."""
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("OptionB_Tests")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .config("spark.ui.enabled", "false")
        .config("spark.local.dir", _spark_tmp)
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test outputs."""
    d = tempfile.mkdtemp(dir=_spark_tmp)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def template_dir(tmp_dir):
    """Create a minimal template directory structure for testing."""
    # Copy actual templates if available, otherwise create minimal ones
    src_templates = os.path.join(
        os.path.dirname(__file__), "..", "..", "templates"
    )
    if os.path.exists(src_templates):
        dst = os.path.join(tmp_dir, "templates")
        shutil.copytree(src_templates, dst)
        return os.path.join(dst, "v1")
    return None


@pytest.fixture
def staging_dir(tmp_dir):
    """Create a staging directory with test data."""
    staging = os.path.join(tmp_dir, "staging_data")
    os.makedirs(staging, exist_ok=True)

    # Copy actual staging data if available
    src_staging = os.path.join(
        os.path.dirname(__file__), "..", "..", "staging_data"
    )
    if os.path.exists(src_staging):
        for f in os.listdir(src_staging):
            src_file = os.path.join(src_staging, f)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, staging)

    return staging
