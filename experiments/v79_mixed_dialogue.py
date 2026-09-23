"""V7.9 Mixed multi-turn dialogue: raw relations + procedures + correction + topic switch."""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def run():
    bot = Bot()
    turns = []

    def t(label, fn):
        r = fn()
        turns.append({"label": label, "status": r.get("status") if isinstance(r, dict) else str(r),
                      "text": str((r.get("text") if isinstance(r, dict) else r) or "")[:100]})
        return r

    # Teach relation
    for u in ["Ana conoce a Luis", "María conoce a Pedro", "Carlos conoce a Sofía"]:
        t("raw_teach", lambda u=u: bot.observe_raw_relation(u))

    # Teach procedure
    for u, b, a in [("suma uno a 2", (2,), (3,)), ("suma uno a 5", (5,), (6,)), ("suma uno a 8", (8,), (9,))]:
        t("proc_teach", lambda u=u, b=b, a=a: bot.observe_transition(u, b, a))

    # Use both
    t("ask_rel", lambda: bot.respond("¿Ana conoce a Luis?"))
    t("ask_proc", lambda: bot.respond("suma uno a 14"))

    # Topic switch: second relation family
    for u in ["Roma está en Italia", "París está en Francia", "Madrid está en España"]:
        t("raw2", lambda u=u: bot.observe_raw_relation(u))

    # Correction on procedure
    t("correct", lambda: bot.correct_transition("suma uno a 14", (14,), (99,)))
    t("ask_proc_down", lambda: bot.respond("suma uno a 14"))

    # Reteach procedure
    for u, b, a in [("suma uno a 1", (1,), (2,)), ("suma uno a 3", (3,), (4,)), ("suma uno a 6", (6,), (7,))]:
        t("reteach", lambda u=u, b=b, a=a: bot.observe_transition(u, b, a))
    t("ask_proc_up", lambda: bot.respond("suma uno a 16"))
    t("ask_proc_corrected", lambda: bot.respond("suma uno a 14"))

    # Relation still works after correction/reteach
    t("ask_rel2", lambda: bot.respond("¿María conoce a Pedro?"))

    statuses = {x["label"]: x["status"] for x in turns}
    ok = (
        statuses.get("ask_rel") == "supported"
        and statuses.get("ask_proc") == "procedure_executed"
        and statuses.get("correct") == "procedure_demoted"
        and statuses.get("ask_proc_down") != "procedure_executed"
        and statuses.get("ask_proc_up") == "procedure_executed"
        and statuses.get("ask_proc_corrected") == "procedure_corrected_conflict"
        and statuses.get("ask_rel2") == "supported"
        and len(bot.raw_relation_promotions) >= 1
    )
    out = {"version": "V7.9-mixed-dialogue", "turns": turns, "promotions": len(bot.raw_relation_promotions),
           "legacy_same_input_recovery": statuses.get("ask_proc_corrected") == "procedure_executed",
           "corrected_input_remains_contested": statuses.get("ask_proc_corrected") == "procedure_corrected_conflict",
           "pass": ok}
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v79_mixed_dialogue.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert ok
    print("PASS: V7.9 mixed dialogue")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
