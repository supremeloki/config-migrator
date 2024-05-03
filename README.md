# config-migrator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Versioned config migration with a registered step chain, composable transforms, optional rollback inverses, and automatic `schema_version` stamping — so old config files keep working after every schema change.

## 🚀 Overview

Every long-lived app accumulates config formats: v1 had `username`, v2 renamed it to `user_name`, v3 nested database keys under a section. `config-migrator` records each hop as a one-version `MigrationStep` (with an optional inverse for rollback), then walks any old file forward to the current version automatically — detecting its version from `schema_version` and refusing broken chains with the exact missing hop.

## ✨ Features

- **Single-hop enforcement:** steps must advance exactly one version — misconfigured chains fail at registration
- **Auto versioning:** migrated configs always carry the correct `schema_version`
- **Composable transforms:** `rename_key`, `set_default`, `nest_section`, and `compose(...)` building blocks
- **Optional rollback:** register `inverse` transforms; `rollback()` walks backward, raising `RollbackUnsupportedError` when an inverse is missing
- **Broken-chain diagnostics:** `ChainBrokenError` names the exact missing version
- **File helpers:** UTF-8 safe JSON load/save with parent-dir creation
- **Zero dependencies**

## 🚧 Structure

```
config-migrator/
├── src/config_migrator/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── README.md
└── pyproject.toml
```

## 📦 Installation

```bash
git clone https://github.com/supremeloki/config-migrator.git
cd config-migrator
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 🏃 Quick Start

```python
from pathlib import Path
from config_migrator import (
    MigrationRegistry, MigrationStep,
    rename_key, set_default, nest_section, compose,
    load_config, save_config,
)

registry = MigrationRegistry(target_version=3)

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
))

config = registry.bring_to_current(load_config(Path("old_app.json")))
save_config(Path("app.json"), config)
```

## 🔧 Error Handling

```text
MigrationError
├── UnknownVersionError        # schema_version missing or out of range
├── ChainBrokenError           # no step registered for a hop
└── RollbackUnsupportedError   # inverse transform absent or bad target
```

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📝 Code Quality

- Full type hints (`X | None` style), frozen steps/results
- Zero comments — names carry the meaning
- `ruff` clean

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👤 Author

**Kooroush Masoumi**

---

⭐ Star this repo if you find it useful!
