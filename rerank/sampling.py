"""Seeded candidate shuffling, mean-rank aggregation, and stability statistics."""

import hashlib
import math
import random


def sample_seed(base_seed: int, bug_id: str, sample_index: int) -> int:
    material = f"{base_seed}:{bug_id}:{sample_index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def display_order(method_ids: list, bug_id: str, sample_index: int, base_seed: int, mode: str = "shuffle") -> list:
    """Deterministic per-sample order; 'sbfl' keeps the saved Ochiai order (position-bias ablation)."""
    order = list(method_ids)
    if mode == "shuffle":
        random.Random(sample_seed(base_seed, bug_id, sample_index)).shuffle(order)
    elif mode != "sbfl":
        raise ValueError(f"Unknown order mode: {mode}")
    return order


def positions(ranking: list) -> dict:
    return {method_id: index for index, method_id in enumerate(ranking, start=1)}


def mean_rank(rankings: list, sbfl_order: list) -> dict:
    """Average 1-based ranks over complete rankings; ties break by SBFL order."""
    if not rankings:
        return {"ranking": list(sbfl_order), "mean": {}, "std": {}}
    tables = [positions(ranking) for ranking in rankings]
    means, stds = {}, {}
    for method_id in sbfl_order:
        values = [table[method_id] for table in tables]
        average = sum(values) / len(values)
        means[method_id] = average
        stds[method_id] = math.sqrt(sum((value - average) ** 2 for value in values) / len(values))
    sbfl_position = positions(sbfl_order)
    ranking = sorted(sbfl_order, key=lambda method_id: (means[method_id], sbfl_position[method_id]))
    return {"ranking": ranking, "mean": means, "std": stds}


def kendall_tau(first: list, second: list) -> float:
    """Kendall tau-a between two complete rankings over the same items."""
    a, b = positions(first), positions(second)
    items = list(a)
    if len(items) < 2:
        return 1.0
    concordant = discordant = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            sign = (a[items[i]] - a[items[j]]) * (b[items[i]] - b[items[j]])
            if sign > 0:
                concordant += 1
            elif sign < 0:
                discordant += 1
    pairs = len(items) * (len(items) - 1) / 2
    return (concordant - discordant) / pairs


def stability(rankings: list) -> dict:
    if len(rankings) < 2:
        return {"pairwise_kendall_tau_mean": None, "top1_agreement": None}
    taus = [kendall_tau(rankings[i], rankings[j]) for i in range(len(rankings)) for j in range(i + 1, len(rankings))]
    top1 = [ranking[0] for ranking in rankings]
    most_common = max(set(top1), key=top1.count)
    return {"pairwise_kendall_tau_mean": round(sum(taus) / len(taus), 4),
            "top1_agreement": round(top1.count(most_common) / len(top1), 4),
            "top1_mode": most_common}
