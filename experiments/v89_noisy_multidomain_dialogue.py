"""V8.9 Noisy multi-domain dialogue: paraphrase, topic switch, retention rates."""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def run():
    bot = Bot()
    turns = []

    def log(label, r):
        st = r.get("status") if isinstance(r, dict) else str(r)
        tx = str((r.get("text") if isinstance(r, dict) else r) or "")[:100]
        turns.append({"label": label, "status": st, "text": tx})
        return r

    # --- Relations (raw) with slight surface variation ---
    for u in [
        "Ana conoce a Luis",
        "María conoce a Pedro",
        "Carlos conoce a Sofía",
        "Elena conoce a Diego",
    ]:
        log("raw", bot.observe_raw_relation(u))

    # --- Procedures ---
    for t, b, a in [
        ("suma uno a 2", (2,), (3,)),
        ("suma uno a 5", (5,), (6,)),
        ("suma uno a 9", (9,), (10,)),
    ]:
        log("proc_teach", bot.observe_transition(t, b, a))

    # --- Symbolic ops + goals ---
    for text, before, after in [
        ("robot va de casa a parque",
         [("at", "robot", "casa")], [("at", "robot", "parque")]),
        ("robot va de parque a escuela",
         [("at", "robot", "parque")], [("at", "robot", "escuela")]),
        ("robot va de escuela a casa",
         [("at", "robot", "escuela")], [("at", "robot", "casa")]),
        ("robot va de casa a escuela",
         [("at", "robot", "casa")], [("at", "robot", "escuela")]),
    ]:
        log("sym", bot.observe_symbolic_transition(text, before, after))
    for text, goal in [
        ("quiero que robot esté en escuela", [("at", "robot", "escuela")]),
        ("quiero que robot esté en parque", [("at", "robot", "parque")]),
    ]:
        log("goal", bot.observe_symbolic_goal(text, goal))
    bot.last_symbolic_state = [("at", "robot", "casa")]

    # --- Mixed queries (including mild noise / paraphrase) ---
    queries = [
        ("q_rel", "¿Ana conoce a Luis?"),
        ("q_rel_unknown", "¿Ana conoce a Pedro?"),
        ("q_proc", "suma uno a 40"),
        ("q_plan", "quiero que robot esté en escuela"),
        ("q_plan_cue", "cómo llego a parque"),
        ("q_noise", "hola qué tal el clima hoy"),  # unsupported
        ("q_rel2", "¿María conoce a Pedro?"),
        ("q_proc2", "suma uno a 0"),
    ]
    for label, text in queries:
        log(label, bot.respond(text))

    # Correction + recovery
    log("correct", bot.correct_transition("suma uno a 40", (40,), (99,)))
    log("q_proc_down", bot.respond("suma uno a 40"))
    for t, b, a in [
        ("suma uno a 1", (1,), (2,)),
        ("suma uno a 3", (3,), (4,)),
        ("suma uno a 6", (6,), (7,)),
    ]:
        log("reteach", bot.observe_transition(t, b, a))
    log("q_proc_up", bot.respond("suma uno a 41"))
    log("q_proc_corrected", bot.respond("suma uno a 40"))
    log("q_rel_after", bot.respond("¿Ana conoce a Luis?"))
    log("q_plan_after", bot.respond("quiero que robot esté en parque"))

    query_turns = [t for t in turns if t["label"].startswith("q_")]
    good = {"supported", "procedure_executed", "symbolic_plan"}
    n_good = sum(1 for t in query_turns if t["status"] in good)
    n_q = len(query_turns)

    out = {
        "version": "V8.9-noisy-multidomain-dialogue",
        "n_query_turns": n_q,
        "n_useful_answers": n_good,
        "useful_rate": n_good / n_q if n_q else 0,
        "legacy_same_input_recovery": any(t["label"] == "q_proc_corrected" and t["status"] == "procedure_executed" for t in turns),
        "turns": turns,
        "checks": {
            "rel_ok": any(t["label"] == "q_rel" and t["status"] == "supported" for t in turns),
            "proc_ok": any(t["label"] == "q_proc" and t["status"] == "procedure_executed" for t in turns),
            "plan_ok": any(t["label"] == "q_plan" and t["status"] == "symbolic_plan" for t in turns),
            "noise_not_hallucinated": any(
                t["label"] == "q_noise" and t["status"] not in ("supported", "procedure_executed", "symbolic_plan")
                for t in turns),
            "correct_demotes": any(t["label"] == "correct" and t["status"] == "procedure_demoted" for t in turns),
            "proc_recovers": any(t["label"] == "q_proc_up" and t["status"] == "procedure_executed" for t in turns),
            "corrected_input_remains_contested": any(t["label"] == "q_proc_corrected" and t["status"] == "procedure_corrected_conflict" for t in turns),
            "rel_after_ok": any(t["label"] == "q_rel_after" and t["status"] == "supported" for t in turns),
            "plan_after_ok": any(t["label"] == "q_plan_after" and t["status"] == "symbolic_plan" for t in turns),
        },
    }
    out["pass"] = all(out["checks"].values()) and out["useful_rate"] >= 0.5
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v89_noisy_multidomain_dialogue.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "turns"}, indent=2, ensure_ascii=False))
    print("turns_sample", json.dumps(turns[-8:], indent=2, ensure_ascii=False))
    assert out["pass"]
    print("PASS: V8.9 noisy multi-domain dialogue")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
