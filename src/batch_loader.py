import csv
import time
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from config.settings import BATCH_SIZE
from src.mongo_setup import initialize_mongodb
from src.elt_pipeline import process_record
from src.metrics import (
    build_metrics,
    save_metrics,
    print_metrics_summary,
)


# ============================================================
# TIME
# ============================================================

def utc_now():
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# ============================================================
# RAW DOCUMENT
# ============================================================

def build_raw_document(
    raw_record,
    run_id,
    source_file,
    source_row_number,
    ingested_at=None,
):
    """
    Build document for orders_raw.

    No cleaning, validation, correction, or transformation
    happens before the record reaches orders_raw.
    """

    if ingested_at is None:
        ingested_at = utc_now()

    return {
        "run_id": run_id,
        "source_file": source_file,
        "source_row_number": source_row_number,
        "ingested_at": ingested_at,
        "engine_used": "python_batch",
        "raw_record": raw_record,
    }


# ============================================================
# VALIDATED DOCUMENT
# ============================================================

def build_validated_document(
    record,
    source_file,
    source_row_number,
    final_status,
    processed_at=None,
):
    """
    Build final business document.

    quality_status:
    - valid
    - corrected
    """

    if processed_at is None:
        processed_at = utc_now()

    document = dict(record)

    document.update({
        "quality_status": final_status,
        "source_file": source_file,
        "source_row_number": source_row_number,
        "processed_at": processed_at,
    })

    document.pop("run_id", None)
    document.pop("run_ids", None)

    return document


# ============================================================
# QUARANTINE DOCUMENT
# ============================================================

def build_quarantine_document(
    result,
    raw_record,
    run_id,
    source_file,
    source_row_number,
    quarantined_at=None,
):
    """Build document for orders_quarantine."""

    if quarantined_at is None:
        quarantined_at = utc_now()

    return {
        "run_id": run_id,
        "source_file": source_file,
        "source_row_number": source_row_number,
        "quarantined_at": quarantined_at,
        "error_codes": result.get("error_codes", []),
        "error_details": result.get("error_details", []),
        "raw_record": raw_record,
    }


# ============================================================
# DUPLICATE QUARANTINE
# ============================================================

def build_duplicate_quarantine_document(
    raw_record,
    run_id,
    source_file,
    source_row_number,
    order_id,
    quarantined_at=None,
):
    """
    Build quarantine document for duplicate order_id
    found inside the same run.
    """

    if quarantined_at is None:
        quarantined_at = utc_now()

    return {
        "run_id": run_id,
        "source_file": source_file,
        "source_row_number": source_row_number,
        "quarantined_at": quarantined_at,
        "error_codes": [
            "DUPLICATE_ORDER_ID",
        ],
        "error_details": [
            f"Duplicate order_id '{order_id}' "
            f"found within the same run."
        ],
        "raw_record": raw_record,
    }


# ============================================================
# CORRECTION AUDIT
# ============================================================

def build_correction_audit_documents(
    corrections,
    corrected_record,
    run_id,
    corrected_at=None,
):
    """
    Build one audit document for every corrected field.
    """

    if corrected_at is None:
        corrected_at = utc_now()

    order_id = corrected_record.get("order_id")

    return [
        {
            "run_id": run_id,
            "order_id": order_id,
            "field": correction.get("field"),
            "original_value": correction.get("original_value"),
            "corrected_value": correction.get(
                "corrected_value"
            ),
            "rule_code": correction.get("rule_code"),
            "corrected_at": corrected_at,
        }
        for correction in corrections
    ]


# ============================================================
# DUPLICATE CHECK
# ============================================================

def normalize_order_id_for_duplicate_check(raw_record):
    """
    Normalize order_id only for duplicate detection.

    The original raw record is NEVER modified.
    """

    value = raw_record.get("order_id")

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
# BUSINESS DOCUMENT
# ============================================================

