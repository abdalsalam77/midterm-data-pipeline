from pathlib import Path

from config.settings import SMALL_FILE_THRESHOLD_MB


# ============================================================
# FILE SIZE
# ============================================================

def get_file_size_mb(file_path):
    """Return file size in megabytes."""

    file_path = Path(file_path)

    if not file_path.exists():

        raise FileNotFoundError(
            f"Input file not found: {file_path}"
        )

    if not file_path.is_file():

        raise ValueError(
            f"Path is not a file: {file_path}"
        )

    return round(
        file_path.stat().st_size / (1024 * 1024),
        4,
    )


# ============================================================
# ENGINE SELECTION
# ============================================================

def choose_engine(
    file_path,
    threshold_mb=SMALL_FILE_THRESHOLD_MB,
):
    """
    Route file to the appropriate processing engine.

    file_size_mb <= threshold_mb -> python_batch
    file_size_mb > threshold_mb  -> pyspark
    """

    # ========================================================
    # VALIDATE THRESHOLD
    # ========================================================

    if threshold_mb <= 0:

        raise ValueError(
            "SMALL_FILE_THRESHOLD_MB must be greater than zero."
        )

    # ========================================================
    # GET FILE INFORMATION
    # ========================================================

    file_path = Path(file_path)

    file_size_mb = get_file_size_mb(
        file_path
    )

    # ========================================================
    # SELECT ENGINE
    # ========================================================

    if file_size_mb <= threshold_mb:

        engine_used = "python_batch"

        reason = (
            "File size is less than or equal "
            "to the configured threshold."
        )

    else:

        engine_used = "pyspark"

        reason = (
            "File size is greater than "
            "the configured threshold."
        )

    # ========================================================
    # ROUTING INFORMATION
    # ========================================================

    routing_info = {
        "file_name": file_path.name,
        "file_path": str(
            file_path.resolve()
        ),
        "file_size_mb": file_size_mb,
        "threshold_mb": threshold_mb,
        "engine_used": engine_used,
        "reason": reason,
    }

    # ========================================================
    # DISPLAY ROUTING DECISION
    # ========================================================

    print()

    print("=" * 55)
    print("             FILE ROUTER")
    print("=" * 55)

    print(
        f"File name       : "
        f"{routing_info['file_name']}"
    )

    print(
        f"File size       : "
        f"{routing_info['file_size_mb']} MB"
    )

    print(
        f"Threshold       : "
        f"{routing_info['threshold_mb']} MB"
    )

    print("-" * 55)

    print(
        f"Selected engine : "
        f"{routing_info['engine_used']}"
    )

    print(
        f"Reason          : "
        f"{routing_info['reason']}"
    )

    print("=" * 55)

    print()

    return routing_info


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Choose Python Batch or PySpark "
            "based on file size."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the input CSV file.",
    )

    args = parser.parse_args()

    choose_engine(
        args.input
    )