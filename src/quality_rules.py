"""
Data Quality Rules.

This module is executed after schema validation.

Responsibilities:
1. Validate data quality.
2. Detect quality issues.
3. Classify the record as:
   - valid
   - correctable
   - quarantine

No data is silently deleted.
No unsafe correction is performed.
"""

import re
from datetime import datetime


# ============================================================
# STANDARD / ALLOWED VALUES
# ============================================================

ALLOWED_STATUSES = {
    "مؤكد",
    "قيد الانتظار",
    "قيد الشحن",
    "تم التسليم",
    "ملغي",
    "مرتجع",
}

ALLOWED_PAYMENT_METHODS = {
    "نقدي",
    "محفظة إلكترونية",
    "تحويل بنكي",
    "بطاقة",
}

ALLOWED_PAYMENT_STATUSES = {
    "تم الدفع",
    "بانتظار الدفع",
    "قيد الدفع",
    "فشل الدفع",
    "ملغى",
}

ALLOWED_DELIVERY_TYPES = {
    "عادي",
    "سريع",
}

STANDARD_CURRENCY = "YER"


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

CORRECTABLE_ERRORS = {
    "INVALID_CURRENCY",
    "INVALID_DATE_FORMAT",
    "INVALID_EMAIL",
    "INVALID_PHONE",
    "INVALID_STATUS",
    "INVALID_PAYMENT_STATUS",
    "INVALID_PAYMENT_METHOD",
    "INVALID_DELIVERY_TYPE",
    "INVALID_DELIVERY_COST",
    "INVALID_PAYMENT_AMOUNT",
    "INVALID_QTY",
    "INVALID_ITEM_TOTAL",
    "UNKNOWN_PRICE",
    "UNKNOWN_TOTAL_AMOUNT",
    "INVALID_TOTAL_AMOUNT",
    "TOTAL_AMOUNT_MISMATCH",
    "WHITESPACE_VALUE",
}


