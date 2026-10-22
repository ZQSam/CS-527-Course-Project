"""Message Batches transport: queue uncached requests, submit them at the batch discount, ingest into the cache.

A batch run is a sequence of rounds over all bugs. Each round runs the normal pipeline with a
BatchCollector in place of the provider: cached requests are answered from the cache, uncached ones
are queued. The queue is submitted as one batch, results are written to the same cache and ledger, and
the next round continues (e.g. validation retries). The round that queues nothing produces the results.
Submitted batches are recorded in a manifest so an interrupted run ingests them instead of paying twice.
"""

import datetime
import json
from pathlib import Path
import time

from rerank.cache import _atomic_write
from rerank.llm import ProviderError, call_cost, request_params, response_record


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BatchCollector:
    """Stands in for a provider during batch rounds; the runner queues requests instead of calling it."""

    collects_batch = True

    def __init__(self, name: str, model: str, effort: str, max_tokens: int):
        self.name = name
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.pending = {}      # cache key -> {"request": ..., "meta": ...}
        self.failures = {}     # cache key -> {"kind": ..., "message": ...} for errored/expired/canceled items
        self.fresh_keys = set()  # keys whose results were paid for during this run

    def queue(self, key: str, request: dict, meta: dict) -> None:
        self.pending.setdefault(key, {"request": request, "meta": meta})

    def failure(self, key: str):
        return self.failures.get(key)

    def complete(self, system: str, messages: list, schema: dict, cache_key: str = None) -> dict:
        failure = self.failures.get(cache_key)
        if failure is None:
            raise RuntimeError("BatchCollector only answers for failed batch items; queue the rest")
        raise ProviderError(failure["message"], failure["kind"])


class AnthropicBatchBackend:
    def __init__(self, timeout: float = 300.0):
        import anthropic  # deferred so offline tests need no SDK
        self.client = anthropic.Anthropic(timeout=timeout, max_retries=3)

    def submit(self, requests: list) -> str:
        return self.client.messages.batches.create(requests=requests).id

    def status(self, batch_id: str) -> str:
        return self.client.messages.batches.retrieve(batch_id).processing_status

    def results(self, batch_id: str):
        """Yield (custom_id, outcome, payload): payload is a response record or an error description."""
        for item in self.client.messages.batches.results(batch_id):
            result = item.result
            if result.type == "succeeded":
                yield item.custom_id, "succeeded", response_record(result.message, None)
            elif result.type == "errored":
                error = result.error.error
                yield item.custom_id, "errored", {"type": error.type, "message": error.message}
            else:
                yield item.custom_id, result.type, {"type": result.type, "message": f"batch item {result.type}"}


class FakeBatchBackend:
    """Offline backend: answers every request immediately with a FakeProvider; the first `fail` items error."""

    def __init__(self, provider, fail: int = 0, fail_type: str = "overloaded_error"):
        self.provider = provider
        self.fail = fail
        self.fail_type = fail_type
        self.batches = {}

    def submit(self, requests: list) -> str:
        batch_id = f"msgbatch_fake_{len(self.batches) + 1}"
        outcomes = []
        for request in requests:
            if self.fail > 0:
                self.fail -= 1
                outcomes.append((request["custom_id"], "errored", {"type": self.fail_type, "message": "fake error"}))
                continue
            params = request["params"]
            response = self.provider.complete(params["system"], params["messages"],
                                              params["output_config"]["format"]["schema"])
            outcomes.append((request["custom_id"], "succeeded", {**response, "latency_s": None}))
        self.batches[batch_id] = outcomes
        return batch_id

    def status(self, batch_id: str) -> str:
        return "ended"

    def results(self, batch_id: str):
        yield from self.batches[batch_id]


def _failure_kind(outcome: str, payload: dict) -> str:
    if outcome == "errored":
        return "batch_invalid_request" if payload.get("type") == "invalid_request_error" else "batch_errored"
    return f"batch_{outcome}"


