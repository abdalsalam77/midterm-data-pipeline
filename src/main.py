import argparse
import uuid
from pathlib import Path

from config.settings import BATCH_SIZE
from src.file_router import choose_engine
from src.batch_loader import load_csv_in_batches
from src.spark_loader import load_csv_with_spark


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():

    # ========================================================
    # COMMAND LINE ARGUMENTS
    # ========================================================

    parser = argparse.ArgumentParser(
        description="Hybrid Data Pipeline"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV file",
    )

    args = parser.parse_args()

    # ========================================================
    # VALIDATE INPUT FILE
    # ========================================================

    file_path = Path(args.input)

    if not file_path.exists():

        raise FileNotFoundError(
            f"Input file not found: {file_path}"
        )

    if not file_path.is_file():

        raise ValueError(
            f"Input path is not a file: {file_path}"
        )

    # ========================================================
    # CREATE RUN ID
    # ========================================================

    run_id = str(uuid.uuid4())

    # ========================================================
    # PIPELINE START
    # ========================================================

    print()

    print("=" * 55)
    print("           HYBRID DATA PIPELINE")
    print("=" * 55)

    print(f"Run ID      : {run_id}")
    print(f"Input file  : {file_path.name}")

    print("=" * 55)

    # ========================================================
    # FILE ROUTER
    # ========================================================

    routing_result = choose_engine(
        file_path
    )

    engine_used = routing_result[
        "engine_used"
    ]

    # ========================================================
    # START SELECTED ENGINE
    # ========================================================

    print("=" * 55)
    print("           PROCESSING STARTED")
    print("=" * 55)

    print(
        f"Engine      : {engine_used}"
    )

    print(
        f"Run ID      : {run_id}"
    )

    print("-" * 55)

    # ========================================================
    # PYTHON BATCH
    # ========================================================

    if engine_used == "python_batch":

        print(
            "Mode        : Streaming CSV with Python Batch"
        )

        print(
            f"Batch size  : {BATCH_SIZE}"
        )

        print()

        load_result = load_csv_in_batches(
            file_path=file_path,
            run_id=run_id,
            batch_size=BATCH_SIZE,
        )

    # ========================================================
    # PYSPARK
    # ========================================================

    elif engine_used == "pyspark":

        print(
            "Mode        : Distributed processing with PySpark"
        )

        print()

        load_result = load_csv_with_spark(
            file_path=file_path,
            run_id=run_id,
        )

    # ========================================================
    # UNKNOWN ENGINE
    # ========================================================

    else:

        raise ValueError(
            f"Unknown engine selected: "
            f"{engine_used}"
        )

    # ========================================================
    # FINAL PIPELINE SUMMARY
    # ========================================================

    print()

    print("=" * 55)
    print("           PIPELINE COMPLETE")
    print("=" * 55)

    print(f"Run ID          : {run_id}")
    print(f"Engine used     : {engine_used}")

    print("-" * 55)

    print(
        f"Rows read       : "
        f"{load_result.get('rows_read', 0)}"
    )

    print(
        f"Raw loaded      : "
        f"{load_result.get('raw_loaded', 0)}"
    )

    print("-" * 55)

    print(
        f"Valid           : "
        f"{load_result.get('valid_count', 0)}"
    )

    print(
        f"Corrected       : "
        f"{load_result.get('corrected_count', 0)}"
    )

    print(
        f"Quarantine      : "
        f"{load_result.get('quarantine_count', 0)}"
    )

    print("-" * 55)

    print(
        f"Inserted        : "
        f"{load_result.get('inserted_count', 0)}"
    )

    print(
        f"Updated         : "
        f"{load_result.get('updated_count', 0)}"
    )

    print(
        f"Unchanged       : "
        f"{load_result.get('unchanged_count', 0)}"
    )

    # ========================================================
    # ELAPSED TIME
    # ========================================================

    elapsed_seconds = load_result.get(
        "elapsed_seconds"
    )

    if elapsed_seconds is not None:

        print("-" * 55)

        print(
            f"Elapsed time    : "
            f"{elapsed_seconds:.2f} seconds"
        )

    # ========================================================
    # COMPLETION MESSAGE
    # ========================================================

    print("=" * 55)

    print(
        "Pipeline finished successfully."
    )

    print("=" * 55)

    print()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    main()