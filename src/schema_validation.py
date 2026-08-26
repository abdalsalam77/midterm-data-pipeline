import json


# ============================================================
# EXPECTED TOP-LEVEL FIELDS
# ============================================================

REQUIRED_FIELDS = [
    "order_id",
    "order_date",
    "status",
    "customer_id",
    "customer_name",
    "customer_phone",
    "customer_email",
    "city",
    "district",
    "delivery_type",
    "delivery_cost",
    "payment_method",
    "payment_status",
    "payment_amount",
    "currency",
    "total_amount",
    "items_json",
]


# ============================================================
# REQUIRED ITEM FIELDS
# ============================================================

REQUIRED_ITEM_FIELDS = [
    "sku",
    "name",
    "qty",
    "unit_price",
    "total",
]


# ============================================================
# MISSING VALUE HELPER
# ============================================================

def is_missing(value):
    """
    Return True when a value is None or an empty string.

    This helper is used only where an actual value-presence
    check is needed. Top-level empty values are handled by
    the Quality Validation stage, not Schema Validation.
    """

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


# ============================================================
# TOP-LEVEL STRUCTURE VALIDATION
# ============================================================

def validate_required_fields(record):
    """
    Validate that all expected top-level fields exist.

    Important:
    Schema Validation checks field existence only.

    Examples:
        Missing column:
            -> Schema Error

        Existing field with empty value:
            -> Quality Validation

    This allows records such as:
        order_id = ""

    to reach the Quality Classification stage and be classified
    correctly as quarantine or correctable when appropriate.
    """

    errors = []

    for field in REQUIRED_FIELDS:

        if field not in record:

            errors.append({
                "code": "MISSING_FIELD",
                "field": field,
                "message": (
                    f"Missing required field: {field}"
                ),
            })

    return errors


# ============================================================
# ITEMS JSON STRUCTURE VALIDATION
# ============================================================

def validate_items_json(record):
    """
    Validate the structural integrity of items_json.

    Schema Validation checks:

    - items_json field exists
    - JSON can be parsed
    - parsed value is a list
    - every item is a dictionary
    - required item fields exist

    The following belong to Quality Validation:

    - empty items list
    - empty item values
    - invalid qty
    - negative qty
    - invalid unit_price
    - negative unit_price
    - invalid totals
    """

    errors = []

    # --------------------------------------------------------
    # FIELD MUST EXIST
    # --------------------------------------------------------

    if "items_json" not in record:

        errors.append({
            "code": "MISSING_FIELD",
            "field": "items_json",
            "message": (
                "Missing required field: items_json"
            ),
        })

        return errors, None

    items_json = record.get("items_json")

    # --------------------------------------------------------
    # EMPTY VALUE
    #
    # Let Quality Validation handle this as a data quality issue.
    # --------------------------------------------------------

    if is_missing(items_json):

        return errors, None

    # --------------------------------------------------------
    # JSON PARSING
    # --------------------------------------------------------

    try:

        items = json.loads(
            items_json
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):

        errors.append({
            "code": "CORRUPTED_ITEMS_JSON",
            "field": "items_json",
            "message": (
                "items_json cannot be parsed "
                "as valid JSON"
            ),
        })

        return errors, None

    # --------------------------------------------------------
    # MUST BE A JSON ARRAY
    # --------------------------------------------------------

    if not isinstance(items, list):

        errors.append({
            "code": "INVALID_ITEMS_STRUCTURE",
            "field": "items_json",
            "message": (
                "items_json must contain "
                "a JSON array"
            ),
        })

        return errors, None

    # --------------------------------------------------------
    # EMPTY LIST
    #
    # EMPTY_ITEMS belongs to Quality Validation.
    # --------------------------------------------------------

    if len(items) == 0:

        return errors, items

    # --------------------------------------------------------
    # ITEM STRUCTURE
    # --------------------------------------------------------

    for index, item in enumerate(items):

        if not isinstance(item, dict):

            errors.append({
                "code": "INVALID_ITEM_STRUCTURE",
                "field": f"items[{index}]",
                "message": (
                    "Each item must be "
                    "a JSON object"
                ),
            })

            continue

        # ----------------------------------------------------
        # REQUIRED ITEM FIELDS MUST EXIST
        #
        # Empty values are handled later by Quality Validation.
        # ----------------------------------------------------

        for field in REQUIRED_ITEM_FIELDS:

            if field not in item:

                errors.append({
                    "code": "MISSING_ITEM_FIELD",
                    "field": (
                        f"items[{index}].{field}"
                    ),
                    "message": (
                        f"Missing required item field: "
                        f"{field}"
                    ),
                })

    return errors, items


# ============================================================
# MAIN SCHEMA VALIDATION
# ============================================================

def validate_schema(record):
    """
    Validate record structure before Data Quality Validation.

    Schema Validation is responsible for:

    1. Record must be a dictionary.
    2. All required top-level fields must exist.
    3. items_json must be structurally valid JSON.
    4. items_json must contain a JSON array.
    5. Every item must be a dictionary.
    6. Required fields inside each item must exist.

    Schema Validation does NOT decide whether values are:

    - empty
    - invalid dates
    - invalid emails
    - invalid phones
    - invalid numeric values
    - negative values
    - EMPTY_ITEMS

    Those decisions belong to Quality Validation and
    Classification.
    """

    # ========================================================
    # RECORD STRUCTURE
    # ========================================================

    if not isinstance(record, dict):

        return {
            "schema_valid": False,
            "schema_errors": [
                {
                    "code": (
                        "INVALID_RECORD_STRUCTURE"
                    ),
                    "field": None,
                    "message": (
                        "Record must be a dictionary"
                    ),
                }
            ],
            "parsed_items": None,
        }

    schema_errors = []

    # ========================================================
    # TOP-LEVEL FIELD EXISTENCE
    # ========================================================

    required_field_errors = (
        validate_required_fields(
            record
        )
    )

    schema_errors.extend(
        required_field_errors
    )

    # ========================================================
    # ITEMS JSON STRUCTURE
    # ========================================================

    items_errors, parsed_items = (
        validate_items_json(
            record
        )
    )

    schema_errors.extend(
        items_errors
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {
        "schema_valid": (
            len(schema_errors) == 0
        ),
        "schema_errors": schema_errors,
        "parsed_items": parsed_items,
    }