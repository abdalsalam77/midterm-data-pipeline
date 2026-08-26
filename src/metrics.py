"""
Pipeline Metrics and Consistency Reporting.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
RESULTS_FILE = REPORTS_DIR / "results.json"


def utc_now_iso():
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def calculate_error_case_counts(error_case_counts):
    """Convert Counter or dict to a JSON-safe dict."""
    if not error_case_counts:
        return {}

    return dict(error_case_counts)


def check_consistency(
    raw_loaded,
    valid_count,
    corrected_count,
    quarantine_count
):
    """
    Check:

    raw_loaded =
        valid_count
        + corrected_count
        + quarantine_count
    """

    final_count = (
        valid_count
        + corrected_count
        + quarantine_count
    )

    difference = raw_loaded - final_count

    return {
        "consistent": difference == 0,
        "run_raw_count": raw_loaded,
        "run_valid_count": valid_count,
        "run_corrected_count": corrected_count,
        "run_quarantine_count": quarantine_count,
        "final_count": final_count,
        "difference": difference,
    }


def build_metrics(
    run_id,
    file_name,
    file_size_mb,
    engine_used,
    rows_read,
    raw_loaded,
    valid_count,
    corrected_count,
    quarantine_count,
    elapsed_seconds,
    throughput=None,
    batch_size=None,
    batch_count=None,
    partitions=None,
    error_case_counts=None,
    inserted_count=0,
    updated_count=0,
    unchanged_count=0,
    extra_metrics=None
):
    """
    Build complete metrics for Python Batch or PySpark.

    Optional:
    - throughput
    - batch_size
    - batch_count
    - partitions
    - error_case_counts
    """

    rows_read = int(rows_read or 0)
    raw_loaded = int(raw_loaded or 0)
    valid_count = int(valid_count or 0)
    corrected_count = int(corrected_count or 0)
    quarantine_count = int(quarantine_count or 0)

    inserted_count = int(inserted_count or 0)
    updated_count = int(updated_count or 0)
    unchanged_count = int(unchanged_count or 0)

    elapsed_seconds = float(elapsed_seconds or 0)
    file_size_mb = float(file_size_mb or 0)

    if throughput is None:

        throughput = (
            rows_read / elapsed_seconds
            if elapsed_seconds > 0
            else 0
        )

    else:

        throughput = float(throughput or 0)

    consistency = check_consistency(
        raw_loaded=raw_loaded,
        valid_count=valid_count,
        corrected_count=corrected_count,
        quarantine_count=quarantine_count
    )

    metrics = {
        "recorded_at": utc_now_iso(),
        "run_id": run_id,
        "file_name": str(file_name),
        "file_size_mb": round(file_size_mb, 4),
        "engine_used": engine_used,

        "rows_read": rows_read,
        "raw_loaded": raw_loaded,

        "valid_count": valid_count,
        "corrected_count": corrected_count,
        "quarantine_count": quarantine_count,

        "elapsed_seconds": round(
            elapsed_seconds,
            6
        ),

        "throughput": round(
            throughput,
            4
        ),

        "batch_size": batch_size,
        "batch_count": batch_count,

        "partitions": partitions,

        "error_case_counts":
            calculate_error_case_counts(
                error_case_counts
            ),

        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,

        "consistency": consistency
    }

    if extra_metrics:

        metrics.update(
            extra_metrics
        )

    return metrics


def load_existing_results():
    """Load existing pipeline results."""

    if not RESULTS_FILE.exists():

        return {
            "runs": []
        }

    try:

        with RESULTS_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if (
            isinstance(data, dict)
            and isinstance(
                data.get("runs"),
                list
            )
        ):

            return data

    except (
        json.JSONDecodeError,
        OSError
    ):

        print(
            "[WARNING] Invalid results.json. "
            "Creating a new report."
        )

    return {
        "runs": []
    }


def save_metrics(metrics):
    """Append metrics to reports/results.json."""

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    results = load_existing_results()

    results["runs"].append(
        metrics
    )

    with RESULTS_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Metrics saved to: {RESULTS_FILE}"
    )

    return RESULTS_FILE


def print_metrics_summary(metrics):
    """Print readable metrics summary."""

    consistency = metrics.get(
        "consistency",
        {}
    )

    print(
        "\n========== RUN METRICS =========="
    )

    print(
        f"Run ID           : "
        f"{metrics.get('run_id')}"
    )

    print(
        f"Engine           : "
        f"{metrics.get('engine_used')}"
    )

    print(
        f"Rows read        : "
        f"{metrics.get('rows_read')}"
    )

    print(
        f"Raw loaded       : "
        f"{metrics.get('raw_loaded')}"
    )

    print(
        f"Valid            : "
        f"{metrics.get('valid_count')}"
    )

    print(
        f"Corrected        : "
        f"{metrics.get('corrected_count')}"
    )

    print(
        f"Quarantine       : "
        f"{metrics.get('quarantine_count')}"
    )

    print(
        f"Inserted         : "
        f"{metrics.get('inserted_count')}"
    )

    print(
        f"Updated          : "
        f"{metrics.get('updated_count')}"
    )

    print(
        f"Unchanged        : "
        f"{metrics.get('unchanged_count')}"
    )

    print(
        f"Batch size       : "
        f"{metrics.get('batch_size')}"
    )

    print(
        f"Batch count      : "
        f"{metrics.get('batch_count')}"
    )

    print(
        f"Partitions       : "
        f"{metrics.get('partitions')}"
    )

    print(
        f"Elapsed seconds  : "
        f"{metrics.get('elapsed_seconds')}"
    )

    print(
        f"Throughput       : "
        f"{metrics.get('throughput')} rows/s"
    )

    print(
        f"Consistency      : "
        f"{consistency.get('consistent')}"
    )

    print(
        f"Consistency diff : "
        f"{consistency.get('difference')}"
    )

    print(
        "=================================\n"
    )


if __name__ == "__main__":

    print("Metrics module test started.")

    test_metrics = build_metrics(
        run_id="test-run",
        file_name="test.csv",
        file_size_mb=10.5,
        engine_used="python_batch",
        rows_read=100,
        raw_loaded=100,
        valid_count=70,
        corrected_count=20,
        quarantine_count=10,
        elapsed_seconds=2.5,
        throughput=40.0,
        batch_size=50,
        batch_count=2,
        partitions=None,
        error_case_counts={
            "INVALID_EMAIL": 5,
            "MISSING_ORDER_ID": 3
        },
        inserted_count=80,
        updated_count=10,
        unchanged_count=0
    )

    print_metrics_summary(
        test_metrics
    )

    save_metrics(
        test_metrics
    )

    print(
        "Metrics module test finished."
    )