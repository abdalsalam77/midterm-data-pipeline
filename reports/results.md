# Pipeline Execution Results

## Overview

This document contains the demonstrated execution results of the Hybrid Data Pipeline.

Two processing modes were successfully tested:

1. Python Batch Processing for a small sample.
2. PySpark Distributed Processing for the large dataset.

Both executions completed successfully and passed the consistency check.

---

# 1. Python Batch Execution

## Input

```text
File: Small Sample
Rows: 100,000
Engine: python_batch
Batch Size: 20,000
Total Batches: 5
Execution Results
Rows Read        : 100000
Raw Loaded       : 100000

Valid            : 48931
Corrected        : 33340
Quarantine       : 17729
Upsert Results
Inserted         : 0
Updated          : 822
Unchanged        : 81449
Performance
Elapsed Time     : 48.02 seconds
Throughput       : 2082.31 rows/second
Total Batches    : 5
Consistency Check
100000 = 48931 + 33340 + 17729

Result:

[PASS] raw_loaded = valid + corrected + quarantine

The Python Batch engine successfully processed the small sample using streaming and configurable batches.

2. PySpark Large File Execution
Input
File: orders_huge_mixed_quality.csv
Rows: 30,000,000
Engine: pyspark
Write Batch Size: 10,000
Spark Configuration
Spark Master             : local[*]
Spark Partitions         : 99
Default Parallelism      : 12
Partition Max Bytes      : 67108864
Minimum Partition Number : 12

The large file was processed using the Spark DataFrame API.

No Pandas was used.

No unnecessary repartition() operation was used.

Data Loading Results
Rows Read               : 30000000
Raw Records Loaded      : 30000000

All records reached the Raw Layer before validation or correction.

Data Quality Results
Valid                   : 14810722
Corrected               : 10079879
Quarantine              : 5109399

Every raw record received exactly one final outcome.

Upsert Results
Inserted                : 693105
Updated                 : 202367
Unchanged               : 23995129

The pipeline used order_id as the Stable Business Key.

MongoDB Upsert prevented duplicate business records.

Spark Performance
Partitions              : 99
Total Time              : 4157.43 seconds
Overall Throughput      : 7215.99 rows/second

The pipeline processed 30 million records using distributed PySpark processing.

Consistency Check
30000000
=
14810722
+
10079879
+
5109399

Result:

[PASS] raw_loaded = valid + corrected + quarantine

Consistency Difference:

0

This confirms that every raw record resulted in exactly one of:

Valid
Corrected
Quarantine
3. Automated Tests

The automated test suite was executed using:

python -m pytest tests -v

Result:

22 passed in 0.77s

The tests covered:

Cleaning Rules
Arabic digits to Latin digits
Currency normalization
Thousand separator removal
Word price conversion
Phone normalization
Email correction
Date normalization
Whitespace trimming
Synonym normalization
Total amount recalculation
Original record protection
Unknown word prices are not guessed
Classification
Valid record classification
Correctable record classification
Missing order_id
Impossible date
Unknown error handling
Valid records do not enter correction
Correctable records are corrected
Quarantine records do not enter correction
Corrupted items JSON
Quarantine error priority
4. Processing Engine Comparison
Feature	Python Batch	PySpark
Input Size Demonstrated	100,000 rows	30,000,000 rows
Processing Model	Streaming Batches	Distributed Processing
Engine	Python	PySpark
Batches / Partitions	5 Batches	99 Partitions
Processing Time	48.02 sec	4157.43 sec
Throughput	2082.31 rows/sec	7215.99 rows/sec
Consistency Check	PASS	PASS

Python Batch is suitable for smaller files where streaming and batch processing are sufficient.

PySpark is suitable for large files requiring distributed processing and parallel execution.

5. Final Results

The Hybrid Data Pipeline successfully demonstrated:

File routing based on a 200 MB threshold.
Python Batch processing for the 100,000-row sample.
PySpark processing for the 30,000,000-row dataset.
Raw-first data ingestion.
Schema and data quality validation.
Separation of Valid, Corrected, and Quarantine records.
Safe deterministic correction rules.
Correction Audit Trail.
Quarantine with error reasons.
MongoDB Upsert.
Stable Business Key using order_id.
Idempotent final business storage.
Consistency validation.
Execution metrics.
Automated testing with 22 passing tests.
Final Status
PYTHON BATCH       : SUCCESS
PYSPARK            : SUCCESS
CONSISTENCY CHECK  : PASS
AUTOMATED TESTS    : 22 PASSED
PROJECT STATUS     : COMPLETED


