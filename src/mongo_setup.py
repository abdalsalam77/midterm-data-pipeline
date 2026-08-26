from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

from config.settings import (
    MONGO_URI,
    MONGO_DATABASE,
    ORDERS_RAW_COLLECTION,
    ORDERS_VALIDATED_COLLECTION,
    ORDERS_QUARANTINE_COLLECTION,
    CORRECTION_AUDIT_COLLECTION,
)


def get_mongo_client():
    """
    Create and return a MongoDB client.
    """

    client = MongoClient(MONGO_URI)

    # Verify MongoDB connection.
    client.admin.command("ping")

    return client


def get_database(client):
    """
    Return the project MongoDB database.
    """

    return client[MONGO_DATABASE]

def get_worker_database():
    """
    Connect a Spark worker to MongoDB.

    Does not create collections or indexes.
    MongoDB setup must happen once in the driver.
    """

    client = get_mongo_client()

    db = get_database(client)

    return client, db

def setup_collections(db):
    """
    Create all required collections and indexes.

    Collections:
        - orders_raw
        - orders_validated
        - orders_quarantine
        - correction_audit
    """

    existing_collections = set(
        db.list_collection_names()
    )

    required_collections = [
        ORDERS_RAW_COLLECTION,
        ORDERS_VALIDATED_COLLECTION,
        ORDERS_QUARANTINE_COLLECTION,
        CORRECTION_AUDIT_COLLECTION,
    ]

    # ============================================================
    # CREATE COLLECTIONS
    # ============================================================

    for collection_name in required_collections:

        if collection_name not in existing_collections:

            db.create_collection(collection_name)

            print(
                f"Created collection: "
                f"{collection_name}"
            )

        else:

            print(
                f"Collection already exists: "
                f"{collection_name}"
            )

    # ============================================================
    # ORDERS VALIDATED
    #
    # order_id is the stable business key.
    #
    # This unique index is required for:
    # - Upsert
    # - Idempotency
    # - Preventing duplicate business records
    # ============================================================

    db[ORDERS_VALIDATED_COLLECTION].create_index(
        [("order_id", ASCENDING)],
        unique=True,
        name="unique_order_id",
    )

    # ============================================================
    # ORDERS RAW
    #
    # Raw history is allowed for every run.
    # Same business record may appear again in a new run_id.
    # ============================================================

    db[ORDERS_RAW_COLLECTION].create_index(
        [("run_id", ASCENDING)],
        name="idx_raw_run_id",
    )

    db[ORDERS_RAW_COLLECTION].create_index(
        [
            ("run_id", ASCENDING),
            ("source_row_number", ASCENDING),
        ],
        name="idx_raw_run_row",
    )

    # ============================================================
    # ORDERS QUARANTINE
    # ============================================================

    db[ORDERS_QUARANTINE_COLLECTION].create_index(
        [("run_id", ASCENDING)],
        name="idx_quarantine_run_id",
    )

    # ============================================================
    # CORRECTION AUDIT
    # ============================================================

    db[CORRECTION_AUDIT_COLLECTION].create_index(
        [("run_id", ASCENDING)],
        name="idx_audit_run_id",
    )

    db[CORRECTION_AUDIT_COLLECTION].create_index(
        [("order_id", ASCENDING)],
        name="idx_audit_order_id",
    )

    print(
        "\nMongoDB collections and indexes "
        "are ready."
    )


def initialize_mongodb():
    """
    Connect to MongoDB and initialize
    the project database.

    Returns:
        client, db
    """

    try:

        client = get_mongo_client()

        db = get_database(client)

        setup_collections(db)

        print(
            "\nMongoDB connected successfully."
        )

        print(
            f"Database: {MONGO_DATABASE}"
        )

        return client, db

    except PyMongoError as error:

        print(
            f"MongoDB initialization failed: "
            f"{error}"
        )

        raise


if __name__ == "__main__":

    client = None

    try:

        client, db = initialize_mongodb()

        print(
            "\nAvailable collections:"
        )

        for collection_name in db.list_collection_names():

            print(
                f"- {collection_name}"
            )

    finally:

        if client is not None:

            client.close()

            print(
                "\nMongoDB connection closed."
            )