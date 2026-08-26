import argparse
import os
import sys
import time
import uuid
import traceback
from collections import Counter
from pymongo.errors import DuplicateKeyError
from pyspark.sql import SparkSession

from pyspark.sql.types import (
    StringType,
    StructField,
    StructType,
)


from config.settings import (
    CSV_DELIMITER,
    DEFAULT_ENCODING,
    SPARK_APP_NAME,
    SPARK_MASTER,
    SPARK_DEFAULT_PARALLELISM,
    SPARK_FILES_MAX_PARTITION_BYTES,
    SPARK_FILES_MIN_PARTITION_NUM,
    SPARK_MONGO_BATCH_SIZE,
    SPARK_PYTHON_WORKER_REUSE,
    SPARK_PYTHON_WORKER_FAULTHANDLER,
    SPARK_DRIVER_MEMORY,
    SPARK_EXECUTOR_MEMORY,
    SPARK_NETWORK_TIMEOUT,
    SPARK_EXECUTOR_HEARTBEAT_INTERVAL,
)

from src.mongo_setup import (
    get_worker_database,
    initialize_mongodb,
)

from src.metrics import (
    build_metrics,
    save_metrics,
    print_metrics_summary,
)
# ============================================================
# SPARK CSV SCHEMA
# ============================================================

CSV_SCHEMA = StructType([
    StructField("order_id", StringType(), True),
    StructField("order_date", StringType(), True),
    StructField("status", StringType(), True),
    StructField("customer_id", StringType(), True),
    StructField("customer_name", StringType(), True),
    StructField("customer_phone", StringType(), True),
    StructField("customer_email", StringType(), True),
    StructField("city", StringType(), True),
    StructField("district", StringType(), True),
    StructField("delivery_type", StringType(), True),
    StructField("delivery_cost", StringType(), True),
    StructField("payment_method", StringType(), True),
    StructField("payment_status", StringType(), True),
    StructField("payment_amount", StringType(), True),
    StructField("currency", StringType(), True),
    StructField("total_amount", StringType(), True),
    StructField("items_json", StringType(), True),
])


# ============================================================
# SETTINGS
# ============================================================

WRITE_BATCH_SIZE = SPARK_MONGO_BATCH_SIZE


# ============================================================
# SPARK SESSION
# ============================================================

def create_spark_session():
    """
    Create SparkSession with explicit Python executable
    and stability settings.
    """

    python_executable = sys.executable

    os.environ["PYSPARK_PYTHON"] = python_executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = python_executable

    spark = (
        SparkSession.builder
        .appName(SPARK_APP_NAME)
        .master(SPARK_MASTER)

        .config(
            "spark.pyspark.python",
            python_executable,
        )

        .config(
            "spark.pyspark.driver.python",
            python_executable,
        )

        .config(
            "spark.default.parallelism",
            SPARK_DEFAULT_PARALLELISM,
        )

        .config(
            "spark.files.maxPartitionBytes",
            SPARK_FILES_MAX_PARTITION_BYTES,
        )

        .config(
            "spark.files.minPartitionNum",
            SPARK_FILES_MIN_PARTITION_NUM,
        )

        .config(
            "spark.driver.memory",
            SPARK_DRIVER_MEMORY,
        )

        .config(
            "spark.executor.memory",
            SPARK_EXECUTOR_MEMORY,
        )

        .config(
            "spark.python.worker.reuse",
            SPARK_PYTHON_WORKER_REUSE,
        )

        .config(
            "spark.python.worker.faulthandler.enabled",
            SPARK_PYTHON_WORKER_FAULTHANDLER,
        )

        .config(
            "spark.sql.execution.pyspark.udf.faulthandler.enabled",
            SPARK_PYTHON_WORKER_FAULTHANDLER,
        )

        .config(
            "spark.network.timeout",
            SPARK_NETWORK_TIMEOUT,
        )

        .config(
            "spark.executor.heartbeatInterval",
            SPARK_EXECUTOR_HEARTBEAT_INTERVAL,
        )

        .config(
            "spark.task.maxFailures",
            "1",
        )

        .getOrCreate()
    )

    return spark


