"""Validate real MockMvc response captures against the frozen baseline v1 schemas.

Uses jsonschema Draft202012Validator; no network resolver or HTTP fixture server.
"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
frozen = json.loads((root / "backend/src/test/resources/vt029-v1-contract.json").read_text())
schema = {"$ref": "#/components/schemas/DocumentPage", "components": frozen["components"]}
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
for name in ("legacy", "search"):
    path = root / f"backend/target/vt029-contract/{name}.json"
    validator.validate(json.loads(path.read_text()))
    print(f"PASS {name}: actual response validates against baseline {frozen['baseline_commit']}")
