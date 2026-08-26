"""
Safe correction rules.

This module applies only clear and deterministic corrections.

The 10 required correction rules are:

1. Arabic Digits -> Latin Digits
2. Currency normalization -> YER
3. Remove thousand separators
4. Convert known word prices
5. Normalize phone when format is clear
6. Fix obvious email errors only
7. Normalize date to YYYY-MM-DD when unambiguous
8. Trim whitespace
9. Normalize known synonyms
10. Recalculate total_amount when components are valid

Unsafe or ambiguous values are not invented.
They remain invalid and will later be quarantined.
"""

import json
import re

from copy import deepcopy
from datetime import datetime


# ============================================================
# ARABIC DIGITS
# ============================================================

ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩",
    "0123456789"
)


# ============================================================
# KNOWN WORD PRICES
#
# Only deterministic values are included.
# Unknown written prices are not guessed.
# ============================================================

WORD_PRICE_MAP = {
    "صفر": "0",
    "مائة": "100",
    "مئه": "100",
    "ألف": "1000",
    "الف": "1000",
    "خمسة آلاف": "5000",
    "خمسه آلاف": "5000",
    "عشرة آلاف": "10000",
    "عشره آلاف": "10000",
    "عشرون ألف": "20000",
    "عشرون الف": "20000",
    "خمسون ألف": "50000",
    "خمسون الف": "50000",
    "مائة ألف": "100000",
    "مائة الف": "100000",
}


# ============================================================
# SYNONYM MAPS
# ============================================================

SYNONYM_MAPS = {
    "status": {
        "تم التأكيد": "مؤكد",
        "مؤكدة": "مؤكد",
        "انتظار": "قيد الانتظار",
        "قيد الإنتظار": "قيد الانتظار",
        "تم الإلغاء": "ملغي",
        "منتهي": "مكتمل",
    },

    "payment_method": {
    "كاش": "نقدي",
    "نقد": "نقدي",

    # القيمة الموجودة فعليًا في ملف البيانات
    "نقدًا عند التسليم": "نقدي",
    "نقداً عند التسليم": "نقدي",
    "نقد عند التسليم": "نقدي",

    "محفظة": "محفظة إلكترونية",
    "محفظه إلكترونية": "محفظة إلكترونية",

    "تحويل": "تحويل بنكي",

    "فيزا": "بطاقة",
},

    "payment_status": {
        "مدفوع": "تم الدفع",
        "تم السداد": "تم الدفع",
        "قيد الانتظار": "بانتظار الدفع",
        "انتظار الدفع": "بانتظار الدفع",
        "غير مدفوع": "بانتظار الدفع",
        "فشلت": "فشل الدفع",
        "تم الإلغاء": "ملغى",
    },

    "delivery_type": {
        "عادي": "عادي",
        "standard": "عادي",
        "express": "سريع",
        "إكسبريس": "سريع",
    }
}


# ============================================================
# AUDIT HELPER
# ============================================================

def add_correction(
    corrections,
    field,
    original_value,
    corrected_value,
    rule_code
):
    """Add a correction only when the value actually changed."""

    if original_value != corrected_value:

        corrections.append({
            "field": field,
            "original_value": original_value,
            "corrected_value": corrected_value,
            "rule_code": rule_code
        })


# ============================================================
# RULE 1
# ARABIC DIGITS -> LATIN DIGITS
# ============================================================

def correct_arabic_digits(
    value,
    field,
    corrections
):
    """Convert Arabic digits to Latin digits."""

    if not isinstance(value, str):
        return value

    corrected = value.translate(
        ARABIC_DIGITS
    )

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "ARABIC_DIGITS_TO_LATIN"
    )

    return corrected


# ============================================================
# RULE 8
# TRIM WHITESPACE
# ============================================================

def correct_trim(
    value,
    field,
    corrections
):
    """Remove leading and trailing whitespace."""

    if not isinstance(value, str):
        return value

    corrected = value.strip()

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "TRIM_WHITESPACE"
    )

    return corrected


# ============================================================
# RULE 2
# CURRENCY -> YER
# ============================================================

def correct_currency(
    value,
    field,
    corrections
):
    """Normalize clear Yemeni Rial representations to YER."""

    if not isinstance(value, str):
        return value

    normalized = value.strip().lower()

    currency_map = {
        "yer": "YER",
        "ريال": "YER",
        "ريال يمني": "YER",
        "الريال اليمني": "YER",
        "yemeni rial": "YER",
        "yemeni riyal": "YER",
    }

    if normalized not in currency_map:
        return value

    corrected = currency_map[
        normalized
    ]

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "NORMALIZE_CURRENCY"
    )

    return corrected


# ============================================================
# RULE 3
# REMOVE THOUSAND SEPARATORS
# ============================================================

def correct_thousand_separators(
    value,
    field,
    corrections
):
    """
    Remove clear thousand separators.

    Only commas and Arabic thousands separator are removed.
    """

    if not isinstance(value, str):
        return value

    corrected = (
        value
        .replace(",", "")
        .replace("٬", "")
    )

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "REMOVE_THOUSAND_SEPARATORS"
    )

    return corrected


