import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_rules_config_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_rule_config(
    directory: Path,
    *,
    rule_config: dict[str, Any],
    prompt: str,
    summary: str,
    session_id: str,
) -> tuple[str, Path]:
    ensure_rules_config_dir(directory)
    file_id = uuid.uuid4().hex
    filename = f"rule-{file_id}.json"
    filepath = directory / filename

    payload = {
        "id": file_id,
        "sessionId": session_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "summary": summary,
        "rule": rule_config,
    }
    filepath.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return filename, filepath


def _validate_config_filename(filename: str) -> None:
    if not filename.startswith("rule-") or not filename.endswith(".json") or "/" in filename or "\\" in filename:
        raise ValueError("Invalid config filename.")


def read_rule_config(directory: Path, filename: str) -> dict[str, Any]:
    _validate_config_filename(filename)
    filepath = directory / filename
    if not filepath.is_file():
        raise FileNotFoundError(filename)
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return {
        "filename": filename,
        "id": data.get("id"),
        "sessionId": data.get("sessionId"),
        "createdAt": data.get("createdAt"),
        "updatedAt": data.get("updatedAt"),
        "prompt": data.get("prompt", ""),
        "summary": data.get("summary", ""),
        "rule": data.get("rule") or {},
    }


def update_rule_config(
    directory: Path,
    filename: str,
    *,
    rule_config: dict[str, Any],
    prompt: str,
    summary: str,
    session_id: str,
) -> tuple[str, Path]:
    _validate_config_filename(filename)
    filepath = directory / filename
    if not filepath.is_file():
        raise FileNotFoundError(filename)

    data = json.loads(filepath.read_text(encoding="utf-8"))
    data["prompt"] = prompt
    data["summary"] = summary
    data["rule"] = rule_config
    data["sessionId"] = session_id
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    filepath.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return filename, filepath


def delete_rule_config(directory: Path, filename: str) -> None:
    _validate_config_filename(filename)
    filepath = directory / filename
    if not filepath.is_file():
        raise FileNotFoundError(filename)
    filepath.unlink()


def list_rule_configs(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("rule-*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        items.append(
            {
                "filename": path.name,
                "id": data.get("id"),
                "name": (data.get("rule") or {}).get("name"),
                "summary": data.get("summary"),
                "createdAt": data.get("createdAt"),
                "updatedAt": data.get("updatedAt"),
            }
        )
    return items