# ============================================================
# NORMALIZE ORDER ID FOR DUPLICATE DETECTION
# ============================================================

def normalize_order_id_value(value):
    """
    Normalize order_id only for duplicate detection.

    Original raw values are never changed.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    arabic_digits = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩",
        "0123456789",
    )

    return value.translate(arabic_digits)


# ============================================================
# PROCESS ONE SPARK PARTITION
# ============================================================

def process_partition(
    rows,
    run_id,
    source_file,
    partition_id,
):
    """
    Process one Spark partition.

    Every record:
        1. Enters orders_raw first.
        2. Goes through quality classification.
        3. Ends exactly once as:
           valid / corrected / quarantine.

    Same-run duplicate detection is handled without
    a Spark Window or Shuffle.
    """

    from pymongo import UpdateOne

    from src.batch_loader import (
        build_raw_document,
        build_validated_document,
        build_quarantine_document,
        build_duplicate_quarantine_document,
        build_correction_audit_documents,
        business_document,
    )

    from src.elt_pipeline import process_record

    client = None

    raw_batch = []
    validated_documents = []
    quarantine_batch = []
    audit_batch = []

    counters = {
        "rows_read": 0,
        "raw_loaded": 0,
        "valid_count": 0,
        "corrected_count": 0,
        "quarantine_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
    }

    error_counts = Counter()

    partition_start = time.perf_counter()

    try:

        # ====================================================
        # WORKER MONGODB CONNECTION
        # ====================================================

        client, db = get_worker_database()

        orders_raw = db["orders_raw"]
        orders_validated = db["orders_validated"]
        orders_quarantine = db["orders_quarantine"]
        correction_audit = db["correction_audit"]
        run_order_ids = db["run_order_ids"]

        
        # ====================================================
        # FLUSH RAW
        # ====================================================

        def flush_raw():

            if not raw_batch:
                return

            documents = list(raw_batch)

            orders_raw.insert_many(
                documents,
                ordered=False,
            )

            counters["raw_loaded"] += len(documents)

            raw_batch.clear()

        # ====================================================
        # FLUSH QUARANTINE
        # ====================================================

        def flush_quarantine():

            if not quarantine_batch:
                return

            documents = list(quarantine_batch)

            orders_quarantine.insert_many(
                documents,
                ordered=False,
            )

            quarantine_batch.clear()

        # ====================================================
        # FLUSH AUDIT
        # ====================================================

        def flush_audit():

            if not audit_batch:
                return

            documents = list(audit_batch)

            correction_audit.insert_many(
                documents,
                ordered=False,
            )

            audit_batch.clear()

        # ====================================================
        # FLUSH VALIDATED
        #
        # UPSERT + IDEMPOTENCY
        # ====================================================

        def flush_validated():

            if not validated_documents:
                return

            documents_to_write = list(
                validated_documents
            )

            validated_documents.clear()

            if not documents_to_write:
                return

            # ================================================
            # NORMALIZE BUSINESS KEYS
            # ================================================

            order_ids = []

            for document in documents_to_write:

                normalized_id = (
                    normalize_order_id_value(
                        document.get("order_id")
                    )
                )

                document["_normalized_order_id"] = (
                    normalized_id
                )

                if normalized_id:

                    order_ids.append(
                        normalized_id
                    )

            # ================================================
            # GET EXISTING BUSINESS RECORDS
            # ================================================

            existing_documents = list(
                orders_validated.find(
                    {
                        "order_id": {
                            "$in": order_ids
                        }
                    }
                )
            )

            existing_by_order_id = {
                normalize_order_id_value(
                    document.get("order_id")
                ): document
                for document in existing_documents
            }

            operations = []

            expected_updated = 0
            expected_unchanged = 0

            # ================================================
            # PROCESS EACH VALIDATED DOCUMENT
            # ================================================

            for document in documents_to_write:

                order_id = document.get(
                    "order_id"
                )

                normalized_order_id = (
                    document.pop(
                        "_normalized_order_id",
                        None,
                    )
                )

                # ============================================
                # MISSING / EMPTY ORDER ID
                #
                # Safety fallback.
                # ============================================

                if not normalized_order_id:

                    counters[
                        "quarantine_count"
                    ] += 1

                    counters[
                        "valid_count"
                    ] -= (
                        1
                        if document.get(
                            "quality_status"
                        ) == "valid"
                        else 0
                    )

                    counters[
                        "corrected_count"
                    ] -= (
                        1
                        if document.get(
                            "quality_status"
                        ) == "corrected"
                        else 0
                    )

                    error_code = (
                        "MISSING_ORDER_ID"
                    )

                    error_counts[
                        error_code
                    ] += 1

                    quarantine_batch.append(
                        build_duplicate_quarantine_document(
                            raw_record=document,
                            run_id=run_id,
                            source_file=source_file,
                            source_row_number=(
                                document.get(
                                    "source_row_number"
                                )
                            ),
                            order_id=None,
                        )
                    )

                    continue

                # ============================================
                # EXISTING RECORD
                # ============================================

                existing = (
                    existing_by_order_id.get(
                        normalized_order_id
                    )
                )

                # ============================================
                # NEW RECORD
                # ============================================

                if existing is None:

                    operations.append(
                        UpdateOne(
                            {
                                "order_id": order_id
                            },
                            {
                                "$setOnInsert": document,
                                "$addToSet": {
                                    "run_ids": run_id
                                },
                            },
                            upsert=True,
                        )
                    )

                    existing_by_order_id[
                        normalized_order_id
                    ] = document

                    continue

                existing_business = (
                    business_document(
                        existing
                    )
                )

                new_business = (
                    business_document(
                        document
                    )
                )

                # ============================================
                # UNCHANGED
                # ============================================

                if (
                    existing_business
                    == new_business
                ):

                    operations.append(
                        UpdateOne(
                            {
                                "order_id": existing[
                                    "order_id"
                                ]
                            },
                            {
                                "$addToSet": {
                                    "run_ids": run_id
                                }
                            },
                            upsert=False,
                        )
                    )

                    expected_unchanged += 1

                # ============================================
                # UPDATED
                # ============================================

                else:

                    document_without_run_ids = {
                        key: value
                        for key, value in document.items()
                        if key != "run_ids"
                    }

                    operations.append(
                        UpdateOne(
                            {
                                "order_id": existing[
                                    "order_id"
                                ]
                            },
                            {
                                "$set": (
                                    document_without_run_ids
                                ),
                                "$addToSet": {
                                    "run_ids": run_id
                                },
                            },
                            upsert=False,
                        )
                    )

                    expected_updated += 1

                    existing_by_order_id[
                        normalized_order_id
                    ] = document

            # ================================================
            # EXECUTE UPSERTS
            # ================================================

            if operations:

                write_result = (
                    orders_validated.bulk_write(
                        operations,
                        ordered=False,
                    )
                )

                counters[
                    "inserted_count"
                ] += (
                    write_result.upserted_count
                )

                counters[
                    "updated_count"
                ] += expected_updated

                counters[
                    "unchanged_count"
                ] += expected_unchanged

        # ====================================================
        # PROCESS ROWS
        # ====================================================

        for local_index, row in enumerate(
            rows,
            start=1,
        ):

            row_dict = row.asDict(
                recursive=True
            )

            counters["rows_read"] += 1

            source_row_number = (
                f"{partition_id}:{local_index}"
            )

            # =================================================
            # BUILD RAW DOCUMENT
            # =================================================

            raw_document = build_raw_document(
                raw_record=row_dict,
                run_id=run_id,
                source_file=source_file,
                source_row_number=source_row_number,
            )

            raw_batch.append(
                raw_document
            )

            # =================================================
            # RAW FIRST GUARANTEE
            # =================================================

            if (
                len(raw_batch)
                >= WRITE_BATCH_SIZE
            ):

                flush_raw()

            # =================================================
            # GLOBAL SAME-RUN DUPLICATE DETECTION
            #
            # MongoDB unique index guarantees duplicate
            # detection across all Spark partitions.
            # =================================================

            normalized_order_id = (
                normalize_order_id_value(
                    row_dict.get("order_id")
                )
            )

            if normalized_order_id:

                try:

                    run_order_ids.insert_one(
                        {
                            "run_id": run_id,
                            "normalized_order_id": (
                                normalized_order_id
                            ),
                        }
                    )

                except DuplicateKeyError:

                    counters[
                        "quarantine_count"
                    ] += 1

                    error_code = (
                        "DUPLICATE_ORDER_ID"
                    )

                    error_counts[
                        error_code
                    ] += 1

                    quarantine_batch.append(
                        build_duplicate_quarantine_document(
                            raw_record=row_dict,
                            run_id=run_id,
                            source_file=source_file,
                            source_row_number=(
                                source_row_number
                            ),
                            order_id=normalized_order_id,
                        )
                    )

                    if (
                        len(quarantine_batch)
                        >= WRITE_BATCH_SIZE
                    ):

                        flush_quarantine()

                    continue

            # =================================================
            # QUALITY PIPELINE
            # =================================================

            try:

                result = process_record(
                    row_dict
                )

            except Exception as error:

                error_code = (
                    "PROCESSING_EXCEPTION"
                )

                error_counts[
                    error_code
                ] += 1

                result = {
                    "final_status": "quarantine",
                    "record": None,
                    "error_codes": [
                        error_code
                    ],
                    "error_details": [
                        {
                            "message": str(error),
                            "traceback": (
                                traceback.format_exc()
                            ),
                        }
                    ],
                }

            final_status = result.get(
                "final_status"
            )

            # =================================================
            # VALID
            # =================================================

            if final_status in (
                "valid",
                "validated",
            ):

                counters[
                    "valid_count"
                ] += 1

                validated_documents.append(
                    build_validated_document(
                        record=result["record"],
                        source_file=source_file,
                        source_row_number=(
                            source_row_number
                        ),
                        final_status="valid",
                    )
                )

            # =================================================
            # CORRECTED
            # =================================================

            elif final_status == "corrected":

                counters[
                    "corrected_count"
                ] += 1

                validated_documents.append(
                    build_validated_document(
                        record=result["record"],
                        source_file=source_file,
                        source_row_number=(
                            source_row_number
                        ),
                        final_status="corrected",
                    )
                )

                audit_documents = (
                    build_correction_audit_documents(
                        corrections=result.get(
                            "corrections",
                            [],
                        ),
                        corrected_record=(
                            result["record"]
                        ),
                        run_id=run_id,
                    )
                )

                audit_batch.extend(
                    audit_documents
                )

            # =================================================
            # QUARANTINE
            # =================================================

            else:

                counters[
                    "quarantine_count"
                ] += 1

                error_codes = result.get(
                    "error_codes",
                    [],
                )

                if not error_codes:

                    error_codes = [
                        "UNKNOWN_CLASSIFICATION_ERROR"
                    ]

                    result["error_codes"] = (
                        error_codes
                    )

                    result["error_details"] = [
                        (
                            "Record was quarantined "
                            "without a specific error code."
                        )
                    ]

                for error_code in error_codes:

                    error_counts[
                        error_code
                    ] += 1

                quarantine_batch.append(
                    build_quarantine_document(
                        result=result,
                        raw_record=row_dict,
                        run_id=run_id,
                        source_file=source_file,
                        source_row_number=(
                            source_row_number
                        ),
                    )
                )

            # =================================================
            # FLUSH VALIDATED
            # =================================================

            if (
                len(validated_documents)
                >= WRITE_BATCH_SIZE
            ):

                flush_validated()

            # =================================================
            # FLUSH QUARANTINE
            # =================================================

            if (
                len(quarantine_batch)
                >= WRITE_BATCH_SIZE
            ):

                flush_quarantine()

            # =================================================
            # FLUSH AUDIT
            # =================================================

            if (
                len(audit_batch)
                >= WRITE_BATCH_SIZE
            ):

                flush_audit()

        # ====================================================
        # FINAL FLUSH
        # ====================================================

        flush_raw()

        flush_validated()

        flush_quarantine()

        flush_audit()

        partition_elapsed = (
            time.perf_counter()
            - partition_start
        )

        partition_throughput = (
            counters["rows_read"]
            / partition_elapsed
            if partition_elapsed > 0
            else 0
        )

        # ====================================================
        # RETURN ONLY SMALL METRICS
        # ====================================================

        yield {
            **counters,
            "partition_id": partition_id,
            "partition_elapsed_seconds": (
                partition_elapsed
            ),
            "partition_throughput": (
                partition_throughput
            ),
            "error_case_counts": dict(
                error_counts
            ),
        }

    except Exception:

        print(
            "\n"
            + "=" * 68
        )
        print(
            "SPARK WORKER ERROR"
        )
        print(
            "=" * 68
        )
        print(
            f"Partition ID : {partition_id}"
        )
        print(
            "-" * 68
        )
        print(
            traceback.format_exc()
        )
        print(
            "=" * 68
            + "\n"
        )

        raise

    finally:

        if client is not None:

            try:
                client.close()

            except Exception:
                pass


# ============================================================
# LOAD LARGE CSV WITH SPARK
# ============================================================

def load_csv_with_spark(
    file_path,
    run_id,
):
    """
    Process a large CSV using real Spark distributed
    processing.

    The CSV is read using Spark DataFrame API.
    No Pandas is used.
    No repartition() is used.
    No global Window-based duplicate detection is used.
    """

    # ========================================================
    # WINDOWS PATH FIX
    # ========================================================

    file_path = str(file_path)
    
    file_size_mb = (
        os.path.getsize(file_path)
        / (1024 * 1024)
        )
    
    spark = None
    setup_client = None

    total_start = time.perf_counter()

    totals = {
        "rows_read": 0,
        "raw_loaded": 0,
        "valid_count": 0,
        "corrected_count": 0,
        "quarantine_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
    }

    total_error_counts = Counter()

    source_file = file_path

    partitions = None

    partition_metrics = []

    print("\n" + "=" * 72)
    print("                 PYSPARK DATA PIPELINE")
    print("=" * 72)

    print(f"Run ID           : {run_id}")
    print(f"Input File       : {file_path}")
    print(f"Spark Master     : {SPARK_MASTER}")
    print(f"Write Batch Size : {WRITE_BATCH_SIZE}")

    print("-" * 72)

    print("PIPELINE")
    print(
        "CSV -> Spark DataFrame -> orders_raw -> "
        "Validation -> Valid / Corrected / Quarantine"
    )

    print("-" * 72)

    print("EXECUTION SETTINGS")
    print("Raw-first policy          : ENABLED")
    print("Spark DataFrame API       : ENABLED")
    print("Pandas                    : DISABLED")
    print("repartition()             : NOT USED")
    print("Global Window Shuffle     : DISABLED")
    print(
        "Duplicate detection       : "
    "MongoDB global same-run unique index"
    )

    print("-" * 72)

    print(
        "Partition max bytes       : "
        f"{SPARK_FILES_MAX_PARTITION_BYTES}"
    )
    print(
        "Minimum partition number  : "
        f"{SPARK_FILES_MIN_PARTITION_NUM}"
    )

    print("=" * 72)

    try:

        # ====================================================
        # INITIALIZE MONGODB ONCE
        # ====================================================

        print(
            "\n[1/4] Preparing MongoDB collections and indexes..."
        )

        setup_client, _ = (
            initialize_mongodb()
        )

        setup_client.close()

        setup_client = None

        print(
            "[OK] MongoDB setup completed successfully."
        )

        # ====================================================
        # START SPARK
        # ====================================================

        print(
            "\n[2/4] Starting Spark session..."
        )

        spark = create_spark_session()

        spark.sparkContext.setLogLevel(
            "WARN"
        )

        print(
            "[OK] Spark session started successfully."
        )

        # ====================================================
        # READ CSV USING DATAFRAME API
        # ====================================================

        print(
            "\n[3/4] Reading large CSV with Spark DataFrame API..."
        )

        print(
            "[INFO] File loading and partition preparation in progress..."
        )

        df = (
            spark.read
            .option("header", "true")
            .option(
                "delimiter",
                CSV_DELIMITER,
            )
            .option(
                "encoding",
                DEFAULT_ENCODING,
            )
            .option("quote", '"')
            .option("escape", '"')
            .option("multiLine", "false")
            .option("mode", "PERMISSIVE")
            .schema(CSV_SCHEMA)
            .csv(file_path)
        )

        print(
            "[OK] CSV loaded into Spark DataFrame."
        )

        # ====================================================
        # PARTITION INFORMATION
        # ====================================================

        partitions = (
            df.rdd.getNumPartitions()
        )

        default_parallelism = (
            spark.sparkContext
            .defaultParallelism
        )

        print(
            "\nSPARK EXECUTION DETAILS"
        )
        print("-" * 72)

        print(
            f"Spark Partitions         : {partitions}"
        )

        print(
            f"Default Parallelism       : "
            f"{default_parallelism}"
        )

        print(
            f"Write Batch Size          : "
            f"{WRITE_BATCH_SIZE}"
        )

        print("-" * 72)

        print(
            "\n[4/4] Distributed processing started..."
        )

        print(
            "[INFO] Spark workers are currently processing partitions."
        )

        print(
            "[INFO] Loading raw records, validating data, "
            "applying safe corrections, and quarantining invalid records..."
        )

        # ====================================================
        # DISTRIBUTED PROCESSING
        #
        # collect() returns only one small metrics dictionary
        # from each partition.
        # ====================================================

        partition_results = (
            df.rdd
            .mapPartitionsWithIndex(
                lambda partition_id, rows:
                process_partition(
                    rows=rows,
                    run_id=run_id,
                    source_file=source_file,
                    partition_id=partition_id,
                )
            )
            .collect()
        )

        print(
            "\n[OK] Distributed processing completed."
        )

        print(
            "[INFO] Aggregating partition metrics..."
        )

        # ====================================================
        # AGGREGATE RESULTS
        # ====================================================

        for result in partition_results:

            partition_metrics.append(
                {
                    "partition_id": result.get(
                        "partition_id"
                    ),
                    "rows_read": result.get(
                        "rows_read",
                        0,
                    ),
                    "elapsed_seconds": result.get(
                        "partition_elapsed_seconds",
                        0,
                    ),
                    "throughput": result.get(
                        "partition_throughput",
                        0,
                    ),
                }
            )

            for key in totals:

                totals[key] += result.get(
                    key,
                    0,
                )

            total_error_counts.update(
                result.get(
                    "error_case_counts",
                    {},
                )
            )

        print(
            "[OK] Partition metrics aggregated successfully."
        )

    finally:

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        if setup_client is not None:

            try:
                setup_client.close()

            except Exception:
                pass

        if spark is not None:

            try:

                print(
                    "\n[INFO] Stopping Spark session..."
                )

                spark.stop()

                print(
                    "[OK] Spark session stopped successfully."
                )

            except Exception as error:

                print(
                    f"[WARNING] "
                    f"Spark stop failed: {error}"
                )

    # ========================================================
    # FINAL METRICS
    # ========================================================

    totals["elapsed_seconds"] = (
        total_elapsed
    )

    totals["batch_count"] = None

    totals["partitions"] = partitions

    totals["partition_metrics"] = (
        partition_metrics
    )

    totals["throughput"] = (
        totals["rows_read"]
        / total_elapsed
        if total_elapsed > 0
        else 0
    )

    totals["error_case_counts"] = dict(
        total_error_counts
    )

    totals["classified_count"] = (
        totals["valid_count"]
        + totals["corrected_count"]
        + totals["quarantine_count"]
    )

    # ========================================================
    # CONSISTENCY CHECK
    # ========================================================

    totals["consistency_ok"] = (
        totals["raw_loaded"]
        == totals["classified_count"]
    )

    totals["consistency_diff"] = (
        totals["raw_loaded"]
        - totals["classified_count"]
    )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print("\n" + "=" * 72)
    print("                 PIPELINE EXECUTION SUMMARY")
    print("=" * 72)

    print("\nDATA LOADING")
    print("-" * 72)
    print(
        f"Rows Read               : "
        f"{totals['rows_read']}"
    )
    print(
        f"Raw Records Loaded      : "
        f"{totals['raw_loaded']}"
    )

    print("\nDATA QUALITY RESULTS")
    print("-" * 72)
    print(
        f"Valid                   : "
        f"{totals['valid_count']}"
    )
    print(
        f"Corrected               : "
        f"{totals['corrected_count']}"
    )
    print(
        f"Quarantine              : "
        f"{totals['quarantine_count']}"
    )

    print("\nUPSERT RESULTS")
    print("-" * 72)
    print(
        f"Inserted                : "
        f"{totals['inserted_count']}"
    )
    print(
        f"Updated                 : "
        f"{totals['updated_count']}"
    )
    print(
        f"Unchanged               : "
        f"{totals['unchanged_count']}"
    )

    print("\nSPARK PERFORMANCE")
    print("-" * 72)
    print(
        f"Partitions              : "
        f"{totals['partitions']}"
    )
    print(
        f"Total Time              : "
        f"{total_elapsed:.2f} seconds"
    )
    print(
        f"Overall Throughput      : "
        f"{totals['throughput']:.2f} rows/second"
    )

    print("\nCONSISTENCY CHECK")
    print("-" * 72)

    if totals["consistency_ok"]:

        print(
            "[PASS] raw_loaded = "
            "valid + corrected + quarantine"
        )

    else:

        print(
            "[WARNING] Consistency mismatch detected!"
        )

        print(
            f"Raw Loaded             : "
            f"{totals['raw_loaded']}"
        )

        print(
            f"Classified Total        : "
            f"{totals['classified_count']}"
        )

        print(
            f"Difference              : "
            f"{totals['consistency_diff']}"
        )

    print("\n" + "=" * 72)

    if totals["consistency_ok"]:

        print(
            "PYSPARK PIPELINE FINISHED SUCCESSFULLY"
        )

    else:

        print(
            "PYSPARK PIPELINE FINISHED WITH CONSISTENCY WARNING"
        )

    print("=" * 72 + "\n")
    # ========================================================
# BUILD AND SAVE METRICS
# ========================================================

    metrics = build_metrics(
        run_id=run_id,
        file_name=os.path.basename(
            file_path
        ),
        file_size_mb=file_size_mb,
        engine_used="pyspark",

        rows_read=totals[
            "rows_read"
        ],

        raw_loaded=totals[
            "raw_loaded"
        ],

        valid_count=totals[
            "valid_count"
        ],

        corrected_count=totals[
            "corrected_count"
        ],

        quarantine_count=totals[
            "quarantine_count"
        ],

        elapsed_seconds=totals[
            "elapsed_seconds"
        ],
        batch_size=WRITE_BATCH_SIZE,
        partitions=partitions,

        error_case_counts=totals[
            "error_case_counts"
        ],

        inserted_count=totals[
            "inserted_count"
        ],

        updated_count=totals[
            "updated_count"
        ],

        unchanged_count=totals[
            "unchanged_count"
        ],

        extra_metrics={
            "partition_metrics":
                partition_metrics,
        },
    )

    save_metrics(
        metrics
    )

    print_metrics_summary(
        metrics
    )
    return totals
    

# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Load a large CSV using PySpark."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV file",
    )

    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run ID",
    )

    args = parser.parse_args()

    run_id = (
        args.run_id
        if args.run_id
        else str(uuid.uuid4())
    )

    load_csv_with_spark(
        file_path=args.input,
        run_id=run_id,
    )