# ============================================================
# RULE 4
# KNOWN WORD PRICE
# ============================================================

def correct_word_price(
    value,
    field,
    corrections
):
    """
    Convert only explicitly known written prices.

    Unknown text is not guessed.
    """

    if not isinstance(value, str):
        return value

    normalized = " ".join(
        value.strip().split()
    )

    if normalized not in WORD_PRICE_MAP:
        return value

    corrected = WORD_PRICE_MAP[
        normalized
    ]

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "WORD_PRICE_TO_NUMBER"
    )

    return corrected


# ============================================================
# RULE 5
# PHONE NORMALIZATION
# ============================================================

def correct_phone(
    value,
    field,
    corrections
):
    """
    Normalize phone only when the result is clearly numeric.

    Allowed input separators:
    spaces, hyphens, parentheses.
    """

    if not isinstance(value, str):
        return value

    original = value

    corrected = re.sub(
        r"[\s\-\(\)]+",
        "",
        value
    )

    # Keep + only at the beginning.
    if corrected.startswith("+"):
        numeric_part = corrected[1:]

        if numeric_part.isdigit():
            final_value = "+" + numeric_part
        else:
            return value

    elif corrected.isdigit():
        final_value = corrected

    else:
        return value

    if len(
        final_value.lstrip("+")
    ) < 7:
        return value

    add_correction(
        corrections,
        field,
        original,
        final_value,
        "NORMALIZE_PHONE"
    )

    return final_value


# ============================================================
# RULE 6
# EMAIL CORRECTION
# ============================================================

def correct_email(
    value,
    field,
    corrections
):
    """
    Fix only obvious repeated symbols.

    Examples:
    user@@mail.com -> user@mail.com
    user@mail..com -> user@mail.com

    If still invalid, it remains invalid.
    """

    if not isinstance(value, str):
        return value

    original = value

    corrected = value.strip()

    corrected = re.sub(
        r"@{2,}",
        "@",
        corrected
    )

    corrected = re.sub(
        r"\.{2,}",
        ".",
        corrected
    )

    add_correction(
        corrections,
        field,
        original,
        corrected,
        "EMAIL_OBVIOUS_SYMBOL_FIX"
    )

    return corrected


# ============================================================
# RULE 7
# DATE -> YYYY-MM-DD
# ============================================================

def correct_date(
    value,
    field,
    corrections
):
    """
    Normalize only unambiguous supported date formats.

    Ambiguous dates are not guessed.
    """

    if not isinstance(value, str):
        return value

    original = value

    text = value.strip()

    supported_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    for date_format in supported_formats:

        try:

            parsed = datetime.strptime(
                text,
                date_format
            )

            corrected = parsed.strftime(
                "%Y-%m-%d"
            )

            add_correction(
                corrections,
                field,
                original,
                corrected,
                "NORMALIZE_DATE"
            )

            return corrected

        except ValueError:
            continue

    return value


# ============================================================
# RULE 9
# SYNONYM NORMALIZATION
# ============================================================

def correct_synonym(
    value,
    field,
    corrections
):
    """Normalize only explicitly known synonyms."""

    if not isinstance(value, str):
        return value

    if field not in SYNONYM_MAPS:
        return value

    normalized = value.strip().lower()

    synonym_map = SYNONYM_MAPS[field]

    if normalized not in synonym_map:
        return value

    corrected = synonym_map[
        normalized
    ]

    add_correction(
        corrections,
        field,
        value,
        corrected,
        "NORMALIZE_SYNONYM"
    )

    return corrected


# ============================================================
# HELPERS FOR RULE 10
# ============================================================

def safe_number(value):
    """
    Convert a value to float.

    Returns None when conversion is not safe.
    """

    try:
        return float(
            str(value)
            .replace(",", "")
            .replace("٬", "")
            .strip()
        )

    except (
        TypeError,
        ValueError
    ):
        return None


def format_number(value):
    """
    Store integer values without .0.
    """

    if float(value).is_integer():
        return str(int(value))

    return str(value)


# ============================================================
# RULE 10
# RECALCULATE TOTAL AMOUNT
# ============================================================

def correct_total_amount(
    record,
    corrections
):
    """
    Recalculate total_amount only when:

    - items_json is valid JSON
    - items_json is a non-empty list
    - every item total is numeric
    - delivery_cost is numeric
    """

    items_json = record.get(
        "items_json"
    )

    delivery_cost = safe_number(
        record.get("delivery_cost")
    )

    if delivery_cost is None:
        return

    try:

        items = json.loads(
            items_json
        )

    except (
        TypeError,
        json.JSONDecodeError
    ):
        return

    if (
        not isinstance(items, list)
        or not items
    ):
        return

    items_total = 0.0

    for item in items:

        if not isinstance(item, dict):
            return

        item_total = safe_number(
            item.get("total")
        )

        if item_total is None:
            return

        items_total += item_total

    expected_total = (
        items_total
        + delivery_cost
    )

    corrected = format_number(
        expected_total
    )

    original = record.get(
        "total_amount"
    )

    if original != corrected:

        add_correction(
            corrections,
            "total_amount",
            original,
            corrected,
            "RECALCULATE_TOTAL_AMOUNT"
        )

        record["total_amount"] = corrected


