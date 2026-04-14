import json
import os
from jsonschema import validate, ValidationError

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "schemas")

def load_schema(schema_name: str) -> dict:
    schema_path = os.path.join(SCHEMA_DIR, f"{schema_name}.json")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, "r") as f:
        return json.load(f)

ASSET_SCHEMA = load_schema("asset")
SYSTEM_SCHEMA = load_schema("system")

def validate_telemetry(payload: dict, schema_type: str = "asset"):
    """
    Validates the given payload against the appropriate schema.
    Raises ValueError if validation fails.
    """
    try:
        if schema_type == "asset":
            validate(instance=payload, schema=ASSET_SCHEMA)
        elif schema_type == "system":
            validate(instance=payload, schema=SYSTEM_SCHEMA)
        else:
            raise ValueError(f"Unknown schema type: {schema_type}")
    except ValidationError as e:
        raise ValueError(f"Schema validation failed: {e.message}")
