import csv
import os
import tempfile
import uuid

from pymongo import ASCENDING

from src.batch_loader import load_csv_in_batches
from src.mongo_setup import initialize_mongodb


def get_existing_validated_record(db):
    """
    Get one existing validated business record.
    """

    return db["orders_validated"].find_one(
        {},
        {"_id": 0}
    )


def create_modified_csv(record):
    """
    Create a temporary CSV containing one existing record
    with one safe business-field modification.

    The original source file is never modified.
    """

    record = dict(record)

    # Remove MongoDB / processing metadata.
    metadata_fields = {
        "quality_status",
        "run_id",
        "run_ids",
        "source_file",
        "source_row_number",
        "processed_at",
    }

    for field in metadata_fields:
        record.pop(field, None)

    # --------------------------------------------------------
    # SAFE MODIFICATION
    #
    # Keep the same order_id.
    # Change customer_name so MongoDB should classify it
    # as an UPDATE, not INSERT.
    # --------------------------------------------------------

    original_name = record.get(
        "customer_name",
        "Customer"
    )

    record["customer_name"] = (
        f"{original_name} - UPDATED"
    )

    # Create temporary CSV.
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8-sig",
        suffix=".csv",
        delete=False
    )

    temp_path = temp_file.name

    try:
        fieldnames = list(record.keys())

        writer = csv.DictWriter(
            temp_file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerow(record)

    finally:
        temp_file.close()

    return temp_path, original_name


def main():

    client = None
    temp_path = None

    try:

        # ====================================================
        # 1. CONNECT TO MONGODB
        # ====================================================

        client, db = initialize_mongodb()

        # ====================================================
        # 2. GET EXISTING RECORD
        # ====================================================

        existing_record = (
            get_existing_validated_record(db)
        )

        if existing_record is None:

            raise RuntimeError(
                "No record found in orders_validated. "
                "Run batch_loader first."
            )

        order_id = existing_record[
            "order_id"
        ]

        print(
            "\n========== UPSERT UPDATE TEST =========="
        )

        print(
            f"Selected order_id: {order_id}"
        )

        # ====================================================
        # 3. CREATE MODIFIED TEMP CSV
        # ====================================================

        temp_path, original_name = (
            create_modified_csv(
                existing_record
            )
        )

        print(
            f"Temporary CSV created: {temp_path}"
        )

        print(
            f"Original customer_name: {original_name}"
        )

        # ====================================================
        # 4. CLOSE INITIAL CONNECTION
        #
        # batch_loader creates and manages its own connection.
        # ====================================================

        client.close()
        client = None

        # ====================================================
        # 5. RUN PIPELINE
        # ====================================================

        run_id = str(
            uuid.uuid4()
        )

        result = load_csv_in_batches(
            file_path=temp_path,
            run_id=run_id,
            batch_size=1
        )

        print(
            "\n========== UPDATE TEST RESULT =========="
        )

        for key, value in result.items():
            print(
                f"{key}: {value}"
            )

        # ====================================================
        # 6. VERIFY EXPECTED RESULT
        # ====================================================

        print(
            "\n========== EXPECTED RESULT =========="
        )

        success = (
            result["inserted_count"] == 0
            and result["updated_count"] == 1
        )

        if success:

            print(
                "SUCCESS: Existing record was updated "
                "without creating a duplicate."
            )

        else:

            print(
                "FAILED: Expected inserted_count=0 "
                "and updated_count=1."
            )

        print(
            "======================================="
        )

    finally:

        # Close connection if still open.
        if client is not None:
            client.close()

        # Remove temporary CSV.
        if (
            temp_path is not None
            and os.path.exists(temp_path)
        ):

            os.remove(temp_path)

            print(
                "\nTemporary CSV removed."
            )


if __name__ == "__main__":
    main()