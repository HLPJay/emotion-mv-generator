from __future__ import annotations

import json
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


_events_cache_by_run: dict[str, list[dict[str, Any]]] = {}


def _key(run_dir: Path) -> str:
    return str(run_dir.resolve())


def register_events_cache(run_dir: Path, cache: list[dict[str, Any]]) -> None:
    _events_cache_by_run[_key(run_dir)] = cache


def unregister_events_cache(run_dir: Path) -> None:
    _events_cache_by_run.pop(_key(run_dir), None)


def log_event(run_dir: Path, step: str, status: str, **extra) -> None:
    event = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "step": step,
        "status": status,
        **extra,
    }
    with (run_dir / "run_events.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
    cache = _events_cache_by_run.get(_key(run_dir))
    if cache is not None:
        cache.append(event)


@contextmanager
def track_step(run_dir: Path, step: str, **extra) -> Iterator[None]:
    started = time.perf_counter()
    log_event(run_dir, step, "started", **extra)
    try:
        yield
    except Exception as exc:
        elapsed = round(time.perf_counter() - started, 3)
        log_event(
            run_dir,
            step,
            "failed",
            duration_seconds=elapsed,
            error_type=exc.__class__.__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise
    elapsed = round(time.perf_counter() - started, 3)
    log_event(run_dir, step, "success", duration_seconds=elapsed)
