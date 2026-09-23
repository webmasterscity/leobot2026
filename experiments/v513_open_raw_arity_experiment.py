"""V5.13 frozen experiment: raw opaque relation induction up to the core Atom arity.

This experiment changes no learner code.  It checks that evidence requirements grow with
arity and that a learned high-arity surface transfers to unseen referents.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter

from leobot import Bot
from leobot.core import Atom

ROOT = Path(__file__).resolve().parents[1]


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "leobot").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def eight_role(i: str) -> str:
    return f"p{i} relaciona q{i} via r{i} hacia s{i} con t{i} desde u{i} sobre v{i} para w{i}"


def run() -> dict:
    before = code_hash()

    bot = Bot(allow_extensional_grounding=False)
    train_reports = [bot.respond(eight_role(str(i))) for i in range(8)]
    learned = train_reports[-1]
    assert all(r.get("status") != "raw_relation_learned" for r in train_reports[:7]), train_reports
    assert learned.get("status") == "raw_relation_learned", learned
    assert learned.get("arity") == 8 and learned.get("support") == 8, learned
    pred = learned["predicate"]

    correct = 0
    latencies = []
    for i in range(100):
        vals = tuple(f"x{i:03d}{j}" for j in range(8))
        text = (
            f"{vals[0]} relaciona {vals[1]} via {vals[2]} hacia {vals[3]} "
            f"con {vals[4]} desde {vals[5]} sobre {vals[6]} para {vals[7]}"
        )
        t0 = perf_counter()
        stored = bot.respond(text)
        latencies.append((perf_counter() - t0) * 1000)
        supported = bot.answer_atom(Atom(pred, vals))
        if stored.get("status") == "stored" and supported.get("status") == "supported":
            correct += 1

    seven = Bot(allow_extensional_grounding=False)
    seven_reports = [seven.respond(eight_role(f"c{i}")) for i in range(7)]

    historical = Bot(allow_extensional_grounding=False)
    old_rows = [
        "ana mueve caja de casa a oficina",
        "bea mueve libro de plaza a tienda",
        "cora mueve mapa de cuarto a taller",
    ]
    old_reports = [historical.respond(x) for x in old_rows]

    noise = Bot(allow_extensional_grounding=False)
    for i in range(80):
        # Each surface has unique lexical anchors, so no repeated anti-unification family
        # should acquire enough independent support.
        noise.respond(f"a{i} verbo{i} b{i} enlace{i} c{i} puente{i} d{i}")

    after = code_hash()
    result = {
        "version": "0.5.13",
        "eight_role_training": {
            "statuses": [r.get("status") for r in train_reports],
            "learned_surface": learned.get("surface"),
            "arity": learned.get("arity"),
            "support": learned.get("support"),
        },
        "eight_role_heldout": {
            "correct": correct,
            "total": 100,
            "p50_store_ms": statistics.median(latencies),
            "p95_store_ms": sorted(latencies)[int(0.95 * (len(latencies) - 1))],
        },
        "seven_support_control": {
            "promotions": len(seven.raw_relation_promotions),
            "facts": seven.kb.stats()["facts"],
            "last_status": seven_reports[-1].get("status"),
        },
        "historical_four_role_three_support_control": {
            "promotions": len(historical.raw_relation_promotions),
            "facts": historical.kb.stats()["facts"],
            "statuses": [r.get("status") for r in old_reports],
        },
        "noise_control": {
            "promotions": len(noise.raw_relation_promotions),
            "facts": noise.kb.stats()["facts"],
        },
        "code_hash_before": before,
        "code_hash_after": after,
        "code_unchanged": before == after,
        "claim_boundary": (
            "Raw opaque surface induction scales through the existing 8-argument Atom limit "
            "with evidence proportional to arity; this is not open-ended language understanding or AGI."
        ),
    }

    assert correct == 100, result
    assert result["seven_support_control"]["promotions"] == 0, result
    assert result["seven_support_control"]["facts"] == 0, result
    assert result["historical_four_role_three_support_control"]["promotions"] == 0, result
    assert result["historical_four_role_three_support_control"]["facts"] == 0, result
    assert result["noise_control"] == {"promotions": 0, "facts": 0}, result
    assert before == after, result
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
