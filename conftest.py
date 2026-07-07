"""Session-wide pytest setup.

Stubs `pyspark` when the real package isn't installed, so unit tests can
exercise Spark-adjacent code paths (schema construction, type references,
`AnalysisException` handling) without requiring a full PySpark + JVM install
in the local/dev/CI environment. Databricks notebooks and jobs always have
the real pyspark available; this stub only activates when it's genuinely
absent, and never overrides an already-installed or already-stubbed pyspark.

Lives at the repo root (not under tests/ or eval/retrieval/tests/) so it
loads before any test module is collected, regardless of collection order —
a per-directory conftest or a stub embedded in one test file would only
protect modules collected after it.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace


def _install_pyspark_stub() -> None:
    try:
        import pyspark  # noqa: F401

        return  # real pyspark is installed — nothing to stub
    except ImportError:
        pass

    if "pyspark" in sys.modules:
        return  # something already stubbed it — don't clobber

    pyspark_mod = types.ModuleType("pyspark")
    sql_mod = types.ModuleType("pyspark.sql")
    types_mod = types.ModuleType("pyspark.sql.types")
    utils_mod = types.ModuleType("pyspark.sql.utils")

    class DataType:
        """Base for stubbed scalar/complex pyspark.sql.types.* classes.

        Each concrete type below is its own distinct subclass (not a single
        shared stand-in) because production code does real `isinstance`
        dispatch on these (e.g. `eval/retrieval/scripts/apply_ops_ddl.py`'s
        `_spark_type_to_ddl`), not just constructor calls.
        """

        def __eq__(self, other):
            return type(self) is type(other)

        def __hash__(self):
            return hash(type(self))

        def __repr__(self):
            return f"{type(self).__name__}()"

    class StringType(DataType):
        pass

    class BooleanType(DataType):
        pass

    class IntegerType(DataType):
        pass

    class LongType(DataType):
        pass

    class DoubleType(DataType):
        pass

    class FloatType(DataType):
        pass

    class DateType(DataType):
        pass

    class TimestampType(DataType):
        pass

    class ArrayType(DataType):
        def __init__(self, elementType, containsNull: bool = True):
            self.elementType = elementType
            self.containsNull = containsNull

    class StructField:
        def __init__(self, name, dataType, nullable: bool = True, metadata=None):
            self.name = name
            self.dataType = dataType
            self.nullable = nullable
            self.metadata = metadata or {}

    class StructType:
        def __init__(self, fields=None):
            self.fields = fields or []

    class SparkSession:
        @staticmethod
        def getActiveSession():
            return None

    class AnalysisException(Exception):
        """Stand-in for pyspark.sql.utils.AnalysisException."""

    types_mod.DataType = DataType
    types_mod.StringType = StringType
    types_mod.BooleanType = BooleanType
    types_mod.IntegerType = IntegerType
    types_mod.LongType = LongType
    types_mod.DoubleType = DoubleType
    types_mod.FloatType = FloatType
    types_mod.DateType = DateType
    types_mod.TimestampType = TimestampType
    types_mod.ArrayType = ArrayType
    types_mod.StructField = StructField
    types_mod.StructType = StructType

    sql_mod.SparkSession = SparkSession
    sql_mod.Row = lambda **kwargs: SimpleNamespace(**kwargs)
    sql_mod.types = types_mod
    sql_mod.utils = utils_mod
    utils_mod.AnalysisException = AnalysisException
    pyspark_mod.sql = sql_mod

    sys.modules["pyspark"] = pyspark_mod
    sys.modules["pyspark.sql"] = sql_mod
    sys.modules["pyspark.sql.types"] = types_mod
    sys.modules["pyspark.sql.utils"] = utils_mod


_install_pyspark_stub()
