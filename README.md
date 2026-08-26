# Hybrid Data Pipeline for Dirty CSV Processing

## Overview

This project implements a Hybrid Data Pipeline for processing a large dirty CSV dataset using:

- Python Batch Processing for small files
- PySpark for large files
- MongoDB for storage
- ELT architecture
- Data Quality validation
- Safe data correction
- Quarantine for unrecoverable records
- Audit Trail for corrected records
- Upsert
- Idempotency
- Consistency checks
- Performance metrics

The project uses a single entry point:

```bash
python -m src.main --input <file>
Architecture

The pipeline follows this flow:

CSV File
   |
   v
Generate run_id
   |
   v
File Router
   |
   +-----------------------------+
   |                             |
   v                             v
Python Batch                 PySpark
Small Files                  Large Files
<= 200 MB                    > 200 MB
   |                             |
   +-------------+---------------+
                 |
                 v
             Raw Load
                 |
                 v
            orders_raw
                 |
                 v
         Schema Validation
                 |
        +--------+--------+
        |        |        |
        v        v        v
      Valid   Correctable Quarantine
        |        |        |
        |        v        |
        |   Safe Correction
        |        |
        |        v
        |   Re-validation
        |        |
        +--------+
                 |
                 v
         orders_validated
                 |
                 v
               Upsert
                 |
                 v
          Idempotency Check
                 |
                 v
         Consistency Check
                 |
                 v
              Metrics
                 |
                 v
       reports/results.json
Project Structure
midterm-data-pipeline/
│
├── README.md
├── requirements.txt
│
├── config/
│   └── settings.py
│
├── data/
│   ├── orders_huge_mixed_quality.csv
│   └── orders_small_sample.csv
│
├── src/
│   ├── main.py
│   ├── file_router.py
│   ├── create_small_sample.py
│   ├── batch_loader.py
│   ├── spark_loader.py
│   ├── schema_validation.py
│   ├── quality_rules.py
│   ├── correction_rules.py
│   ├── elt_pipeline.py
│   ├── mongo_setup.py
│   └── metrics.py
│
├── tests/
│   ├── test_cleaning_rules.py
│   └── test_classification.py
│
├── reports/
│   ├── results.json
│   ├── results.md
│   └── screenshots/
│
└── docs/
    └── architecture.md
File Router

The pipeline uses a configurable threshold:

SMALL_FILE_THRESHOLD_MB = 200

Routing logic:

File size <= 200 MB → python_batch
File size > 200 MB → pyspark

The router records:

run_id
file_name
file_size_mb
threshold
engine_used
routing_reason

The project successfully demonstrated:

Small sample → Python Batch
Large dataset → PySpark
Small Sample Generation

A reproducible small sample can be generated using:

python -m src.create_small_sample \
    --input data/orders_huge_mixed_quality.csv \
    --rows 100000

The sample generator:

Uses streaming
Does not load the full source file into memory
Supports configurable row counts
Does not require manual editing or Excel
Python Batch Processing

Small files are processed using Python.

Features:

Streaming CSV reading
Configurable batch size
No list(reader)
MongoDB insert_many() for raw batches
Batch metrics
Batch number
Row count
Processing time
Throughput
Error logging

Demonstrated result:

Rows Read: 100000
Raw Loaded: 100000
Valid: 48931
Corrected: 33340
Quarantine: 17729
Consistency: PASS
Total Batches: 5
PySpark Processing

Large files are processed using PySpark.

Features:

SparkSession
Spark DataFrame API
Fixed schema
Sensitive raw fields preserved as strings
Distributed processing
MongoDB integration
No Pandas for large files
No unnecessary repartition()

Demonstrated large dataset result:

Rows Read: 30000000
Raw Loaded: 30000000
Valid: 14810722
Corrected: 10079879
Quarantine: 5109399

Partitions: 99
Elapsed Time: 4157.43 seconds
Throughput: 7215.99 rows/second

Consistency Check: PASS
Raw-First Policy

Every record is stored in orders_raw before validation or cleaning.

Each raw record contains:

run_id
source_file
source_row_number
ingested_at
engine_used
raw_record

No record is silently deleted.

Data Quality Pipeline

After Raw Load, records pass through:

Schema Validation
Data Quality Validation
Classification

Each record receives exactly one final result:

valid
corrected
quarantine

Valid records never enter the correction stage.

Only records classified as correctable enter Safe Correction.

Unsafe or ambiguous records are quarantined.

Correction Rules

The pipeline implements 10 safe correction rules:

Arabic Digits → Latin Digits
Currency normalization → YER
Remove thousand separators
Convert known word prices
Normalize phone numbers when the format is clear
Fix obvious email errors only
Normalize dates to YYYY-MM-DD when unambiguous
Trim whitespace
Normalize known synonyms
Recalculate total_amount when components are valid

Unknown or ambiguous values are never guessed.

Audit Trail

Every corrected record includes correction information:

field
original_value
corrected_value
rule_code

Detailed correction records are stored in:

correction_audit

Each audit entry contains:

run_id
order_id
field
original_value
corrected_value
rule_code
corrected_at
Quarantine

Unrecoverable records are stored in:

orders_quarantine

Each quarantined record contains:

run_id
error_codes
error_details
raw_record

Examples include:

MISSING_ORDER_ID
MISSING_CUSTOMER_ID
INVALID_IMPOSSIBLE_DATE
CORRUPTED_ITEMS_JSON
EMPTY_ITEMS
UNKNOWN_PRICE
AMBIGUOUS_NEGATIVE_VALUE
DUPLICATE_ORDER_ID
MULTIPLE_CONFLICTING_ERRORS

Records are never silently dropped.

MongoDB Collections

The project uses four main collections:

orders_raw

Stores all incoming records before cleaning or validation.

orders_validated

Stores valid and successfully corrected records.

A unique index is created on:

order_id
orders_quarantine

Stores unrecoverable records with their error reasons.

correction_audit

Stores the audit trail for every correction.

Upsert

The pipeline uses MongoDB Upsert for orders_validated.

The following metrics are calculated:

inserted_count
updated_count
unchanged_count

The pipeline does not rely on an unsafe primary check-then-insert strategy.

Idempotency

The pipeline supports idempotent processing.

order_id is the Stable Business Key.

Running the same final business data again:

Does not create duplicate business records
Does not incorrectly increase validated records
Keeps unchanged records unchanged

The project tested:

First Run → Insert
Re-run → No duplicate business records
Modified record → Update without duplicate

Raw history is still preserved using a new run_id for every execution.

Consistency Check

For every run, the following equation must hold:

run_raw_count =
run_valid_count
+ run_corrected_count
+ run_quarantine_count

Both demonstrated executions passed:

[PASS] raw_loaded = valid + corrected + quarantine
Metrics

Metrics are saved to:

reports/results.json

Recorded metrics include:

run_id
file_name
file_size_mb
engine_used
rows_read
raw_loaded
valid_count
corrected_count
quarantine_count
elapsed_seconds
throughput
batch_size
batch_count
partitions
error_case_counts
inserted_count
updated_count
unchanged_count
consistency status

Throughput is calculated as:

throughput = rows_processed / elapsed_seconds
Testing

Run all tests using:

python -m pytest tests -v

Current result:

22 passed

Tests cover:

Cleaning Rules
Arabic digits
Currency normalization
Thousand separators
Word prices
Phone normalization
Email correction
Date normalization
Trim whitespace
Synonym normalization
Total amount recalculation
Original record protection
Unknown word prices are not guessed
Classification
Valid record classification
Correctable record classification
Missing order_id
Impossible date
Unknown error
Valid records do not enter correction
Correctable records are corrected
Quarantine records do not enter correction
Corrupted items JSON
Quarantine error priority
Installation

Install the required dependencies:

pip install -r requirements.txt

MongoDB must be available and configured through the project settings or environment variables.

Java and PySpark are required for large-file processing.

Configuration

Main configuration includes:

SMALL_FILE_THRESHOLD_MB = 200
BATCH_SIZE = 20000

The threshold determines whether the pipeline uses:

python_batch

or:

pyspark
Running the Pipeline

Run the pipeline using:

python -m src.main --input data/orders_small_sample.csv

For the large dataset:

python -m src.main --input data/orders_huge_mixed_quality.csv
Spark UI

During PySpark execution, Spark UI can be used to inspect:

Jobs
Stages
Tasks
Executors
Storage
Partitions

Screenshots are available in:

reports/screenshots/
Demonstration Results
Python Batch
Rows Read: 100000
Raw Loaded: 100000
Valid: 48931
Corrected: 33340
Quarantine: 17729
Total Batches: 5
Consistency: PASS
PySpark
Rows Read: 30000000
Raw Loaded: 30000000
Valid: 14810722
Corrected: 10079879
Quarantine: 5109399

Partitions: 99
Consistency: PASS
Final Requirements Status
 Python Batch for small files
 PySpark for large files
 File Router
 Raw-first loading
 Schema validation
 Valid / Corrected / Quarantine separation
 10 safe correction rules
 Correction Audit Trail
 Quarantine with reasons
 MongoDB storage
 Upsert
 Unique Business Key
 Idempotency
 Consistency Check
 Metrics
 Python Batch demonstration
 PySpark demonstration
 Automated tests
 22 tests passed
Conclusion

The project successfully implements a Hybrid Data Pipeline capable of routing files based on size, processing small files with Python Batch and large files with PySpark, preserving all raw data, validating quality, safely correcting deterministic errors, quarantining unsafe records, maintaining correction audit trails, supporting Upsert and Idempotency, and recording execution metrics.