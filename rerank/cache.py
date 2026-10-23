"""Content-addressed disk cache for model calls and an append-only spend ledger."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


def request_key(request: dict) -> str:
    canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        handle.write(text)
        temporary = handle.name
    os.replace(temporary, path)


class ResponseCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str):
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: str, record: dict) -> None:
        _atomic_write(self._path(key), json.dumps(record, indent=1, ensure_ascii=False))


class SpendLedger:
    """Cumulative paid spend across runs; cache hits are free and never recorded here."""

    def __init__(self, path: Path, cap_usd: float):
        self.path = path
        self.cap_usd = cap_usd

    def total(self) -> float:
        if not self.path.is_file():
            return 0.0
        return sum(json.loads(line)["cost_usd"] for line in self.path.read_text(encoding="utf-8").splitlines() if line)

    def check(self, estimated_usd: float) -> None:
        spent = self.total()
        if spent + estimated_usd > self.cap_usd:
            raise BudgetExceeded(f"Spend cap ${self.cap_usd:.2f} would be exceeded "
                                 f"(spent ${spent:.4f}, next call up to ${estimated_usd:.4f})")

    def record(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


class BudgetExceeded(RuntimeError):
    pass