QUARANTINE_ERRORS = {
    "MISSING_ORDER_ID",
    "MISSING_CUSTOMER_ID",
    "INVALID_IMPOSSIBLE_DATE",
    "EMPTY_ITEMS",
    "NEGATIVE_QTY",
    "NEGATIVE_UNIT_PRICE",
    "AMBIGUOUS_NEGATIVE_VALUE",
    "MULTIPLE_CONFLICTING_ERRORS",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_empty(value):
    """Return True if value is None or empty."""
    return value is None or str(value).strip() == ""


def contains_extra_whitespace(value):
    """Check for leading or trailing whitespace."""
    if value is None:
        return False

    text = str(value)
    return text != text.strip()


def is_valid_email(email):
    """
    Basic email validation.

    Obvious corrections are handled later.
    """
    if is_empty(email):
        return False

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return re.match(
        pattern,
        str(email).strip()
    ) is not None


def is_valid_phone(phone):
    """
    Basic phone validation.
    """

    if is_empty(phone):
        return False

    cleaned = re.sub(
        r"[\s\-()]",
        "",
        str(phone)
    )

    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    return (
        cleaned.isdigit()
        and len(cleaned) >= 7
    )


def validate_date(value):
    """
    Validate order date.

    Standard formats are valid.

    Clearly understandable alternative formats
    are marked as correctable.

    Impossible calendar dates are quarantined.
    """

    if is_empty(value):
        return {
            "valid": False,
            "impossible": False,
        }

    text = str(value).strip()

    valid_formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    for date_format in valid_formats:

        try:

            datetime.strptime(
                text,
                date_format
            )

            return {
                "valid": True,
                "impossible": False,
            }

        except ValueError:
            continue

    correctable_formats = [
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for date_format in correctable_formats:

        try:

            datetime.strptime(
                text,
                date_format
            )

            return {
                "valid": False,
                "impossible": False,
            }

        except ValueError:
            continue

    date_like_pattern = (
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"
    )

    if re.match(
        date_like_pattern,
        text
    ):

        return {
            "valid": False,
            "impossible": True,
        }

    return {
        "valid": False,
        "impossible": False,
    }


def to_number(value):
    """
    Strict numeric conversion.

    This function intentionally does NOT:
    - convert Arabic digits
    - remove commas
    - perform cleaning

    Cleaning belongs to correction_rules.py.
    """

    try:

        return float(
            str(value).strip()
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# ITEMS QUALITY VALIDATION
# ============================================================

def validate_items_quality(items):
    """
    Validate item numeric fields.
    """

    errors = []

    if (
        not isinstance(items, list)
        or len(items) == 0
    ):

        errors.append(
            "EMPTY_ITEMS"
        )

        return errors

    for index, item in enumerate(items):

        qty = item.get("qty")

        unit_price = item.get(
            "unit_price"
        )

        total = item.get("total")

        qty_number = to_number(
            qty
        )

        price_number = to_number(
            unit_price
        )

        total_number = to_number(
            total
        )

        # QTY

        if qty_number is None:

            errors.append(
                f"INVALID_QTY:item[{index}]"
            )

        elif qty_number <= 0:

            errors.append(
                f"NEGATIVE_QTY:item[{index}]"
            )

        # UNIT PRICE

        if price_number is None:

            errors.append(
                f"UNKNOWN_PRICE:item[{index}]"
            )

        elif price_number < 0:

            errors.append(
                f"NEGATIVE_UNIT_PRICE:item[{index}]"
            )

        # ITEM TOTAL

        if total_number is None:

            errors.append(
                f"INVALID_ITEM_TOTAL:item[{index}]"
            )

        elif total_number < 0:

            errors.append(
                f"AMBIGUOUS_NEGATIVE_VALUE:item[{index}]"
            )

    return errors


# ============================================================
# TOTAL AMOUNT VALIDATION
# ============================================================

def validate_total_amount(
    record,
    parsed_items
):
    """
    Validate total_amount against:

    sum(item totals) + delivery_cost
    """

    total_amount = to_number(
        record.get("total_amount")
    )

    delivery_cost = to_number(
        record.get("delivery_cost")
    )

    if total_amount is None:

        return [
            "UNKNOWN_TOTAL_AMOUNT"
        ]

    if total_amount < 0:

        return [
            "AMBIGUOUS_NEGATIVE_VALUE"
        ]

    if delivery_cost is None:

        return [
            "INVALID_DELIVERY_COST"
        ]

    if delivery_cost < 0:

        return [
            "AMBIGUOUS_NEGATIVE_VALUE"
        ]

    calculated_items_total = 0.0

    for item in parsed_items:

        item_total = to_number(
            item.get("total")
        )

        if item_total is None:

            return [
                "INVALID_ITEM_TOTAL"
            ]

        calculated_items_total += (
            item_total
        )

    expected_total = (
        calculated_items_total
        + delivery_cost
    )

    if (
        abs(
            total_amount
            - expected_total
        )
        > 0.01
    ):

        return [
            "TOTAL_AMOUNT_MISMATCH"
        ]

    return []


# ============================================================
# MAIN QUALITY VALIDATION
# ============================================================

def validate_data_quality(
    record,
    parsed_items
):
    """
    Validate data quality after schema validation.
    """

    error_codes = []
    error_details = []

    # ========================================================
    # BUSINESS KEYS
    # ========================================================

    if is_empty(
        record.get("order_id")
    ):

        error_codes.append(
            "MISSING_ORDER_ID"
        )

        error_details.append(
            "order_id is missing or empty."
        )

    if is_empty(
        record.get("customer_id")
    ):

        error_codes.append(
            "MISSING_CUSTOMER_ID"
        )

        error_details.append(
            "customer_id is missing or empty."
        )

    # ========================================================
    # DATE
    # ========================================================

    date_result = validate_date(
        record.get("order_date")
    )

    if not date_result["valid"]:

        if date_result["impossible"]:

            error_codes.append(
                "INVALID_IMPOSSIBLE_DATE"
            )

            error_details.append(
                "order_date is invalid or impossible."
            )

        else:

            error_codes.append(
                "INVALID_DATE_FORMAT"
            )

            error_details.append(
                "order_date format is not standard."
            )

    # ========================================================
    # EMAIL
    # ========================================================

    if not is_valid_email(
        record.get("customer_email")
    ):

        error_codes.append(
            "INVALID_EMAIL"
        )

        error_details.append(
            "customer_email format is invalid."
        )

    # ========================================================
    # PHONE
    # ========================================================

    if not is_valid_phone(
        record.get("customer_phone")
    ):

        error_codes.append(
            "INVALID_PHONE"
        )

        error_details.append(
            "customer_phone format is invalid."
        )

    # ========================================================
    # CURRENCY
    # ========================================================

    currency = str(
        record.get("currency", "")
    ).strip()

    if currency != STANDARD_CURRENCY:

        error_codes.append(
            "INVALID_CURRENCY"
        )

        error_details.append(
            f"currency must be "
            f"{STANDARD_CURRENCY}."
        )

    # ========================================================
    # STATUS
    # ========================================================

    status = str(
        record.get("status", "")
    ).strip()

    if status not in ALLOWED_STATUSES:

        error_codes.append(
            "INVALID_STATUS"
        )

        error_details.append(
            "status is not allowed."
        )

    # ========================================================
    # PAYMENT METHOD
    # ========================================================

    payment_method = str(
        record.get(
            "payment_method",
            ""
        )
    ).strip()

    if (
        payment_method
        not in ALLOWED_PAYMENT_METHODS
    ):

        error_codes.append(
            "INVALID_PAYMENT_METHOD"
        )

        error_details.append(
            "payment_method is not allowed."
        )

    # ========================================================
    # PAYMENT STATUS
    # ========================================================

    payment_status = str(
        record.get(
            "payment_status",
            ""
        )
    ).strip()

    if (
        payment_status
        not in ALLOWED_PAYMENT_STATUSES
    ):

        error_codes.append(
            "INVALID_PAYMENT_STATUS"
        )

        error_details.append(
            "payment_status is not allowed."
        )

    # ========================================================
    # DELIVERY TYPE
    # ========================================================

    delivery_type = str(
        record.get(
            "delivery_type",
            ""
        )
    ).strip()

    if (
        delivery_type
        not in ALLOWED_DELIVERY_TYPES
    ):

        error_codes.append(
            "INVALID_DELIVERY_TYPE"
        )

        error_details.append(
            "delivery_type is not allowed."
        )

    # ========================================================
    # NUMERIC FIELDS
    # ========================================================

    numeric_fields = [
        "delivery_cost",
        "payment_amount",
        "total_amount",
    ]

    for field in numeric_fields:

        value = to_number(
            record.get(field)
        )

        if value is None:

            error_codes.append(
                f"INVALID_{field.upper()}"
            )

            error_details.append(
                f"{field} is not numeric."
            )

        elif value < 0:

            error_codes.append(
                "AMBIGUOUS_NEGATIVE_VALUE"
            )

            error_details.append(
                f"{field} cannot safely "
                f"be negative."
            )

    # ========================================================
    # WHITESPACE
    # ========================================================

    fields_to_check = [
        "order_id",
        "customer_id",
        "customer_name",
        "customer_phone",
        "customer_email",
        "city",
        "district",
        "status",
        "currency",
    ]

    for field in fields_to_check:

        if contains_extra_whitespace(
            record.get(field)
        ):

            error_codes.append(
                f"WHITESPACE_VALUE:{field}"
            )

            error_details.append(
                f"{field} contains "
                f"leading or trailing whitespace."
            )

    # ========================================================
    # ITEMS
    # ========================================================

    item_errors = validate_items_quality(
        parsed_items
    )

    for error in item_errors:

        error_codes.append(
            error
        )

        error_details.append(
            f"Items quality problem: "
            f"{error}"
        )

    # ========================================================
    # TOTAL AMOUNT
    # ========================================================

    total_errors = validate_total_amount(
        record,
        parsed_items,
    )

    for error in total_errors:

        error_codes.append(
            error
        )

        error_details.append(
            f"Total amount validation problem: "
            f"{error}"
        )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique_error_codes = list(
        dict.fromkeys(
            error_codes
        )
    )

    unique_error_details = list(
        dict.fromkeys(
            error_details
        )
    )

    return {
        "quality_valid": (
            len(unique_error_codes) == 0
        ),
        "error_codes": (
            unique_error_codes
        ),
        "error_details": (
            unique_error_details
        ),
    }


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_quality_result(
    quality_result
):
    """
    Final classification:

    valid
    correctable
    quarantine
    """

    error_codes = quality_result.get(
        "error_codes",
        []
    )

    if not error_codes:

        return "valid"

    base_codes = []

    for error in error_codes:

        base_code = error.split(
            ":"
        )[0]

        base_codes.append(
            base_code
        )

    # Any unsafe error wins.

    for error in base_codes:

        if error in QUARANTINE_ERRORS:

            return "quarantine"

    # Every remaining error must be known
    # and safely correctable.

    for error in base_codes:

        if error not in CORRECTABLE_ERRORS:

            return "quarantine"

    return "correctable"


# ============================================================
# FULL QUALITY CHECK
# ============================================================

def run_quality_check(
    record,
    parsed_items
):
    """
    Run validation and classification.
    """

    quality_result = validate_data_quality(
        record,
        parsed_items,
    )

    classification = (
        classify_quality_result(
            quality_result
        )
    )

    return {
        **quality_result,
        "classification": classification,
    }