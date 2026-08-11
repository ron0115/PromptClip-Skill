from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import to_jsonable


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(to_jsonable(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_file(run_dir: Path) -> Path:
    return run_dir / "run.json"


def save_run(run_dir: Path, run: dict[str, Any]) -> None:
    save_json(run_file(run_dir), run)


def load_run(run_dir: Path) -> dict[str, Any]:
    path = run_file(run_dir)
    if not path.exists():
        raise FileNotFoundError(f"Not a video highlight run: {run_dir}")
    return load_json(path)