class BatchRunner:
    def __init__(self, collector: BatchCollector, backend, cache, ledger, price: dict, settings: dict,
                 manifest_dir: Path, max_rounds: int, sleep=time.sleep, log=print):
        self.collector = collector
        self.backend = backend
        self.cache = cache
        self.ledger = ledger
        self.price = price
        self.multiplier = settings["price_multiplier"]
        self.poll_interval_s = settings["poll_interval_s"]
        self.max_wait_s = settings["max_wait_s"]
        self.manifest_dir = manifest_dir
        self.max_rounds = max_rounds
        self.sleep = sleep
        self.log = log
        self.batch_ids = []

    def run(self, bugs: list, run_one) -> list:
        """run_one(entry, bug) -> output; returns the outputs of the first round that queues nothing."""
        self.ingest_outstanding()
        for round_index in range(self.max_rounds):
            self.collector.pending.clear()
            outputs = [run_one(entry, bug) for entry, bug in bugs]
            if not self.collector.pending:
                return outputs
            pending = self.collector.pending
            worst_case = sum(item["meta"]["worst_case_usd"] for item in pending.values()) * self.multiplier
            self.ledger.check(worst_case)
            requests = [{"custom_id": key, "params": request_params(
                item["request"]["model"], item["request"]["effort"], item["request"]["max_tokens"],
                item["request"]["system"], item["request"]["messages"], item["request"]["schema"])}
                for key, item in pending.items()]
            batch_id = self.backend.submit(requests)
            self.batch_ids.append(batch_id)
            self._write_manifest(batch_id, {"batch_id": batch_id, "status": "submitted", "created_at": utc_now(),
                                            "provider": self.collector.name, "model": self.collector.model,
                                            "round": round_index, "requests": {key: {**item["meta"],
                                                                                     "request": item["request"]}
                                                                               for key, item in pending.items()}})
            self.log(f"batch round {round_index}: submitted {batch_id} with {len(requests)} requests "
                     f"(worst case ${worst_case:.4f})")
            self.wait_and_ingest(batch_id)
        raise RuntimeError(f"Batch run did not settle within {self.max_rounds} rounds")

    def ingest_outstanding(self) -> None:
        """Finish batches a previous, interrupted run submitted (same provider and model only)."""
        if not self.manifest_dir.is_dir():
            return
        for path in sorted(self.manifest_dir.glob("*.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest["status"] == "submitted" and manifest["provider"] == self.collector.name \
                    and manifest["model"] == self.collector.model:
                self.log(f"resuming outstanding batch {manifest['batch_id']}")
                self.wait_and_ingest(manifest["batch_id"])

    def wait_and_ingest(self, batch_id: str) -> None:
        waited = 0.0
        while self.backend.status(batch_id) != "ended":
            if waited >= self.max_wait_s:
                raise RuntimeError(f"Batch {batch_id} still running after {waited:.0f}s; rerun to resume it")
            self.sleep(self.poll_interval_s)
            waited += self.poll_interval_s
        manifest = self._read_manifest(batch_id)
        counts = {}
        for key, outcome, payload in self.backend.results(batch_id):
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome != "succeeded":
                self.collector.failures[key] = {"kind": _failure_kind(outcome, payload),
                                                "message": f"{outcome}: {payload.get('message')}"}
                continue
            if self.cache.get(key) is not None:
                continue  # already ingested (e.g. a crash between ingest and manifest update)
            meta = manifest["requests"][key]
            cost = round(call_cost(payload["usage"], self.price) * self.multiplier, 8)
            self.cache.put(key, {"cache_key": key, "created_at": utc_now(), "request": meta["request"],
                                 "response": payload, "cost_usd": cost, "batch_id": batch_id,
                                 "price_multiplier": self.multiplier})
            if self.collector.name == "anthropic":
                self.ledger.record({"at": utc_now(), "cache_key": key, "model": self.collector.model,
                                    "bug_id": meta["bug_id"], "sample_index": meta["sample_index"],
                                    "attempt": meta["attempt"], "cost_usd": cost, "batch_id": batch_id})
            self.collector.fresh_keys.add(key)
        manifest.update(status="ingested", ingested_at=utc_now(), result_counts=counts)
        self._write_manifest(batch_id, manifest)
        self.log(f"batch {batch_id} ingested: {counts}")

    def _manifest_path(self, batch_id: str) -> Path:
        return self.manifest_dir / f"{batch_id}.json"

    def _read_manifest(self, batch_id: str) -> dict:
        return json.loads(self._manifest_path(batch_id).read_text(encoding="utf-8"))

    def _write_manifest(self, batch_id: str, manifest: dict) -> None:
        _atomic_write(self._manifest_path(batch_id), json.dumps(manifest, indent=1, ensure_ascii=False))
