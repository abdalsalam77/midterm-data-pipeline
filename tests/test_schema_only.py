import csv
from collections import Counter
from src.schema_validation import validate_schema

INPUT_FILE = "data/01_student_test_small.csv"

total = 0
passed = 0
rejected = 0
error_counts = Counter()

with open(INPUT_FILE, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        result = validate_schema(row)

        if result["schema_valid"]:
            passed += 1
        else:
            rejected += 1

            for error in result["schema_errors"]:
                error_counts[error["code"]] += 1

print("\n========== SCHEMA ONLY TEST ==========")
print(f"Total records       : {total}")
print(f"Schema passed       : {passed}")
print(f"Schema rejected     : {rejected}")
print("--------------------------------------")
print("Schema error counts:")

for code, count in error_counts.items():
    print(f"{code:30} : {count}")

print("======================================")