def business_document(document):
    """
    Return only business data.

    Processing metadata is removed before comparison.

    This ensures idempotency:
    the same business record in another run remains unchanged.
    """

    ignored_fields = {
        "_id",
        "run_id",
        "run_ids",
        "source_file",
        "source_row_number",
        "processed_at",
    }

    return {
        key: value
        for key, value in document.items()
        if key not in ignored_fields
    }


# ============================================================
# BULK UPSERT
# ============================================================

def bulk_upsert_documents(
    orders_validated,
    final_documents,
    run_id,
):
    """
    Upsert validated documents.

    Classification:
    - inserted
    - updated
    - unchanged
    """

    if not final_documents:
        return {
            "inserted_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
        }

    order_ids = [
        document["order_id"]
        for document in final_documents
    ]

    existing_documents = orders_validated.find(
        {
            "order_id": {
                "$in": order_ids,
            }
        }
    )

    existing_by_order_id = {
        document["order_id"]: document
        for document in existing_documents
    }

    operations = []

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0

    for document in final_documents:

        order_id = document["order_id"]

        existing = existing_by_order_id.get(
            order_id
        )

        # ====================================================
        # NEW RECORD
        # ====================================================

        if existing is None:

            insert_document = dict(document)

            operations.append(
                UpdateOne(
                    {
                        "order_id": order_id,
                    },
                    {
                        "$setOnInsert": insert_document,
                        "$addToSet": {
                            "run_ids": run_id,
                        },
                    },
                    upsert=True,
                )
            )

            inserted_count += 1
            continue

        existing_business = business_document(
            existing
        )

        new_business = business_document(
            document
        )

        # ====================================================
        # UNCHANGED
        # ====================================================

        if existing_business == new_business:

            operations.append(
                UpdateOne(
                    {
                        "order_id": order_id,
                    },
                    {
                        "$addToSet": {
                            "run_ids": run_id,
                        }
                    },
                    upsert=False,
                )
            )

            unchanged_count += 1

        # ====================================================
        # UPDATED
        # ====================================================

        else:

            operations.append(
                UpdateOne(
                    {
                        "order_id": order_id,
                    },
                    {
                        "$set": document,
                        "$addToSet": {
                            "run_ids": run_id,
                        },
                    },
                    upsert=False,
                )
            )

            updated_count += 1

    if operations:

        try:

            orders_validated.bulk_write(
                operations,
                ordered=False,
            )

        except PyMongoError as error:

            print(
                f"[ERROR] Bulk upsert failed: "
                f"{error}"
            )

            raise

    return {
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
    }


# ============================================================
# PROCESS BATCH
# ============================================================

