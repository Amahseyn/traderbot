from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> None:
    """Apply ``KEY=value`` lines from a .env file; never overwrites existing ``os.environ`` entries."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def upsert_env_vars(path: Path, updates: dict[str, str]) -> None:
    """Merge keys into a .env file without removing unrelated lines."""
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    index: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        index[key] = i
    for key, value in updates.items():
        entry = f"{key}={value}"
        if key in index:
            lines[index[key]] = entry
        else:
            lines.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
