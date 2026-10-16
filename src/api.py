
"""Optional FastAPI interface for the existing midterm pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from pymongo import MongoClient

from config.settings import MONGO_URI, MONGO_DATABASE, REPORTS_DIR
from src.analytics import (
    create_indexes,
    explain_examples,
    run_queries,
    run_aggregations,
    refresh_materialized_views,
)


app = FastAPI(
    title="Midterm Data Pipeline API",
    version="1.0.0",
)


def _client() -> MongoClient:
    """Create a MongoDB client and verify the connection."""
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=3000,
    )
    try:
        client.admin.command("ping")
        return client
    except Exception:
        client.close()
        raise


def _serialize(data):
    """Convert MongoDB-specific values, including ObjectId, to JSON-safe values."""
    return jsonable_encoder(
        data,
        custom_encoder={ObjectId: str},
    )


def _limit_result(data, limit: int = 20):
    """Limit list sizes recursively to keep API responses manageable."""
    if isinstance(data, list):
        return [
            _limit_result(item, limit)
            for item in data[:limit]
        ]

    if isinstance(data, dict):
        return {
            key: _limit_result(value, limit)
            for key, value in data.items()
        }

    return data


@app.get("/health")
def health():
    """Check API and MongoDB connectivity."""
    try:
        with _client() as client:
            return {
                "status": "ok",
                "database": MONGO_DATABASE,
                "mongo": "connected",
            }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB connection failed: {exc}",
        ) from exc


@app.post("/indexes")
def indexes():
    """Create the indexes required by analytics queries."""
    try:
        with _client() as client:
            result = create_indexes(client[MONGO_DATABASE])
            return _serialize({"created_indexes": result})
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/queries")
def queries(limit: int = 5):
    """Run example MongoDB queries."""
    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 100",
        )

    try:
        with _client() as client:
            result = run_queries(client[MONGO_DATABASE], limit)
            return _serialize(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/explain")
def explain():
    """Return query execution plans."""
    try:
        with _client() as client:
            result = explain_examples(client[MONGO_DATABASE])
            return _serialize({"explain": result})
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/aggregations")
def aggregations():
    """Run aggregation pipelines and return a limited preview."""
    try:
        with _client() as client:
            result = run_aggregations(client[MONGO_DATABASE])
            limited_result = _limit_result(result, limit=20)
            return _serialize(limited_result)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.post("/materialized-views/refresh")
def refresh_views():
    """Refresh the materialized analytics views."""
    try:
        with _client() as client:
            result = refresh_materialized_views(client[MONGO_DATABASE])
            return _serialize(result)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.post("/report")
def write_report():
    """Refresh analytics views and save an analytics report."""
    try:
        with _client() as client:
            db = client[MONGO_DATABASE]

            report = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "aggregations": run_aggregations(db),
                "materialized_views": refresh_materialized_views(db),
            }

            REPORTS_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            path = REPORTS_DIR / "analytics_report.json"
            path.write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

            return {
                "saved": str(path),
                "materialized_views": _serialize(
                    report["materialized_views"]
                ),
            }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
