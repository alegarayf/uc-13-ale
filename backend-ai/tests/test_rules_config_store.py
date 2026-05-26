import json
from pathlib import Path

import pytest

from app.services.rules_config_store import (
    delete_rule_config,
    read_rule_config,
    update_rule_config,
    write_rule_config,
)


def test_update_rule_config_preserves_id(tmp_path: Path):
    filename, path = write_rule_config(
        tmp_path,
        rule_config={"name": "Original"},
        prompt="original prompt",
        summary="original summary",
        session_id="sess-1",
    )
    data = json.loads(path.read_text())
    original_id = data["id"]

    update_rule_config(
        tmp_path,
        filename,
        rule_config={"name": "Updated"},
        prompt="new prompt",
        summary="new summary",
        session_id="sess-2",
    )

    updated = read_rule_config(tmp_path, filename)
    assert updated["id"] == original_id
    assert updated["prompt"] == "new prompt"
    assert updated["summary"] == "new summary"
    assert updated["rule"]["name"] == "Updated"
    assert updated["updatedAt"] is not None


def test_read_rejects_invalid_filename(tmp_path: Path):
    with pytest.raises(ValueError):
        read_rule_config(tmp_path, "../secrets.json")


def test_delete_rule_config(tmp_path: Path):
    filename, path = write_rule_config(
        tmp_path,
        rule_config={"name": "To delete"},
        prompt="p",
        summary="s",
        session_id="sess",
    )
    assert path.is_file()
    delete_rule_config(tmp_path, filename)
    assert not path.is_file()
