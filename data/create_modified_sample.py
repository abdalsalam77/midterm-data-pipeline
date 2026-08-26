import csv
from pathlib import Path

INPUT_FILE = Path("data/orders_small_sample.csv")
OUTPUT_FILE = Path("data/orders_small_sample_modified.csv")

TARGET_ORDER_ID = "طلب-104522"

modified = False

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8-sig",
    newline=""
) as source_file, open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8-sig",
    newline=""
) as target_file:

    reader = csv.DictReader(source_file)

    writer = csv.DictWriter(
        target_file,
        fieldnames=reader.fieldnames
    )

    writer.writeheader()

    for row in reader:

        if row.get("order_id") == TARGET_ORDER_ID:

            print("Found:", TARGET_ORDER_ID)
            print(
                "Old customer_name:",
                row.get("customer_name")
            )

            row["customer_name"] = "اسم معدل للاختبار"

            print(
                "New customer_name:",
                row["customer_name"]
            )

            modified = True

        writer.writerow(row)

if modified:

    print(
        "\nModified file created:",
        OUTPUT_FILE
    )

else:

    print(
        "\nERROR: order_id not found"
    )