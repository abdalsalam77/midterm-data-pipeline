"""Optional lightweight scheduler. Run as `python -m src.scheduled_jobs`."""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pymongo import MongoClient
import schedule
from config.settings import MONGO_URI, MONGO_DATABASE, REPORTS_DIR
from src.analytics import refresh_materialized_views, run_aggregations


def refresh_and_report() -> None:
    started = datetime.now(timezone.utc).isoformat()
    try:
        with MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) as client:
            db = client[MONGO_DATABASE]
            views = refresh_materialized_views(db)
            report = {
                "generated_at": started,
                "materialized_views": views,
                "aggregations": run_aggregations(db),
            }
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            (REPORTS_DIR / "analytics_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print(f"[{started}] analytics refresh completed: {views}")
    except Exception as exc:
        # Do not swallow errors: log them visibly for the demo/audit trail.
        print(f"[{started}] analytics refresh FAILED: {type(exc).__name__}: {exc}")


def main() -> None:
    schedule.every(60).minutes.do(refresh_and_report)
    print("Scheduled analytics refresh started (every 60 minutes). Ctrl+C to stop.")
    refresh_and_report()  # initial run proves it works now, not only on schedule
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Scheduler stopped.")


if __name__ == "__main__":
    main()
