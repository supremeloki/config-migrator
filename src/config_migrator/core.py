from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

Transform = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationError(Exception):
    pass


class UnknownVersionError(MigrationError):
    def __init__(self, version: int, available: tuple[int, ...]) -> None:
        super().__init__(
            f"unknown config version {version}; known versions: {list(available)}"
        )
        self.version = version
        self.available = available


class ChainBrokenError(MigrationError):
    def __init__(self, from_version: int, to_version: int) -> None:
        super().__init__(f"no migration registered from v{from_version} to v{to_version}")


class RollbackUnsupportedError(MigrationError):
    pass


@dataclass(frozen=True)
class MigrationStep:
    from_version: int
    to_version: int
    transform: Transform
    inverse: Transform | None = None

    def __post_init__(self) -> None:
        if self.to_version != self.from_version + 1:
            raise MigrationError(
                f"steps must advance exactly one version (got {self.from_version}→{self.to_version})"
            )


@dataclass(frozen=True)
class MigrationResult:
    config: dict[str, Any]
    start_version: int
    end_version: int
    steps_applied: int


@dataclass
class MigrationRegistry:
    target_version: int
    _steps: dict[int, MigrationStep] = field(default_factory=dict)

    @property
    def known_versions(self) -> tuple[int, ...]:
        return tuple(sorted({0, *self._steps.keys(), self.target_version}))

    def register(self, step: MigrationStep) -> None:
        if step.to_version > self.target_version:
            raise MigrationError(f"step exceeds target version {self.target_version}")
        if step.from_version in self._steps:
            raise MigrationError(f"duplicate migration from v{step.from_version}")
        self._steps[step.from_version] = step

    def migrate(self, config: dict[str, Any], current_version: int) -> MigrationResult:
        working = dict(config)
        version = current_version
        applied = 0
        while version < self.target_version:
            step = self._steps.get(version)
            if step is None:
                raise ChainBrokenError(version, version + 1)
            working = step.transform(working)
            working.setdefault("schema_version", step.to_version)
            working["schema_version"] = step.to_version
            version = step.to_version
            applied += 1
        return MigrationResult(
            config=working, start_version=current_version,
            end_version=version, steps_applied=applied,
        )

    def rollback(self, config: dict[str, Any], from_version: int, to_version: int) -> MigrationResult:
        if to_version >= from_version:
            raise RollbackUnsupportedError("rollback target must be older")
        working = dict(config)
        version = from_version
        applied = 0
        while version > to_version:
            step = self._steps.get(version - 1)
            if step is None or step.inverse is None:
                raise RollbackUnsupportedError(
                    f"no inverse registered for v{version - 1}→v{version}"
                )
            working = step.inverse(working)
            working["schema_version"] = version - 1
            version -= 1
            applied += 1
        return MigrationResult(
            config=working, start_version=from_version,
            end_version=version, steps_applied=applied,
        )

    def detect_version(self, config: dict[str, Any]) -> int:
        raw = config.get("schema_version")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise UnknownVersionError(-1, self.known_versions)
        if not 0 <= raw <= self.target_version:
            raise UnknownVersionError(raw, self.known_versions)
        return raw

    def bring_to_current(self, config: dict[str, Any]) -> MigrationResult:
        detected = self.detect_version(config)
        return self.migrate(config, detected)


def rename_key(source: str, destination: str) -> Transform:
    def transform(config: dict[str, Any]) -> dict[str, Any]:
        updated = {k: v for k, v in config.items() if k != source}
        if source in config:
            updated[destination] = config[source]
        return updated

    return transform


def set_default(key: str, value: Any) -> Transform:
    def transform(config: dict[str, Any]) -> dict[str, Any]:
        updated = dict(config)
        updated.setdefault(key, value)
        return updated

    return transform


def nest_section(prefix: str, keys: tuple[str, ...]) -> Transform:
    def transform(config: dict[str, Any]) -> dict[str, Any]:
        updated = {k: v for k, v in config.items() if k not in keys}
        section = {k: config[k] for k in keys if k in config}
        if section:
            updated[prefix] = section
        return updated

    return transform


def compose(*transforms: Transform) -> Transform:
    def transform(config: dict[str, Any]) -> dict[str, Any]:
        result = config
        for single in transforms:
            result = single(result)
        return result

    return transform


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise MigrationError(f"config root must be an object: {path.name}")
    return document


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