def process_batch(
    batch,
    db,
    run_id,
    source_file,
    batch_number,
    seen_order_ids,
):
    """
    Process one batch.

    Flow:

    CSV
      ↓
    orders_raw
      ↓
    Duplicate Check
      ↓
    Validation
      ↓
    Valid / Corrected / Quarantine
      ↓
    orders_validated
    orders_quarantine
    correction_audit
    """

    orders_raw = db["orders_raw"]
    orders_validated = db["orders_validated"]
    orders_quarantine = db["orders_quarantine"]
    correction_audit = db["correction_audit"]

    batch_start = time.perf_counter()

    # ========================================================
    # 1. RAW LOAD FIRST
    # ========================================================

    ingested_at = utc_now()

    raw_documents = [
        build_raw_document(
            raw_record=item["record"],
            run_id=run_id,
            source_file=source_file,
            source_row_number=item["row_number"],
            ingested_at=ingested_at,
        )
        for item in batch
    ]

    try:

        orders_raw.insert_many(
            raw_documents,
            ordered=False,
        )

        raw_loaded = len(raw_documents)

    except PyMongoError as error:

        print(
            f"[ERROR] Batch {batch_number} "
            f"failed during Raw Load: {error}"
        )

        raise

    # ========================================================
    # 2. PROCESS RECORDS
    # ========================================================

    final_documents = []
    quarantine_documents = []
    audit_documents = []

    valid_count = 0
    corrected_count = 0
    quarantine_count = 0

    error_case_counts = Counter()

    processed_at = utc_now()

    for item in batch:

        raw_record = item["record"]
        row_number = item["row_number"]

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        order_id_for_check = (
            normalize_order_id_for_duplicate_check(
                raw_record
            )
        )

        if (
            order_id_for_check is not None
            and order_id_for_check in seen_order_ids
        ):

            quarantine_count += 1

            error_case_counts[
                "DUPLICATE_ORDER_ID"
            ] += 1

            quarantine_documents.append(
                build_duplicate_quarantine_document(
                    raw_record=raw_record,
                    run_id=run_id,
                    source_file=source_file,
                    source_row_number=row_number,
                    order_id=order_id_for_check,
                    quarantined_at=processed_at,
                )
            )

            continue

        # ----------------------------------------------------
        # REGISTER ORDER ID
        # ----------------------------------------------------

        if order_id_for_check is not None:

            seen_order_ids.add(
                order_id_for_check
            )

        # ----------------------------------------------------
        # ELT PIPELINE
        # ----------------------------------------------------

        result = process_record(
            raw_record
        )

        final_status = result.get(
            "final_status"
        )

        # ====================================================
        # VALID
        # ====================================================

        if final_status in (
            "valid",
            "validated",
        ):

            valid_count += 1

            document = build_validated_document(
                record=result["record"],
                source_file=source_file,
                source_row_number=row_number,
                final_status="valid",
                processed_at=processed_at,
            )

            final_documents.append(
                document
            )

        # ====================================================
        # CORRECTED
        # ====================================================

        elif final_status == "corrected":

            corrected_count += 1

            document = build_validated_document(
                record=result["record"],
                source_file=source_file,
                source_row_number=row_number,
                final_status="corrected",
                processed_at=processed_at,
            )

            final_documents.append(
                document
            )

            audit_documents.extend(
                build_correction_audit_documents(
                    corrections=result.get(
                        "corrections",
                        [],
                    ),
                    corrected_record=result[
                        "record"
                    ],
                    run_id=run_id,
                    corrected_at=processed_at,
                )
            )

        # ====================================================
        # QUARANTINE
        # ====================================================

        else:

            quarantine_count += 1

            error_codes = result.get(
                "error_codes",
                [],
            )

            if not error_codes:

                error_codes = [
                    "UNKNOWN_CLASSIFICATION_ERROR"
                ]

                result["error_codes"] = error_codes

                result["error_details"] = [
                    "Record was quarantined without "
                    "a specific error code."
                ]

            for error_code in error_codes:

                error_case_counts[
                    error_code
                ] += 1

            quarantine_documents.append(
                build_quarantine_document(
                    result=result,
                    raw_record=raw_record,
                    run_id=run_id,
                    source_file=source_file,
                    source_row_number=row_number,
                    quarantined_at=processed_at,
                )
            )

    # ========================================================
    # 3. BULK UPSERT
    # ========================================================

    upsert_result = bulk_upsert_documents(
        orders_validated=orders_validated,
        final_documents=final_documents,
        run_id=run_id,
    )

    # ========================================================
    # 4. QUARANTINE INSERT
    # ========================================================

    if quarantine_documents:

        try:

            orders_quarantine.insert_many(
                quarantine_documents,
                ordered=False,
            )

        except PyMongoError as error:

            print(
                f"[ERROR] Batch {batch_number} "
                f"failed during Quarantine insert: "
                f"{error}"
            )

            raise

    # ========================================================
    # 5. CORRECTION AUDIT INSERT
    # ========================================================

    if audit_documents:

        try:

            correction_audit.insert_many(
                audit_documents,
                ordered=False,
            )

        except PyMongoError as error:

            print(
                f"[ERROR] Batch {batch_number} "
                f"failed during Audit insert: "
                f"{error}"
            )

            raise

    # ========================================================
    # 6. BATCH METRICS
    # ========================================================

    batch_elapsed = (
        time.perf_counter()
        - batch_start
    )

    throughput = (
        len(batch) / batch_elapsed
        if batch_elapsed > 0
        else 0
    )

    return {
        "rows_read": len(batch),
        "raw_loaded": raw_loaded,
        "valid_count": valid_count,
        "corrected_count": corrected_count,
        "quarantine_count": quarantine_count,
        "inserted_count": upsert_result[
            "inserted_count"
        ],
        "updated_count": upsert_result[
            "updated_count"
        ],
        "unchanged_count": upsert_result[
            "unchanged_count"
        ],
        "elapsed_seconds": batch_elapsed,
        "throughput": throughput,
        "error_case_counts": dict(
            error_case_counts
        ),
    }


