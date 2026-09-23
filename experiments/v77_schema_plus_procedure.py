"""V7.7 Schema (with KB facts) + procedure multi-turn; mutual retention."""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot
from leobot.core import Atom, KnowledgeBase


def run():
    kb = KnowledgeBase()
    for i in range(8):
        kb.add(Atom('posee', (f'persona{i}', f'objeto{i}')))
        kb.add(Atom('ubicado', (f'objeto{i}', f'lugar{i}')))
    bot = Bot(kb=kb)
    log = []

    # Procedure
    for t, b, a in [
        ("suma uno a 1", (1,), (2,)),
        ("suma uno a 3", (3,), (4,)),
        ("suma uno a 7", (7,), (8,)),
    ]:
        r = bot.observe_transition(t, b, a)
        log.append(("proc", r.get("status")))

    # Schema contrastive (requires KB atoms)
    examples = [
        "persona0 enlaza objeto0 con lugar0",
        "persona1 enlaza objeto1 con lugar1",
        "persona0 no enlaza objeto0 con lugar1",
        "persona0 no enlaza objeto1 con lugar0",
        "persona1 no enlaza objeto0 con lugar0",
    ]
    report = None
    for t in examples:
        report = bot.observe_schema_statement(t)
        log.append(("schema", report.get("status")))

    use_p = bot.respond("suma uno a 50")
    q_ok = bot.query_schema("persona6 enlaza objeto6 con lugar6")
    q_bad = bot.query_schema("persona6 enlaza objeto6 con lugar7")

    schema_learned = report and report.get("status") == "schema_learned"
    out = {
        "version": "V7.7-schema-plus-procedure",
        "log": log,
        "procedure_use": use_p.get("status"),
        "procedure_result_ok": "51" in str(use_p),
        "schema_final_status": report.get("status") if report else None,
        "schema_query_pos": q_ok.get("status"),
        "schema_query_neg": q_bad.get("status"),
        "schema_learned": schema_learned,
        "pass": use_p.get("status") == "procedure_executed" and "51" in str(use_p) and schema_learned,
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v77_schema_plus_procedure.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"]
    print("PASS: V7.7 schema + procedure co-exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
