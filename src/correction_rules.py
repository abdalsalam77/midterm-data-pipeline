"""
Safe correction rules.

This module applies only clear and deterministic corrections.

The correction output is designed to be compatible with quality_rules.py.
Every corrected record must be re-validated by the Quality stage.
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
# Compatible with quality_rules.py allowed values
# ============================================================

SYNONYM_MAPS = {

    "status": {
        "تم التأكيد": "مؤكد",
        "مؤكدة": "مؤكد",
        "انتظار": "قيد الانتظار",
        "قيد الإنتظار": "قيد الانتظار",
        "تم الإلغاء": "ملغي",

        # Quality allows "تم التسليم", not "مكتمل"
        "منتهي": "تم التسليم",
    },

    "payment_method": {

        # Quality allows "نقدًا عند التسليم"
        "كاش": "نقدًا عند التسليم",
        "نقد": "نقدًا عند التسليم",
        "نقدي": "نقدًا عند التسليم",
        "نقدًا عند التسليم": "نقدًا عند التسليم",
        "نقداً عند التسليم": "نقدًا عند التسليم",
        "نقد عند التسليم": "نقدًا عند التسليم",

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
    """
    Add a correction only when the value actually changed.
    """

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
    """
    Convert Arabic digits to Latin digits.
    """

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
    """
    Remove leading and trailing whitespace.
    """

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
    """
    Normalize clear Yemeni Rial representations to YER.
    """

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
    Quality requires exactly:

        7XXXXXXXX

    Supported deterministic forms:

        7XXXXXXXX
        +9677XXXXXXXX
        9677XXXXXXXX

    Separators such as spaces, hyphens and parentheses
    are removed first.

    No digits are invented.
    """

    if not isinstance(value, str):
        return value

    original = value

    value = value.translate(
        ARABIC_DIGITS
    ).strip()

    cleaned = re.sub(
        r"[\s\-\(\)]",
        "",
        value
    )

    # Already valid according to Quality
    if re.fullmatch(
        r"7\d{8}",
        cleaned
    ):
        return value

    digits = None

    # +9677XXXXXXXX
    if (
        cleaned.startswith("+967")
        and cleaned[4:].isdigit()
    ):
        digits = cleaned[4:]

    # 9677XXXXXXXX
    elif (
        cleaned.startswith("967")
        and cleaned[3:].isdigit()
    ):
        digits = cleaned[3:]

    # Local format
    elif (
        cleaned.isdigit()
        and len(cleaned) == 9
    ):
        digits = cleaned

    # Never invent or guess a phone number
    if digits is None:
        return value

    # Final result MUST satisfy Quality exactly
    if not re.fullmatch(
        r"7\d{8}",
        digits
    ):
        return value

    add_correction(
        corrections,
        field,
        original,
        digits,
        "NORMALIZE_PHONE"
    )

    return digits


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
    Fix only obvious repeated-symbol errors.

    Examples:

        user@@mail.com
        user@mail..com

    No username/domain is invented.
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

    # Same basic format expected by Quality
    valid_pattern = (
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    if not re.fullmatch(
        valid_pattern,
        corrected
    ):
        return value

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
# DATE NORMALIZATION
# ============================================================

def correct_date(
    value,
    field,
    corrections
):
    """
    Quality valid format:

        YYYY-MM-DDTHH:MM:SS

    Quality correctable formats:

        YYYY/MM/DD
        DD/MM/YYYY
        DD-MM-YYYY

    Date-only values are deterministically assigned
    midnight (00:00:00).
    """

    if not isinstance(value, str):
        return value

    original = value

    text = value.strip()

    # Already valid
    try:

        datetime.strptime(
            text,
            "%Y-%m-%dT%H:%M:%S"
        )

        return value

    except ValueError:
        pass

    correctable_formats = [
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for date_format in correctable_formats:

        try:

            parsed = datetime.strptime(
                text,
                date_format
            )

            corrected = parsed.strftime(
                "%Y-%m-%dT00:00:00"
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

    # Unknown / impossible date remains unchanged
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
    """
    Normalize only explicitly known synonyms.
    """

    if not isinstance(value, str):
        return value

    if field not in SYNONYM_MAPS:
        return value

    normalized = value.strip().lower()

    synonym_map = SYNONYM_MAPS[
        field
    ]

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
    Convert a value to float safely.

    Arabic digits and thousand separators
    are handled here.
    """

    try:

        return float(
            str(value)
            .translate(ARABIC_DIGITS)
            .replace(",", "")
            .replace("٬", "")
            .strip()
        )

    except (
        TypeError,
        ValueError
    ):

        return None


def numeric_value(value):
    """
    Convert safe numeric values to actual
    int/float values.

    This is especially important for qty because
    Quality treats numeric strings as INVALID_QTY.
    """

    number = safe_number(
        value
    )

    if number is None:
        return None

    if number.is_integer():
        return int(number)

    return number


def format_number(value):
    """
    Store integer values without .0.
    """

    if float(value).is_integer():
        return str(
            int(value)
        )

    return str(value)


# ============================================================
# ITEMS JSON CORRECTION
# ============================================================

def correct_items_json(
    record,
    corrections
):
    """
    Normalize item numeric fields.

    Important:

        "2" -> 2

    for qty, because Quality considers
    numeric qty strings invalid.

    Negative values are NOT corrected.
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

    if (
        not isinstance(items, list)
        or not items
    ):
        return

    original_json = items_json

    changed = False

    for item in items:

        if not isinstance(
            item,
            dict
        ):
            continue

        for field in (
            "qty",
            "unit_price",
            "total"
        ):

            if field not in item:
                continue

            value = item[field]

            if not isinstance(
                value,
                str
            ):
                continue

            translated = (
                value
                .translate(
                    ARABIC_DIGITS
                )
                .replace(",", "")
                .replace("٬", "")
                .strip()
            )

            number = numeric_value(
                translated
            )

            # Unknown text is not guessed
            if number is None:
                continue

            # Never turn a negative value into a valid one
            if number < 0:
                continue

            # qty must be positive
            if (
                field == "qty"
                and number <= 0
            ):
                continue

            if value != number:

                item[field] = number

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
# RULE 10
# RECALCULATE TOTAL AMOUNT
# ============================================================

def correct_total_amount(
    record,
    corrections
):
    """
    Recalculate:

        sum(item.total) + delivery_cost

    only when all components are safe.
    """

    items_json = record.get(
        "items_json"
    )

    delivery_cost = safe_number(
        record.get(
            "delivery_cost"
        )
    )

    if (
        delivery_cost is None
        or delivery_cost < 0
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

    if (
        not isinstance(items, list)
        or not items
    ):
        return

    items_total = 0.0

    for item in items:

        if not isinstance(
            item,
            dict
        ):
            return

        item_total = safe_number(
            item.get("total")
        )

        if (
            item_total is None
            or item_total < 0
        ):
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

        record["total_amount"] = (
            corrected
        )


# ============================================================
# MAIN FUNCTION
# ============================================================

def apply_corrections(
    raw_record
):
    """
    Apply safe corrections.

    The raw record is never modified.

    The returned record MUST be passed again
    through Quality validation.
    """

    record = deepcopy(
        raw_record
    )

    corrections = []

    # ========================================================
    # RULE 1
    # ARABIC DIGITS
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
    # RULE 8
    # TRIM
    # ========================================================

    for field in list(
        record.keys()
    ):

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
    # RULE 2
    # CURRENCY
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
    # RULE 3
    # THOUSAND SEPARATORS
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
    # RULE 4
    # KNOWN WORD PRICES
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
    # ITEMS JSON
    # ========================================================

    correct_items_json(
        record,
        corrections
    )

    # ========================================================
    # RULE 5
    # PHONE
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
    # RULE 6
    # EMAIL
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
    # RULE 7
    # DATE
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
    # RULE 9
    # SYNONYMS
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
    # RULE 10
    # RECALCULATE TOTAL
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
# END
# ============================================================