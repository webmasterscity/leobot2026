"""V7.8 Bootstrap relational knowledge from Spanish without pre-seeded KB.

Teach opaque relations via independent utterances → promote → query via respond/language.
Also keep a procedure family to show multi-domain retention.
"""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot
from leobot.core import Atom


def run():
    bot = Bot()  # empty KB
    log = []

    # Bootstrap relation "conoce" style with varying entities
    utterances = [
        "Ana conoce a Luis",
        "María conoce a Pedro",
        "Carlos conoce a Sofía",
        "Elena conoce a Diego",
    ]
    for t in utterances:
        r = bot.observe_raw_relation(t)
        log.append(("raw", t, r.get("status"), r.get("predicate") or r.get("surface")))

    # Procedure family in same session
    for t, b, a in [
        ("suma uno a 2", (2,), (3,)),
        ("suma uno a 4", (4,), (5,)),
        ("suma uno a 6", (6,), (7,)),
    ]:
        r = bot.observe_transition(t, b, a)
        log.append(("proc", t, r.get("status")))

    # Check promotions
    promotions = dict(bot.raw_relation_promotions)
    # Query via atom if we know predicate
    queries = []
    if promotions:
        pred = list(promotions.values())[0].get("predicate")
        arity = list(promotions.values())[0].get("arity", 2)
        if pred and arity >= 2:
            a1 = Atom(pred, ("ana", "luis"))
            q1 = bot.answer_atom(a1)
            queries.append(("ana-luis", q1.get("status"), q1.get("text", "")[:80]))
            a2 = Atom(pred, ("ana", "pedro"))
            q2 = bot.answer_atom(a2)
            queries.append(("ana-pedro", q2.get("status"), q2.get("text", "")[:80]))
    # Conversational query
    q_resp = bot.respond("¿Ana conoce a Luis?")
    queries.append(("respond", q_resp.get("status"), str(q_resp.get("text", ""))[:80]))

    use_proc = bot.respond("suma uno a 10")

    promoted = len(promotions) >= 1
    proc_ok = use_proc.get("status") == "procedure_executed" and "11" in str(use_proc)
    fact_ok = any(q[1] in ("supported", "yes", "entailed", "known") for q in queries)
    # Softer: at least promotion happened and procedure works
    out = {
        "version": "V7.8-raw-bootstrap",
        "log": log,
        "promotions": {k: {"pred": v.get("predicate"), "arity": v.get("arity"), "support": v.get("support")}
                       for k, v in promotions.items()},
        "queries": queries,
        "procedure_use": use_proc.get("status"),
        "procedure_ok": proc_ok,
        "raw_promoted": promoted,
        "pass": promoted and proc_ok and fact_ok,
        "fact_ok": fact_ok,
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v78_raw_bootstrap.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"], "raw relation must promote and procedure must still execute"
    print("PASS: V7.8 raw bootstrap + procedure retention")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
