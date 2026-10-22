"""Offline fusion of LLM and SBFL ranks over the full candidate list."""


def sbfl_tie_ranks(candidates: list) -> dict:
    """Tie-aware SBFL rank inside the candidate list: equal Ochiai scores share their average position.

    rank_max can exceed the candidate list (e.g. a 2400-way zero tie); positions are clipped to the list.
    """
    ranks = {}
    by_group = {}
    for position, candidate in enumerate(candidates, start=1):
        by_group.setdefault(candidate["rank_min"], []).append((position, candidate["method_id"]))
    for members in by_group.values():
        average = sum(position for position, _ in members) / len(members)
        for _, method_id in members:
            ranks[method_id] = average
    return ranks


def fuse(llm_ranking: list, candidates: list, weight: float, method: str = "weighted_rank", rrf_k: int = 60) -> dict:
    """weight=1 is pure LLM order, weight=0 is pure SBFL; ties break by SBFL display rank then ID."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError("Fusion weight must be within [0, 1]")
    sbfl = sbfl_tie_ranks(candidates)
    display = {candidate["method_id"]: candidate["sbfl_rank"] for candidate in candidates}
    llm = {method_id: index for index, method_id in enumerate(llm_ranking, start=1)}
    if set(llm) != set(sbfl):
        raise ValueError("LLM ranking must cover exactly the candidate list")
    if method == "weighted_rank":
        scores = {m: weight * llm[m] + (1 - weight) * sbfl[m] for m in sbfl}
        ranking = sorted(scores, key=lambda m: (scores[m], display[m], m))
    elif method == "rrf":
        scores = {m: weight / (rrf_k + llm[m]) + (1 - weight) / (rrf_k + sbfl[m]) for m in sbfl}
        ranking = sorted(scores, key=lambda m: (-scores[m], display[m], m))
    else:
        raise ValueError(f"Unknown fusion method: {method}")
    return {"weight": weight, "method": method, "ranking": ranking,
            "scores": {m: round(scores[m], 6) for m in ranking}}


def weight_key(weight: float) -> str:
    return f"{weight:.2f}"
