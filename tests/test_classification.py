import json

from src.quality_rules import (
    run_quality_check,
    classify_quality_result,
)

from src.elt_pipeline import process_record


# ============================================================
# BASE VALID RECORD
# ============================================================

def get_valid_record():
    return {
        "order_id": "ORDER-001",
        "order_date": "2025-01-31",
        "status": "مؤكد",
        "customer_id": "CUSTOMER-001",
        "customer_name": "محمد",
        "customer_phone": "+967771234567",
        "customer_email": "user@mail.com",
        "city": "تعز",
        "district": "القاهرة",
        "delivery_type": "عادي",
        "delivery_cost": "1000",
        "payment_method": "نقدي",
        "payment_status": "تم الدفع",
        "payment_amount": "50000",
        "currency": "YER",
        "total_amount": "50000",
        "items_json": json.dumps(
            [
                {
                    "sku": "SKU-001",
                    "name": "منتج",
                    "qty": "1",
                    "unit_price": "49000",
                    "total": "49000",
                }
            ],
            ensure_ascii=False,
        ),
    }


# ============================================================
# TEST 1
# VALID RECORD
# ============================================================

def test_valid_record_classification():

    record = get_valid_record()

    parsed_items = json.loads(
        record["items_json"]
    )

    result = run_quality_check(
        record,
        parsed_items,
    )

    assert result["classification"] == "valid"

    assert result["error_codes"] == []


# ============================================================
# TEST 2
# CORRECTABLE RECORD
# ============================================================

def test_correctable_record_classification():

    record = get_valid_record()

    record["currency"] = "ريال يمني"

    parsed_items = json.loads(
        record["items_json"]
    )

    result = run_quality_check(
        record,
        parsed_items,
    )

    assert result["classification"] == "correctable"

    assert "INVALID_CURRENCY" in (
        result["error_codes"]
    )


# ============================================================
# TEST 3
# MISSING ORDER ID -> QUARANTINE
# ============================================================

def test_missing_order_id_quarantine():

    record = get_valid_record()

    record["order_id"] = ""

    parsed_items = json.loads(
        record["items_json"]
    )

    result = run_quality_check(
        record,
        parsed_items,
    )

    assert result["classification"] == "quarantine"

    assert "MISSING_ORDER_ID" in (
        result["error_codes"]
    )


# ============================================================
# TEST 4
# IMPOSSIBLE DATE -> QUARANTINE
# ============================================================

def test_impossible_date_quarantine():

    record = get_valid_record()

    record["order_date"] = "2025-99-99"

    parsed_items = json.loads(
        record["items_json"]
    )

    result = run_quality_check(
        record,
        parsed_items,
    )

    assert result["classification"] == "quarantine"

    assert "INVALID_IMPOSSIBLE_DATE" in (
        result["error_codes"]
    )


# ============================================================
# TEST 5
# UNKNOWN ERROR -> QUARANTINE
# ============================================================

def test_unknown_error_quarantine():

    result = {
        "error_codes": [
            "UNKNOWN_UNSAFE_ERROR"
        ]
    }

    classification = (
        classify_quality_result(
            result
        )
    )

    assert classification == "quarantine"


# ============================================================
# TEST 6
# VALID MUST NOT ENTER CORRECTION
# ============================================================

def test_valid_record_does_not_enter_correction():

    record = get_valid_record()

    result = process_record(
        record
    )

    assert result["final_status"] == "valid"

    assert result["corrections"] == []


# ============================================================
# TEST 7
# CORRECTABLE RECORD -> CORRECTED
# ============================================================

def test_correctable_record_is_corrected():

    record = get_valid_record()

    record["currency"] = "ريال يمني"

    result = process_record(
        record
    )

    assert result["final_status"] == "corrected"

    assert len(
        result["corrections"]
    ) > 0


# ============================================================
# TEST 8
# MISSING ORDER ID MUST NOT BE CORRECTED
# ============================================================

def test_missing_order_id_does_not_enter_correction():

    record = get_valid_record()

    record["order_id"] = ""

    result = process_record(
        record
    )

    assert result["final_status"] == "quarantine"

    assert result["corrections"] == []


# ============================================================
# TEST 9
# CORRUPTED ITEMS JSON -> QUARANTINE
# ============================================================

def test_corrupted_items_json_quarantine():

    record = get_valid_record()

    record["items_json"] = (
        '[{"sku": "SKU-001",'
        '"qty": 1'
    )

    result = process_record(
        record
    )

    assert result["final_status"] == "quarantine"


# ============================================================
# TEST 10
# CLASSIFICATION PRIORITY:
# QUARANTINE ERROR WINS
# ============================================================

def test_quarantine_error_has_priority():

    result = {
        "error_codes": [
            "INVALID_CURRENCY",
            "MISSING_ORDER_ID",
        ]
    }

    classification = (
        classify_quality_result(
            result
        )
    )

    assert classification == "quarantine"