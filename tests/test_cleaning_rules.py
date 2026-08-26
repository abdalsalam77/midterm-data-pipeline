from src.correction_rules import (
    apply_corrections,
)


# ============================================================
# HELPER
# ============================================================

def get_base_record():
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
        "items_json": (
            '[{"sku":"SKU-001",'
            '"name":"منتج",'
            '"qty":"1",'
            '"unit_price":"49000",'
            '"total":"49000"}]'
        ),
    }


# ============================================================
# TEST 1
# ARABIC DIGITS -> LATIN DIGITS
# ============================================================

def test_arabic_digits_to_latin():

    record = get_base_record()

    record["delivery_cost"] = "٥٠٠٠"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["delivery_cost"]
        == "5000"
    )

    assert any(
        correction["rule_code"]
        == "ARABIC_DIGITS_TO_LATIN"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 2
# CURRENCY -> YER
# ============================================================

def test_currency_normalization():

    record = get_base_record()

    record["currency"] = "ريال يمني"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["currency"]
        == "YER"
    )

    assert any(
        correction["rule_code"]
        == "NORMALIZE_CURRENCY"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 3
# THOUSAND SEPARATORS
# ============================================================

def test_remove_thousand_separators():

    record = get_base_record()

    record["payment_amount"] = "125,000"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["payment_amount"]
        == "125000"
    )

    assert any(
        correction["rule_code"]
        == "REMOVE_THOUSAND_SEPARATORS"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 4
# WORD PRICE -> NUMBER
# ============================================================

def test_word_price_conversion():

    record = get_base_record()

    record["delivery_cost"] = "خمسة آلاف"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["delivery_cost"]
        == "5000"
    )

    assert any(
        correction["rule_code"]
        == "WORD_PRICE_TO_NUMBER"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 5
# PHONE NORMALIZATION
# ============================================================

def test_phone_normalization():

    record = get_base_record()

    record["customer_phone"] = (
        "+967 77 123 4567"
    )

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["customer_phone"]
        == "+967771234567"
    )

    assert any(
        correction["rule_code"]
        == "NORMALIZE_PHONE"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 6
# EMAIL OBVIOUS FIX
# ============================================================

def test_email_correction():

    record = get_base_record()

    record["customer_email"] = (
        "user@@mail..com"
    )

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["customer_email"]
        == "user@mail.com"
    )

    assert any(
        correction["rule_code"]
        == "EMAIL_OBVIOUS_SYMBOL_FIX"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 7
# DATE -> YYYY-MM-DD
# ============================================================

def test_date_normalization():

    record = get_base_record()

    record["order_date"] = "2025/01/31"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["order_date"]
        == "2025-01-31"
    )

    assert any(
        correction["rule_code"]
        == "NORMALIZE_DATE"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 8
# TRIM WHITESPACE
# ============================================================

def test_trim_whitespace():

    record = get_base_record()

    record["customer_name"] = " محمد "

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["customer_name"]
        == "محمد"
    )

    assert any(
        correction["rule_code"]
        == "TRIM_WHITESPACE"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 9
# SYNONYM NORMALIZATION
# ============================================================

def test_synonym_normalization():

    record = get_base_record()

    record["payment_method"] = "كاش"

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["payment_method"]
        == "نقدي"
    )

    assert any(
        correction["rule_code"]
        == "NORMALIZE_SYNONYM"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 10
# RECALCULATE TOTAL AMOUNT
# ============================================================

def test_recalculate_total_amount():

    record = get_base_record()

    record["delivery_cost"] = "1000"

    record["total_amount"] = "999"

    record["items_json"] = (
        '[{"sku":"SKU-001",'
        '"name":"منتج",'
        '"qty":"1",'
        '"unit_price":"49000",'
        '"total":"49000"}]'
    )

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["total_amount"]
        == "50000"
    )

    assert any(
        correction["rule_code"]
        == "RECALCULATE_TOTAL_AMOUNT"
        for correction
        in result["corrections"]
    )


# ============================================================
# TEST 11
# ORIGINAL RECORD MUST NOT CHANGE
# ============================================================

def test_original_record_not_modified():

    record = get_base_record()

    record["currency"] = "ريال يمني"

    original_currency = record["currency"]

    apply_corrections(record)

    assert (
        record["currency"]
        == original_currency
    )


# ============================================================
# TEST 12
# UNKNOWN VALUE MUST NOT BE INVENTED
# ============================================================

def test_unknown_word_price_not_guessed():

    record = get_base_record()

    record["delivery_cost"] = (
        "سعر غير معروف"
    )

    result = apply_corrections(record)

    assert (
        result["corrected_record"]
        ["delivery_cost"]
        == "سعر غير معروف"
    )