# ============================================================
# CSV STREAMING LOADER
# ============================================================

def load_csv_in_batches(
    file_path,
    run_id,
    batch_size=BATCH_SIZE,
):
    """
    Stream CSV and process configurable batches.

    Requirements:
    - No list(reader)
    - Does not load entire file into memory
    - Uses configurable batch size
    - Raw load happens before validation
    """

    client = None
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

    total_error_case_counts = Counter()

    batch = []
    batch_number = 0
    seen_order_ids = set()

    source_file = str(file_path)

    input_path = Path(file_path)

    file_size_mb = (
        input_path.stat().st_size
        / (1024 * 1024)
    )

    # ========================================================
    # START DISPLAY
    # ========================================================

    print("\n" + "=" * 65)
    print("PYTHON BATCH DATA PIPELINE")
    print("=" * 65)

    print(f"Run ID        : {run_id}")
    print(f"Input File    : {input_path.name}")
    print(f"File Size     : {file_size_mb:.2f} MB")
    print(f"Engine        : Python Batch")
    print(f"Batch Size    : {batch_size}")

    print("-" * 65)

    print("Pipeline:")
    print(
        "CSV -> orders_raw -> Validation -> "
        "Valid / Corrected / Quarantine"
    )

    print("=" * 65)

    print(
        "\n[1/4] Connecting to MongoDB..."
    )

    try:

        client, db = initialize_mongodb()

        print(
            "[OK] MongoDB connection established."
        )

        print(
            "\n[2/4] Loading records into orders_raw..."
        )

        print(
            "[INFO] Raw-first policy enabled."
        )

        with open(
            file_path,
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:

            reader = csv.DictReader(
                csv_file
            )

            for row_number, row in enumerate(
                reader,
                start=2,
            ):

                batch.append(
                    {
                        "record": row,
                        "row_number": row_number,
                    }
                )

                if len(batch) >= batch_size:

                    batch_number += 1

                    result = process_batch(
                        batch=batch,
                        db=db,
                        run_id=run_id,
                        source_file=source_file,
                        batch_number=batch_number,
                        seen_order_ids=seen_order_ids,
                    )

                    for key in totals:
                        totals[key] += result[key]

                    total_error_case_counts.update(
                        result[
                            "error_case_counts"
                        ]
                    )

                    print(
                        f"[PROGRESS] Batch "
                        f"{batch_number} completed | "
                        f"Rows processed: "
                        f"{totals['rows_read']}"
                    )

                    batch = []

            # ====================================================
            # FINAL INCOMPLETE BATCH
            # ====================================================

            if batch:

                batch_number += 1

                result = process_batch(
                    batch=batch,
                    db=db,
                    run_id=run_id,
                    source_file=source_file,
                    batch_number=batch_number,
                    seen_order_ids=seen_order_ids,
                )

                for key in totals:
                    totals[key] += result[key]

                total_error_case_counts.update(
                    result[
                        "error_case_counts"
                    ]
                )

                print(
                    f"[PROGRESS] Final batch "
                    f"{batch_number} completed | "
                    f"Rows processed: "
                    f"{totals['rows_read']}"
                )

        # ========================================================
        # RAW LOAD COMPLETE
        # ========================================================

        print(
            "\n[OK] Raw Load completed successfully."
        )

        print(
            f"     Total records stored in orders_raw "
            f"for this run: "
            f"{totals['raw_loaded']}"
        )

        print(
            "\n[3/4] Data Quality and ELT processing completed."
        )

        print(
            "[4/4] Finalizing metrics and consistency results..."
        )

    finally:

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        if client is not None:

            client.close()

            print(
                "[OK] MongoDB connection closed."
            )

    # ========================================================
    # TOTAL METRICS
    # ========================================================

    totals["elapsed_seconds"] = total_elapsed

    totals["error_case_counts"] = dict(
        total_error_case_counts
    )

    # ========================================================
    # SAVE METRICS
    # ========================================================

    metrics = build_metrics(
        run_id=run_id,
        file_name=input_path.name,
        file_size_mb=file_size_mb,
        engine_used="python_batch",
        rows_read=totals["rows_read"],
        raw_loaded=totals["raw_loaded"],
        valid_count=totals["valid_count"],
        corrected_count=totals["corrected_count"],
        quarantine_count=totals[
            "quarantine_count"
        ],
        elapsed_seconds=totals[
            "elapsed_seconds"
        ],
        batch_size=batch_size,
        partitions=None,
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
            "batch_count": batch_number,
        },
    )

    save_metrics(metrics)

    # ========================================================
    # FINAL DISPLAY
    # ========================================================

    print("\n" + "=" * 65)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 65)

    print("\nDATA LOADING")
    print(
        f"Rows Read        : "
        f"{totals['rows_read']}"
    )
    print(
        f"Raw Loaded       : "
        f"{totals['raw_loaded']}"
    )

    print("\nDATA QUALITY RESULTS")
    print(
        f"Valid            : "
        f"{totals['valid_count']}"
    )
    print(
        f"Corrected        : "
        f"{totals['corrected_count']}"
    )
    print(
        f"Quarantine       : "
        f"{totals['quarantine_count']}"
    )

    print("\nUPSERT RESULTS")
    print(
        f"Inserted         : "
        f"{totals['inserted_count']}"
    )
    print(
        f"Updated          : "
        f"{totals['updated_count']}"
    )
    print(
        f"Unchanged        : "
        f"{totals['unchanged_count']}"
    )

    print("\nPERFORMANCE")
    print(
        f"Total Time       : "
        f"{total_elapsed:.2f} seconds"
    )

    throughput = (
        totals["rows_read"]
        / total_elapsed
        if total_elapsed > 0
        else 0
    )

    print(
        f"Throughput       : "
        f"{throughput:.2f} rows/second"
    )

    print(
        f"Total Batches    : "
        f"{batch_number}"
    )

    print("\nCONSISTENCY CHECK")

    classified_count = (
        totals["valid_count"]
        + totals["corrected_count"]
        + totals["quarantine_count"]
    )

    if (
        totals["raw_loaded"]
        == classified_count
    ):

        print(
            "[PASS] raw_loaded = "
            "valid + corrected + quarantine"
        )

    else:

        print(
            "[WARNING] Consistency mismatch detected!"
        )

        print(
            f"Raw Loaded       : "
            f"{totals['raw_loaded']}"
        )

        print(
            f"Classified Total : "
            f"{classified_count}"
        )

    print("\nMETRICS")
    print(
        "[OK] Metrics saved to reports/results.json"
    )

    print("=" * 65)
    print("PIPELINE FINISHED SUCCESSFULLY")
    print("=" * 65 + "\n")

    print_metrics_summary(
        metrics
    )

    return totals


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    import argparse
    import uuid

    parser = argparse.ArgumentParser(
        description=(
            "Load a CSV file using "
            "Python batch streaming."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to CSV file",
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

    load_csv_in_batches(
        file_path=args.input,
        run_id=run_id,
    )