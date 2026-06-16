from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from schema.models import InfrastructureSchema, TopologyValidationError


def load_and_validate(path: str | Path) -> InfrastructureSchema:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    try:
        return InfrastructureSchema.model_validate(raw)
    except TopologyValidationError:
        raise
    except ValidationError as exc:
        for item in exc.errors(include_url=False):
            nested = item.get("ctx", {}).get("error")
            if isinstance(nested, TopologyValidationError):
                raise nested from None
        errors = []
        for item in exc.errors(include_url=False):
            errors.append({
                "code": item["type"].upper(),
                "path": ".".join(str(part) for part in item["loc"]),
                "value": str(item.get("input", ""))[:200],
                "message": item["msg"],
            })
        raise TopologyValidationError(errors) from None


def to_legacy_topology(schema: InfrastructureSchema) -> dict[str, Any]:
    return schema.model_dump(mode="json")