# ============================================================
# ITEMS JSON CORRECTIONS
# ============================================================

def correct_items_json(
    record,
    corrections
):
    """
    Apply safe digit and numeric formatting corrections
    inside items_json.

    This is necessary because item values are stored as JSON.
    """

    items_json = record.get(
        "items_json"
    )

    if not isinstance(
        items_json,
        str
    ):
        return

    try:

        items = json.loads(
            items_json
        )

    except (
        TypeError,
        json.JSONDecodeError
    ):
        return

    if not isinstance(items, list):
        return

    original_json = items_json

    changed = False

    for item in items:

        if not isinstance(item, dict):
            continue

        for field in [
            "qty",
            "unit_price",
            "total"
        ]:

            if field not in item:
                continue

            value = item[field]

            if isinstance(value, str):

                corrected = value.translate(
                    ARABIC_DIGITS
                )

                corrected = (
                    corrected
                    .replace(",", "")
                    .replace("٬", "")
                    .strip()
                )

                if corrected != value:

                    item[field] = corrected
                    changed = True

    if changed:

        corrected_json = json.dumps(
            items,
            ensure_ascii=False
        )

        record["items_json"] = (
            corrected_json
        )

        add_correction(
            corrections,
            "items_json",
            original_json,
            corrected_json,
            "NORMALIZE_ITEMS_NUMERIC_VALUES"
        )


# ============================================================
# MAIN FUNCTION
# ============================================================

def apply_corrections(raw_record):
    """
    Apply the 10 safe correction rules.

    Important:
    - The original raw_record is never modified.
    - Only deterministic corrections are applied.
    - Ambiguous values are left unchanged.
    """

    record = deepcopy(
        raw_record
    )

    corrections = []

    # ========================================================
    # 1. ARABIC DIGITS
    # ========================================================

    arabic_digit_fields = [
        "order_id",
        "customer_id",
        "customer_phone",
        "delivery_cost",
        "payment_amount",
        "total_amount",
    ]

    for field in arabic_digit_fields:

        if field in record:

            record[field] = (
                correct_arabic_digits(
                    record[field],
                    field,
                    corrections
                )
            )

    # ========================================================
    # 8. TRIM WHITESPACE
    # ========================================================

    for field in list(record.keys()):

        if isinstance(
            record[field],
            str
        ):

            record[field] = (
                correct_trim(
                    record[field],
                    field,
                    corrections
                )
            )

    # ========================================================
    # 2. CURRENCY
    # ========================================================

    if "currency" in record:

        record["currency"] = (
            correct_currency(
                record["currency"],
                "currency",
                corrections
            )
        )

    # ========================================================
    # 3. THOUSAND SEPARATORS
    # ========================================================

    numeric_fields = [
        "delivery_cost",
        "payment_amount",
        "total_amount",
    ]

    for field in numeric_fields:

        if field in record:

            record[field] = (
                correct_thousand_separators(
                    record[field],
                    field,
                    corrections
                )
            )

    # ========================================================
    # 4. KNOWN WORD PRICES
    # ========================================================

    for field in numeric_fields:

        if field in record:

            record[field] = (
                correct_word_price(
                    record[field],
                    field,
                    corrections
                )
            )

    # ========================================================
    # ITEMS JSON SAFE NUMERIC CORRECTION
    # ========================================================

    correct_items_json(
        record,
        corrections
    )

    # ========================================================
    # 5. PHONE
    # ========================================================

    if "customer_phone" in record:

        record["customer_phone"] = (
            correct_phone(
                record["customer_phone"],
                "customer_phone",
                corrections
            )
        )

    # ========================================================
    # 6. EMAIL
    # ========================================================

    if "customer_email" in record:

        record["customer_email"] = (
            correct_email(
                record["customer_email"],
                "customer_email",
                corrections
            )
        )

    # ========================================================
    # 7. DATE
    # ========================================================

    if "order_date" in record:

        record["order_date"] = (
            correct_date(
                record["order_date"],
                "order_date",
                corrections
            )
        )

    # ========================================================
    # 9. SYNONYMS
    # ========================================================

    synonym_fields = [
        "status",
        "payment_method",
        "payment_status",
        "delivery_type",
    ]

    for field in synonym_fields:

        if field in record:

            record[field] = (
                correct_synonym(
                    record[field],
                    field,
                    corrections
                )
            )

    # ========================================================
    # 10. RECALCULATE TOTAL
    # ========================================================

    correct_total_amount(
        record,
        corrections
    )

    return {
        "corrected_record": record,
        "corrections": corrections
    }


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":

    test_record = {
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
        )
    }

    result = apply_corrections(
        test_record
    )

    print(
        "\n========== CORRECTION TEST ==========\n"
    )

    print("Corrected record:")

    for key, value in result[
        "corrected_record"
    ].items():

        print(f"{key}: {value}")

    print("\nCorrections:")

    for correction in result[
        "corrections"
    ]:

        print(correction)

    print(
        "\n=====================================\n"
    )