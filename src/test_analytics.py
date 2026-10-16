
from pymongo import MongoClient
from config.settings import MONGO_URI, MONGO_DATABASE
from src.analytics import (
    create_indexes,
    run_queries,
    explain_examples,
    run_aggregations,
    refresh_materialized_views,
)

def main():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

    try:
        client.admin.command("ping")
        db = client[MONGO_DATABASE]

        print("\n1. INDEXES")
        print(create_indexes(db))

        print("\n2. QUERIES")
        print(run_queries(db, limit=3).keys())

        print("\n3. EXPLAIN")
        print(explain_examples(db))

        print("\n4. AGGREGATIONS")
        print(run_aggregations(db).keys())

        print("\n5. MATERIALIZED VIEWS")
        print(refresh_materialized_views(db))

        print("\nAnalytics checks completed.")

    finally:
        client.close()

if __name__ == "__main__":
    main()
