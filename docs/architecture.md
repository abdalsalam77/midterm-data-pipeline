# System Architecture

## 1. Overview

This project implements a Hybrid Data Pipeline for processing dirty CSV files.

The pipeline automatically selects the processing engine according to file size:

- Small files (`<= 200 MB`) are processed using Python Batch.
- Large files (`> 200 MB`) are processed using PySpark.

MongoDB is used for raw storage, validated records, quarantined records, and correction audit records.

The architecture follows an ELT-style approach where every record is first preserved in the Raw Layer before validation, correction, or quarantine.

---

## 2. High-Level Architecture

```text
                         INPUT CSV
                             |
                             v
                        Generate run_id
                             |
                             v
                        FILE ROUTER
                             |
              +--------------+--------------+
              |                             |
              v                             v
       Python Batch                      PySpark
       <= 200 MB                         > 200 MB
              |                             |
              +-------------+---------------+
                            |
                            v
                       RAW LOAD
                            |
                            v
                      orders_raw
                            |
                            v
                    SCHEMA VALIDATION
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
            VALID       CORRECTABLE    QUARANTINE
              |             |             |
              |             v             |
              |       SAFE CORRECTION     |
              |             |             |
              |             v             |
              |        RE-VALIDATION      |
              |             |             |
              +-------------+-------------+
                            |
                            v
                    orders_validated
                            |
                            v
                          UPSERT
                            |
                            v
                    IDEMPOTENCY CHECK
                            |
                            v
                    CONSISTENCY CHECK
                            |
                            v
                          METRICS
                            |
                            v
                  reports/results.json
3. File Router

The File Router is responsible for selecting the processing engine.

Configuration:

SMALL_FILE_THRESHOLD_MB = 200

Routing logic:

file_size_mb <= 200
        |
        v
  Python Batch

file_size_mb > 200
        |
        v
     PySpark

For every execution, the pipeline generates a unique run_id.

The following information is recorded:

run_id
file_name
file_size_mb
threshold
engine_used
routing_reason
4. Processing Engines
Python Batch

Python Batch is used for small files.

Main characteristics:

Streaming CSV processing
No full-file loading into memory
Configurable batch size
Raw loading using MongoDB insert_many()
Batch-level metrics
Batch number tracking
Throughput calculation

Demonstrated execution:

100,000 records
5 batches
PySpark

PySpark is used for large files.

Main characteristics:

SparkSession
Spark DataFrame API
Distributed processing
Fixed schema
Raw values preserved
No Pandas for large files
No unnecessary repartition()
Parallel processing

Demonstrated execution:

30,000,000 records
99 partitions
5. Raw Layer

All incoming records are stored first in:

orders_raw

Each raw record contains:

run_id
source_file
source_row_number
ingested_at
engine_used
raw_record

No cleaning or transformation occurs before Raw Load.

This ensures:

Data lineage
Traceability
Reproducibility
No silent record deletion

A new run_id is generated for every execution, allowing historical raw ingestion records to be preserved.

6. Schema Validation

After Raw Load, records are checked for structural validity.

Validation includes:

Required fields
order_id
Essential field structure
items_json
JSON parsing

Records that fail schema validation are sent directly to:

orders_quarantine

Records that pass continue to Data Quality Validation.

7. Data Quality Classification

After schema validation, each record is classified into one of three categories.

Valid

A record is valid when it contains no quality errors.

quality_status = valid

Valid records:

Go directly to orders_validated
Never enter the correction stage
Correctable

A record is classified as correctable when all detected problems can be safely and deterministically corrected.

Flow:

Correctable
     |
     v
Safe Correction
     |
     v
Re-validation
     |
     +------ Valid ------> Corrected
     |
     +------ Invalid ----> Quarantine

Successfully corrected records receive:

quality_status = corrected
Quarantine

Unsafe, ambiguous, or unrecoverable records are sent to:

orders_quarantine

Examples:

MISSING_ORDER_ID
MISSING_CUSTOMER_ID
INVALID_IMPOSSIBLE_DATE
CORRUPTED_ITEMS_JSON
EMPTY_ITEMS
UNKNOWN_PRICE
AMBIGUOUS_NEGATIVE_VALUE

Every quarantined record includes:

run_id
error_codes
error_details
raw_record

No record is silently dropped.

8. Safe Correction Layer

Only records classified as correctable enter the correction stage.

The project implements 10 required safe correction rules:

Arabic Digits → Latin Digits
Currency normalization → YER
Remove thousand separators
Convert known word prices
Normalize phone numbers when clearly formatted
Fix obvious email errors only
Normalize dates to YYYY-MM-DD when unambiguous
Trim whitespace
Normalize known synonyms
Recalculate total_amount when components are valid

Unsafe values are never guessed or invented.

After correction, the record is validated again.

9. Correction Audit Trail

Every successful correction is recorded.

Correction information includes:

field
original_value
corrected_value
rule_code

Detailed records are stored in:

correction_audit

Each audit record contains:

run_id
order_id
field
original_value
corrected_value
rule_code
corrected_at

This provides full traceability for all modifications.

10. MongoDB Storage Architecture

The project uses four main collections.

orders_raw

Stores every incoming record before cleaning or validation.

Purpose:

Preserve original data
Maintain ingestion history
Support traceability
orders_validated

Stores final business records that are either:

Valid
Successfully corrected

A unique index is created on:

order_id

order_id is used as the Stable Business Key.

orders_quarantine

Stores records that cannot be safely corrected.

Each record includes the reason for quarantine.

correction_audit

Stores detailed information about every applied correction.

11. Upsert Architecture

Final valid records are written to:

orders_validated

using MongoDB Upsert.

The pipeline calculates:

inserted_count
updated_count
unchanged_count

The unique order_id index prevents duplicate business records.

The architecture does not depend on a primary check-then-insert strategy.

12. Idempotency

Idempotency applies to the final business state in:

orders_validated

The same final data can be processed again without creating duplicate business records.

Expected behavior:

First Run
    |
    v
Insert new records

Re-run Same Data
    |
    v
Inserted = 0
Updated = 0
Unchanged > 0

Modified Existing Record
    |
    v
Updated > 0
No Duplicate

Raw ingestion history remains separate because every execution receives a new run_id.

13. Consistency Check

Each raw record must produce exactly one final result.

For every run:

run_raw_count =
run_valid_count
+ run_corrected_count
+ run_quarantine_count

The project verifies this equation after processing.

If the equation does not match, the pipeline reports a consistency problem.

Demonstrated executions passed:

[PASS] raw_loaded = valid + corrected + quarantine
14. Metrics

Execution metrics are saved to:

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

Throughput is calculated using:

throughput = rows_processed / elapsed_seconds
15. Demonstrated Execution
Python Batch
Rows Read        : 100000
Raw Loaded       : 100000

Valid            : 48931
Corrected        : 33340
Quarantine       : 17729

Total Batches    : 5

Consistency      : PASS
PySpark
Rows Read        : 30000000
Raw Loaded       : 30000000

Valid            : 14810722
Corrected        : 10079879
Quarantine       : 5109399

Partitions       : 99
Elapsed Seconds  : 4157.43
Throughput       : 7215.99 rows/second

Consistency      : PASS
16. Architecture Guarantees

The architecture guarantees that:

Every record reaches orders_raw first.
No record is silently deleted.
Each record has exactly one final result.
Valid records do not enter the correction stage.
Only correctable records enter Safe Correction.
Unsafe records are quarantined with reasons.
Corrected records have an Audit Trail.
order_id is the Stable Business Key.
orders_validated uses Upsert.
Duplicate business records are prevented.
Re-running the same data supports Idempotency.
Raw history is preserved using run_id.
Metrics are recorded for every run.
A consistency equation verifies the final processing results.