"""Dry-run evaluator scaffold for AI Tutor behavior cases.

This script intentionally does not judge model responses yet. It validates a
portable JSONL case format and prints a summary that can become the input for a
future LLM-judge or rubric-based evaluator.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_CASE_FIELDS = {"id", "category", "prompt_profile", "messages", "expectations"}
REQUIRED_EXPECTATION_FIELDS = {"required_behaviors", "forbidden_behaviors"}


def _require_text(value: Any, field_name: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Case {case_id} must provide a non-empty string for '{field_name}'")
    return value.strip()


def _require_string_list(value: Any, field_name: str, case_id: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Case {case_id} must provide a non-empty list for '{field_name}'")
    items = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"Case {case_id} has an invalid '{field_name}' item")
        items.append(item.strip())
    return items


def validate_case(raw_case: dict[str, Any], line_number: int) -> dict[str, Any]:
    missing = REQUIRED_CASE_FIELDS - set(raw_case)
    if missing:
        raise ValueError(f"Line {line_number} is missing required fields: {', '.join(sorted(missing))}")

    case_id = _require_text(raw_case["id"], "id", f"line-{line_number}")
    category = _require_text(raw_case["category"], "category", case_id)
    prompt_profile = _require_text(raw_case["prompt_profile"], "prompt_profile", case_id)

    messages = raw_case["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"Case {case_id} must provide at least one message")
    normalized_messages = []
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            raise ValueError(f"Case {case_id} message {index} must be an object")
        role = _require_text(message.get("role"), "role", case_id)
        content = _require_text(message.get("content"), "content", case_id)
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Case {case_id} message {index} has unsupported role '{role}'")
        normalized_messages.append({"role": role, "content": content})

    expectations = raw_case["expectations"]
    if not isinstance(expectations, dict):
        raise ValueError(f"Case {case_id} expectations must be an object")
    missing_expectations = REQUIRED_EXPECTATION_FIELDS - set(expectations)
    if missing_expectations:
        raise ValueError(f"Case {case_id} expectations missing fields: {', '.join(sorted(missing_expectations))}")

    normalized = dict(raw_case)
    normalized["id"] = case_id
    normalized["category"] = category
    normalized["prompt_profile"] = prompt_profile
    normalized["messages"] = normalized_messages
    normalized["expectations"] = {
        **expectations,
        "required_behaviors": _require_string_list(
            expectations["required_behaviors"],
            "required_behaviors",
            case_id,
        ),
        "forbidden_behaviors": _require_string_list(
            expectations["forbidden_behaviors"],
            "forbidden_behaviors",
            case_id,
        ),
    }
    return normalized


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            raw_case = json.loads(line)
            if not isinstance(raw_case, dict):
                raise ValueError(f"Line {line_number} must be a JSON object")
            cases.append(validate_case(raw_case, line_number))
    if not cases:
        raise ValueError(f"No eval cases found in {path}")
    return cases


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter(case["category"] for case in cases)
    prompt_profiles = Counter(case["prompt_profile"] for case in cases)
    return {
        "total_cases": len(cases),
        "categories": dict(sorted(categories.items())),
        "prompt_profiles": dict(sorted(prompt_profiles.items())),
        "mode": "dry_run_schema_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and summarize AI Tutor behavior eval cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/tutor_cases.jsonl"),
        help="Path to the Tutor behavior JSONL case file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a short text summary.",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    summary = summarize_cases(cases)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"Loaded {summary['total_cases']} Tutor behavior eval cases from {args.cases}")
    print("Categories:")
    for category, count in summary["categories"].items():
        print(f"- {category}: {count}")
    print("Mode: dry-run schema validation only; no LLM judge is executed yet.")


if __name__ == "__main__":
    main()
