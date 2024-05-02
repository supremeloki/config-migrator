import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from config_migrator import (
    ChainBrokenError,
    MigrationRegistry,
    MigrationStep,
    RollbackUnsupportedError,
    UnknownVersionError,
    compose,
    load_config,
    nest_section,
    rename_key,
    save_config,
    set_default,
)


def build_registry(target: int = 3) -> MigrationRegistry:
    registry = MigrationRegistry(target_version=target)

    def unnest_section(prefix: str, keys: tuple[str, ...]) -> __import__("typing").Callable:
        def transform(config):
            updated = {k: v for k, v in config.items() if k != prefix}
            section = config.get(prefix, {})
            for key in keys:
                if key in section:
                    updated[key] = section[key]
            return updated
        return transform

    registry.register(MigrationStep(
        from_version=1, to_version=2,
        transform=rename_key("username", "user_name"),
        inverse=rename_key("user_name", "username"),
    ))
    registry.register(MigrationStep(
        from_version=2, to_version=3,
        transform=compose(
            set_default("timeout_seconds", 30),
            nest_section("database", ("db_host", "db_port")),
        ),
        inverse=unnest_section("database", ("db_host", "db_port")),
    ))
    return registry


def test_step_must_advance_single_version():
    with pytest.raises(MigrationError if False else __import__("config_migrator", fromlist=["MigrationError"]).MigrationError):
        MigrationStep(from_version=1, to_version=3, transform=lambda c: c)


def test_forward_migration_chains():
    old = {"schema_version": 1, "username": "koor"}
    result = build_registry().migrate(old, current_version=1)
    assert result.end_version == 3
    assert result.config["user_name"] == "koor"
    assert result.config["timeout_seconds"] == 30
    assert result.config["schema_version"] == 3
    assert result.steps_applied == 2


def test_nesting_moves_keys_into_section():
    config = {"db_host": "x", "db_port": 1433, "keep": True}
    result = build_registry().migrate(config, current_version=2)
    assert result.config["database"] == {"db_host": "x", "db_port": 1433}
    assert result.config["keep"] is True
    assert "db_host" not in result.config


def test_broken_chain_reports_gap():
    registry = MigrationRegistry(target_version=5)
    registry.register(MigrationStep(1, 2, lambda c: c))
    with pytest.raises(ChainBrokenError):
        registry.migrate({}, current_version=1)


def test_detect_version_rejects_missing_and_out_of_range():
    registry = build_registry()
    with pytest.raises(UnknownVersionError):
        registry.detect_version({})
    with pytest.raises(UnknownVersionError):
        registry.detect_version({"schema_version": 99})


def test_rollback_with_inverse():
    registry = build_registry()
    migrated = registry.migrate({"schema_version": 1, "username": "s"}, current_version=1)
    rolled_back = registry.rollback(migrated.config, from_version=3, to_version=1)
    assert rolled_back.config["schema_version"] == 1
    assert rolled_back.config["username"] == "s"
    assert "user_name" not in rolled_back.config


def test_rollback_without_inverse_raises():
    registry = MigrationRegistry(target_version=2)
    registry.register(MigrationStep(1, 2, lambda c: c))
    with pytest.raises(RollbackUnsupportedError):
        registry.rollback({"schema_version": 2}, from_version=2, to_version=1)
    with pytest.raises(RollbackUnsupportedError):
        registry.rollback({}, from_version=1, to_version=1)


def test_duplicate_registration_rejected():
    registry = MigrationRegistry(target_version=3)
    registry.register(MigrationStep(1, 2, lambda c: c))
    with pytest.raises(__import__("config_migrator", fromlist=["MigrationError"]).MigrationError):
        registry.register(MigrationStep(1, 2, lambda c: c))


def test_exceeding_target_rejected():
    with pytest.raises(__import__("config_migrator", fromlist=["MigrationError"]).MigrationError):
        registry = MigrationRegistry(target_version=2)
        registry.register(MigrationStep(2, 3, lambda c: c))


def test_file_roundtrip(tmp_path: Path):
    target = tmp_path / "nested" / "app.json"
    payload = {"schema_version": 1, "username": "a"}
    save_config(target, payload)
    loaded = load_config(target)
    assert loaded == payload


def test_already_current_is_noop():
    registry = build_registry()
    result = registry.migrate({"schema_version": 3}, current_version=3)
    assert result.steps_applied == 0


def test_json_dump_unicode_safe(tmp_path: Path):
    target = tmp_path / "fa.json"
    save_config(target, {"name": "کوروش"})
    assert "کوروش" in target.read_text(encoding="utf-8")
