from src.schema_validation import validate_schema
from src.quality_rules import run_quality_check
from src.correction_rules import apply_corrections


def process_record(raw_record):
    """
    Process one record through the ELT quality pipeline.

    Flow:
        1. Schema validation
        2. Quality validation
        3. Classification
        4. Safe correction for correctable records only
        5. Re-validation after correction

    Final status:
        - validated
        - quarantine
    """

    # ============================================================
    # 1. SCHEMA VALIDATION
    # ============================================================

    schema_result = validate_schema(raw_record)

    if not schema_result["schema_valid"]:
        return {
            "final_status": "quarantine",
            "record": raw_record,
            "error_codes": [
                error["code"]
                for error in schema_result["schema_errors"]
            ],
            "error_details": [
                error["message"]
                for error in schema_result["schema_errors"]
            ],
            "corrections": [],
        }

    parsed_items = schema_result["parsed_items"]

    # ============================================================
    # 2. QUALITY CHECK
    # ============================================================

    quality_result = run_quality_check(
        raw_record,
        parsed_items,
    )

    classification = quality_result["classification"]

    # ============================================================
    # 3. VALID
    #
    # Valid records must NEVER enter the correction stage.
    # ============================================================

    if classification == "valid":
        return {
            "final_status": "valid",
        "record": raw_record,
        "error_codes": [],
        "error_details": [],
        "corrections": [],
    }

    # ============================================================
    # 4. QUARANTINE
    #
    # Unsafe or unrecoverable records must NOT enter correction.
    # ============================================================

    if classification == "quarantine":
        return {
            "final_status": "quarantine",
            "record": raw_record,
            "error_codes": quality_result["error_codes"],
            "error_details": quality_result["error_details"],
            "corrections": [],
        }

    # ============================================================
    # 5. CORRECTION STAGE
    #
    # Only records classified as correctable reach this stage.
    # ============================================================

    correction_result = apply_corrections(raw_record)

    corrected_record = correction_result[
        "corrected_record"
    ]

    corrections = correction_result[
        "corrections"
    ]

    # ============================================================
    # 6. SCHEMA VALIDATION AFTER CORRECTION
    # ============================================================

    corrected_schema = validate_schema(
        corrected_record
    )

    if not corrected_schema["schema_valid"]:
        return {
            "final_status": "quarantine",
            "record": corrected_record,
            "error_codes": [
                error["code"]
                for error in corrected_schema[
                    "schema_errors"
                ]
            ],
            "error_details": [
                error["message"]
                for error in corrected_schema[
                    "schema_errors"
                ]
            ],
            "corrections": corrections,
        }

    corrected_items = corrected_schema[
        "parsed_items"
    ]

    # ============================================================
    # 7. QUALITY CHECK AFTER CORRECTION
    # ============================================================

    corrected_quality = run_quality_check(
        corrected_record,
        corrected_items,
    )

    # ============================================================
    # 8. FINAL DECISION
    # ============================================================

    if corrected_quality["classification"] == "valid":
        return {
            "final_status": "corrected",
            "record": corrected_record,
            "error_codes": [],
            "error_details": [],
            "corrections": corrections,
        }

    # ============================================================
    # 9. STILL INVALID AFTER CORRECTION
    # ============================================================

    return {
        "final_status": "quarantine",
        "record": corrected_record,
        "error_codes": corrected_quality[
            "error_codes"
        ],
        "error_details": corrected_quality[
            "error_details"
        ],
        "corrections": corrections,
    }


# ================================================================
# TEST HELPER
# ================================================================

def print_result(test_name, result):
    """Print a pipeline test result clearly."""

    print("\n" + "=" * 60)
    print(f"TEST: {test_name}")
    print("=" * 60)

    print(
        f"\nFinal status: "
        f"{result['final_status']}"
    )

    print("\nFinal record:")

    for key, value in result["record"].items():
        print(f"{key}: {value}")

    print("\nError codes:")

    if result["error_codes"]:
        for error in result["error_codes"]:
            print(f"- {error}")
    else:
        print("None")

    print("\nCorrections:")

    if result["corrections"]:
        for correction in result["corrections"]:
            print(correction)
    else:
        print("None")


# ================================================================
# MANUAL TESTS
# ================================================================

if __name__ == "__main__":

    # ============================================================
    # TEST 1: CORRECTABLE
    #
    # Expected final status: corrected
    # ============================================================

    correctable_record = {
        "order_id": " طلب-١٢٣ ",
        "order_date": "2025/01/31",
        "status": "تم التأكيد",
        "customer_id": " عميل-١ ",
        "customer_name": " محمد ",
        "customer_phone": "+967 77 123 4567",
        "customer_email": "user@@mail..com",
        "city": " تعز ",
        "district": " القاهرة ",
        "delivery_type": "express",
        "delivery_cost": "٥,٠٠٠",
        "payment_method": "كاش",
        "payment_status": "مدفوع",
        "payment_amount": "125,000",
        "currency": " ريال يمني ",
        "total_amount": "999",
        "items_json": (
            '[{"sku":"SKU-1",'
            '"name":"منتج",'
            '"qty":"١",'
            '"unit_price":"١٢٠,٠٠٠",'
            '"total":"120000"}]'
        ),
    }

    result = process_record(correctable_record)

    print_result(
        "CORRECTABLE RECORD",
        result,
    )

    # ============================================================
    # TEST 2: VALID
    #
    # Expected final status: validated
    # Must NOT enter correction stage.
    # ============================================================

    valid_record = {
        "order_id": "ORDER-001",
        "order_date": "2025-01-31",
        "status": "مؤكد",
        "customer_id": "CUSTOMER-001",
        "customer_name": "محمد",
        "customer_phone": "+967771234567",
        "customer_email": "user@mail.com",
        "city": "تعز",
        "district": "القاهرة",
        "delivery_type": "سريع",
        "delivery_cost": "5000",
        "payment_method": "نقدي",
        "payment_status": "تم الدفع",
        "payment_amount": "125000",
        "currency": "YER",
        "total_amount": "125000",
        "items_json": (
            '[{"sku":"SKU-1",'
            '"name":"منتج",'
            '"qty":"1",'
            '"unit_price":"120000",'
            '"total":"120000"}]'
        ),
    }

    result = process_record(valid_record)

    print_result(
        "VALID RECORD",
        result,
    )

    # ============================================================
    # TEST 3: QUARANTINE
    #
    # Missing order_id is unsafe and must NOT enter correction.
    # ============================================================

    quarantine_record = {
        "order_id": "",
        "order_date": "2025-01-31",
        "status": "مؤكد",
        "customer_id": "CUSTOMER-003",
        "customer_name": "أحمد",
        "customer_phone": "+967771234567",
        "customer_email": "ahmed@mail.com",
        "city": "صنعاء",
        "district": "التحرير",
        "delivery_type": "عادي",
        "delivery_cost": "1000",
        "payment_method": "نقدي",
        "payment_status": "تم الدفع",
        "payment_amount": "50000",
        "currency": "YER",
        "total_amount": "50000",
        "items_json": (
            '[{"sku":"SKU-3",'
            '"name":"منتج",'
            '"qty":"1",'
            '"unit_price":"49000",'
            '"total":"49000"}]'
        ),
    }

    result = process_record(quarantine_record)

    print_result(
        "QUARANTINE RECORD",
        result,
    )

    print("\n" + "=" * 60)
    print("ALL ELT PIPELINE TESTS FINISHED")
    print("=" * 60)