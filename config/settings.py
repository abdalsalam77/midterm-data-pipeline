import os
from pathlib import Path


# ==========================================
# PROJECT PATHS
# ==========================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

REPORTS_DIR = PROJECT_ROOT / "reports"

SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"


# ==========================================
# FILE ROUTER SETTINGS
# ==========================================

# الملفات التي حجمها أقل من أو يساوي هذا الحد
# تتم معالجتها باستخدام Python Batch.
# الملفات الأكبر تتم معالجتها باستخدام PySpark.
SMALL_FILE_THRESHOLD_MB = int(
    os.getenv(
        "SMALL_FILE_THRESHOLD_MB",
        "200",
    )
)


# ==========================================
# PYTHON BATCH SETTINGS
# ==========================================

# عدد السجلات في كل Batch للـ Python loader.
BATCH_SIZE = int(
    os.getenv(
        "BATCH_SIZE",
        "5000",
    )
)


# ==========================================
# MONGODB SETTINGS
# ==========================================

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017",
)

MONGO_DATABASE = os.getenv(
    "MONGO_DATABASE",
    "midterm_data_pipeline",
)


# ==========================================
# MONGODB COLLECTIONS
# ==========================================

ORDERS_RAW_COLLECTION = "orders_raw"

ORDERS_VALIDATED_COLLECTION = "orders_validated"

ORDERS_QUARANTINE_COLLECTION = "orders_quarantine"

CORRECTION_AUDIT_COLLECTION = "correction_audit"


# ==========================================
# SPARK GENERAL SETTINGS
# ==========================================

SPARK_APP_NAME = os.getenv(
    "SPARK_APP_NAME",
    "MidtermDataPipeline",
)

# local[*] = استخدام جميع الأنوية المنطقية
# المتاحة في الجهاز.
SPARK_MASTER = os.getenv(
    "SPARK_MASTER",
    "local[*]",
)


# ==========================================
# SPARK PARALLELISM SETTINGS
# ==========================================

# جهازك يحتوي على 12 logical CPU cores.
#
# هذا الإعداد يستخدم كـ default parallelism
# للعمليات التي تحتاج Spark لتحديد مستوى التوازي.
SPARK_DEFAULT_PARALLELISM = int(
    os.getenv(
        "SPARK_DEFAULT_PARALLELISM",
        "12",
    )
)


# ==========================================
# SPARK FILE PARTITION SETTINGS
# ==========================================

SPARK_FILES_MAX_PARTITION_BYTES = int(
    os.getenv(
        "SPARK_FILES_MAX_PARTITION_BYTES",
        str(64 * 1024 * 1024),
    )
)

SPARK_FILES_MIN_PARTITION_NUM = int(
    os.getenv(
        "SPARK_FILES_MIN_PARTITION_NUM",
        "12",
    )
)


# ==========================================
# SPARK MONGODB WRITE SETTINGS
# ==========================================

# عدد السجلات التي يجمعها كل Spark worker
# قبل تنفيذ عملية كتابة جماعية في MongoDB.
SPARK_MONGO_BATCH_SIZE = int(
    os.getenv(
        "SPARK_MONGO_BATCH_SIZE",
        "10000",
    )
)


# ==========================================
# SPARK PYTHON WORKER SETTINGS
# ==========================================

# إعادة استخدام Python workers تقلل تكلفة
# إنشاء Python process جديد لكل task.
SPARK_PYTHON_WORKER_REUSE = os.getenv(
    "SPARK_PYTHON_WORKER_REUSE",
    "true",
)

# يساعد في إظهار traceback أفضل عند تعطل
# Python worker.
SPARK_PYTHON_WORKER_FAULTHANDLER = os.getenv(
    "SPARK_PYTHON_WORKER_FAULTHANDLER",
    "true",
)


# ==========================================
# SPARK MEMORY SETTINGS
# ==========================================

# ذاكرة Spark Driver.
SPARK_DRIVER_MEMORY = os.getenv(
    "SPARK_DRIVER_MEMORY",
    "4g",
)

# ذاكرة Spark Executor.
#
# في local[*] يكون التنفيذ محليًا،
# لذلك لا ترفع هذه القيمة أعلى من RAM جهازك.
SPARK_EXECUTOR_MEMORY = os.getenv(
    "SPARK_EXECUTOR_MEMORY",
    "4g",
)


# ==========================================
# SPARK STABILITY SETTINGS
# ==========================================

# زيادة timeout لتقليل مشاكل الاتصال
# أثناء معالجة الملف الكبير.
SPARK_NETWORK_TIMEOUT = os.getenv(
    "SPARK_NETWORK_TIMEOUT",
    "600s",
)

# heartbeat للـ executor.
SPARK_EXECUTOR_HEARTBEAT_INTERVAL = os.getenv(
    "SPARK_EXECUTOR_HEARTBEAT_INTERVAL",
    "60s",
)


# ==========================================
# FILE SETTINGS
# ==========================================

DEFAULT_ENCODING = os.getenv(
    "DEFAULT_ENCODING",
    "utf-8",
)

CSV_DELIMITER = os.getenv(
    "CSV_DELIMITER",
    ",",
)


# ==========================================
# REPORT FILES
# ==========================================

RESULTS_JSON_PATH = (
    REPORTS_DIR / "results.json"
)

RESULTS_MD_PATH = (
    REPORTS_DIR / "results.md"
)