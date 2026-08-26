def check_run_consistency(db, run_id, run_metrics=None):
    """
    Check that every raw record for a run has exactly one final outcome.

    Main equation:

        raw_count =
            valid_count
            + corrected_count
            + quarantine_count

    The authoritative outcome counts for the current run should come
    from run_metrics when available, because orders_validated uses
    order_id as a business key and Upsert/Idempotency may overwrite
    metadata from previous runs.
    """

    orders_raw = db["orders_raw"]
    orders_validated = db["orders_validated"]
    orders_quarantine = db["orders_quarantine"]

    # ============================================================
    # 1. RAW COUNT
    # ============================================================

    raw_count = orders_raw.count_documents({
        "run_id": run_id
    })

    # ============================================================
    # 2. QUARANTINE COUNT FROM DATABASE
    # ============================================================

    quarantine_count_db = orders_quarantine.count_documents({
        "run_id": run_id
    })

    # ============================================================
    # 3. VALID / CORRECTED DATABASE DIAGNOSTICS
    #
    # Important:
    # Your batch_loader uses:
    #
    # quality_status = "valid"
    # quality_status = "corrected"
    #
    # NOT "validated".
    # ============================================================

    valid_count_db = orders_validated.count_documents({
        "run_id": run_id,
        "quality_status": "valid"
    })

    corrected_count_db = orders_validated.count_documents({
        "run_id": run_id,
        "quality_status": "corrected"
    })

    # ============================================================
    # 4. AUTHORITATIVE COUNTS FOR THIS RUN
    #
    # run_metrics represents what actually happened to every row
    # during this specific pipeline execution.
    # ============================================================

    if run_metrics is not None:

        valid_count = run_metrics.get(
            "valid_count",
            0
        )

        corrected_count = run_metrics.get(
            "corrected_count",
            0
        )

        quarantine_count = run_metrics.get(
            "quarantine_count",
            0
        )

        count_source = "run_metrics"

    else:

        valid_count = valid_count_db

        corrected_count = corrected_count_db

        quarantine_count = quarantine_count_db

        count_source = "mongodb"

    # ============================================================
    # 5. FINAL COUNT
    # ============================================================

    final_count = (
        valid_count
        + corrected_count
        + quarantine_count
    )

    # ============================================================
    # 6. MAIN CONSISTENCY EQUATION
    # ============================================================

    is_consistent = (
        raw_count == final_count
    )

    # ============================================================
    # 7. DATABASE DIAGNOSTIC
    #
    # This is diagnostic only. It may differ from run_metrics because
    # orders_validated is an Upsert collection keyed by order_id.
    # ============================================================

    database_final_count = (
        valid_count_db
        + corrected_count_db
        + quarantine_count_db
    )

    database_is_consistent = (
        raw_count == database_final_count
    )

    # ============================================================
    # 8. RESULT
    # ============================================================

    return {
        "run_id": run_id,

        # Main consistency result
        "raw_count": raw_count,
        "valid_count": valid_count,
        "corrected_count": corrected_count,
        "quarantine_count": quarantine_count,
        "final_count": final_count,
        "is_consistent": is_consistent,
        "count_source": count_source,

        # Database diagnostics
        "valid_count_db": valid_count_db,
        "corrected_count_db": corrected_count_db,
        "quarantine_count_db": quarantine_count_db,
        "database_final_count": database_final_count,
        "database_is_consistent": database_is_consistent
    }


def print_consistency_result(result):
    """Print consistency result in a readable format."""

    print(
        "\n========== CONSISTENCY RESULT =========="
    )

    print(
        f"Run ID       : {result['run_id']}"
    )

    print(
        f"Count source : {result['count_source']}"
    )

    print(
        f"Raw          : {result['raw_count']}"
    )

    print(
        f"Valid        : {result['valid_count']}"
    )

    print(
        f"Corrected    : {result['corrected_count']}"
    )

    print(
        f"Quarantine   : {result['quarantine_count']}"
    )

    print(
        f"Final        : {result['final_count']}"
    )

    print(
        "----------------------------------------"
    )

    print(
        f"Equation: "
        f"{result['raw_count']} = "
        f"{result['valid_count']} + "
        f"{result['corrected_count']} + "
        f"{result['quarantine_count']}"
    )

    print(
        "----------------------------------------"
    )

    print(
        f"Passed       : {result['is_consistent']}"
    )

    print(
        "----------------------------------------"
    )

    print("MongoDB Diagnostic:")

    print(
        f"Valid in DB      : "
        f"{result['valid_count_db']}"
    )

    print(
        f"Corrected in DB  : "
        f"{result['corrected_count_db']}"
    )

    print(
        f"Quarantine in DB : "
        f"{result['quarantine_count_db']}"
    )

    print(
        f"DB Final         : "
        f"{result['database_final_count']}"
    )

    print(
        f"DB Consistent    : "
        f"{result['database_is_consistent']}"
    )

    print(
        "========================================\n"
    )


if __name__ == "__main__":

    import argparse

    from src.mongo_setup import (
        get_mongo_client,
        get_database
    )

    parser = argparse.ArgumentParser(
        description="Check pipeline consistency for a run."
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID to check"
    )

    args = parser.parse_args()

    client = get_mongo_client()

    try:

        db = get_database(client)

        result = check_run_consistency(
            db=db,
            run_id=args.run_id
        )

        print_consistency_result(result)

    finally:

        client.close()

        print(
            "MongoDB connection closed."
        )