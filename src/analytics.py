
from pymongo import ASCENDING, DESCENDING
from datetime import datetime, timezone


VALID = "orders_validated"
RAW = "orders_raw"
QUARANTINE = "orders_quarantine"
AUDIT = "correction_audit"

MV_DAILY = "mv_daily_sales"
MV_CITY = "mv_city_summary"


def create_indexes(db):
    """Create indexes while reusing equivalent existing indexes."""

    def ensure(collection_name, keys, name, unique=False):
        collection = db[collection_name]

        for index in collection.list_indexes():
            same_keys = list(index["key"].items()) == keys
            same_unique = index.get("unique", False) == unique

            if same_keys and same_unique:
                return index["name"]

        return collection.create_index(
            keys,
            unique=unique,
            name=name,
        )

    return {
        "order_id_unique": ensure(
            VALID, [("order_id", ASCENDING)],
            "unique_order_id", unique=True
        ),
        "run_id_valid": ensure(
            VALID, [("run_id", ASCENDING)], "idx_run_id_valid"
        ),
        "run_id_raw": ensure(
            RAW, [("run_id", ASCENDING)], "idx_run_id_raw"
        ),
        "run_id_quarantine": ensure(
            QUARANTINE, [("run_id", ASCENDING)],
            "idx_run_id_quarantine"
        ),
        "run_id_audit": ensure(
            AUDIT, [("run_id", ASCENDING)], "idx_run_id_audit"
        ),
        "date_status": ensure(
            VALID,
            [("order_date", DESCENDING), ("quality_status", ASCENDING)],
            "idx_date_status"
        ),
        "customer_id": ensure(
            VALID, [("customer_id", ASCENDING)], "idx_customer_id"
        ),
        "city": ensure(
            VALID, [("city", ASCENDING)], "idx_city"
        ),
    }


def run_queries(db, limit=10):
    """Run useful read-only queries against validated orders."""
    orders = db[VALID]

    return {
        "recent_orders": list(
            orders.find({}).sort("_id", DESCENDING).limit(limit)
        ),
        "valid_orders": list(
            orders.find({"quality_status": "valid"}).limit(limit)
        ),
        "corrected_orders": list(
            orders.find({"quality_status": "corrected"}).limit(limit)
        ),
        "orders_by_city": list(
            orders.find(
                {"city": {"$exists": True, "$ne": None}}
            ).limit(limit)
        ),
        "orders_by_customer": list(
            orders.find(
                {"customer_id": {"$exists": True, "$ne": None}}
            ).limit(limit)
        ),
    }


def explain_examples(db):
    """Return query execution plans for index/performance inspection."""
    orders = db[VALID]

    return {
        "order_id": orders.find(
            {"order_id": "__EXPLAIN_SAMPLE__"}
        ).explain(),
        "quality_status": orders.find(
            {"quality_status": "valid"}
        ).explain(),
        "customer_id": orders.find(
            {"customer_id": "__EXPLAIN_SAMPLE__"}
        ).explain(),
    }


def run_aggregations(db):
    """Aggregate validated order counts and sales."""
    orders = db[VALID]

    status_pipeline = [
        {
            "$group": {
                "_id": "$quality_status",
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
    ]

    city_pipeline = [
        {
            "$group": {
                "_id": "$city",
                "order_count": {"$sum": 1},
                "total_amount": {
                    "$sum": {
                        "$convert": {
                            "input": "$total_amount",
                            "to": "double",
                            "onError": 0,
                            "onNull": 0,
                        }
                    }
                },
            }
        },
        {"$sort": {"total_amount": -1}},
    ]

    daily_pipeline = [
        {
            "$group": {
                "_id": "$order_date",
                "order_count": {"$sum": 1},
                "total_amount": {
                    "$sum": {
                        "$convert": {
                            "input": "$total_amount",
                            "to": "double",
                            "onError": 0,
                            "onNull": 0,
                        }
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]

    return {
        "quality_status": list(orders.aggregate(status_pipeline)),
        "city_summary": list(orders.aggregate(city_pipeline)),
        "daily_sales": list(orders.aggregate(daily_pipeline)),
    }



def refresh_materialized_views(db):
    """Refresh daily sales and city summaries using $merge."""

    orders = db[VALID]

    # $merge requires a unique index on each "on" field.
    db[MV_DAILY].create_index(
        [("order_date", ASCENDING)],
        unique=True,
        name="uq_mv_order_date",
    )
    db[MV_CITY].create_index(
        [("city", ASCENDING)],
        unique=True,
        name="uq_mv_city",
    )

    daily_pipeline = [
        {
            "$group": {
                "_id": "$order_date",
                "order_count": {"$sum": 1},
                "total_amount": {
                    "$sum": {
                        "$convert": {
                            "input": "$total_amount",
                            "to": "double",
                            "onError": 0,
                            "onNull": 0,
                        }
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "order_date": "$_id",
                "order_count": 1,
                "total_amount": 1,
                "refreshed_at": "$$NOW",
            }
        },
        {
            "$merge": {
                "into": MV_DAILY,
                "on": "order_date",
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }
        },
    ]

    city_pipeline = [
        {
            "$group": {
                "_id": "$city",
                "order_count": {"$sum": 1},
                "total_amount": {
                    "$sum": {
                        "$convert": {
                            "input": "$total_amount",
                            "to": "double",
                            "onError": 0,
                            "onNull": 0,
                        }
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "city": {"$ifNull": ["$_id", "Unknown"]},
                "order_count": 1,
                "total_amount": 1,
                "refreshed_at": "$$NOW",
            }
        },
        {
            "$merge": {
                "into": MV_CITY,
                "on": "city",
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }
        },
    ]

    list(orders.aggregate(daily_pipeline))
    list(orders.aggregate(city_pipeline))

    return {
        "daily_sales_documents": db[MV_DAILY].count_documents({}),
        "city_summary_documents": db[MV_CITY].count_documents({}),
    }
