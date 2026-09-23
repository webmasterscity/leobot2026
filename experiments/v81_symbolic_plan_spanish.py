"""V8.1 Symbolic operators from Spanish + procedure retention."""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def run():
    bot = Bot()
    log = []

    # Factual states: robot at loc, move mentions entities
    # before: at(robot, a)  after: at(robot, b)  text mentions robot, a, b
    examples = [
        ("robot va de casa a parque",
         [("at", "robot", "casa")],
         [("at", "robot", "parque")]),
        ("robot va de parque a escuela",
         [("at", "robot", "parque")],
         [("at", "robot", "escuela")]),
        ("robot va de escuela a casa",
         [("at", "robot", "escuela")],
         [("at", "robot", "casa")]),
    ]
    for text, before, after in examples:
        r = bot.observe_symbolic_transition(text, before, after)
        log.append(("sym", r.get("status"), r.get("pattern")))

    # Numeric procedure same session
    for t, b, a in [
        ("suma uno a 2", (2,), (3,)),
        ("suma uno a 5", (5,), (6,)),
        ("suma uno a 8", (8,), (9,)),
    ]:
        r = bot.observe_transition(t, b, a)
        log.append(("proc", r.get("status")))

    plan = bot.plan_symbolic(
        [("at", "robot", "casa")],
        [("at", "robot", "escuela")],
        max_steps=6,
    )
    proc = bot.respond("suma uno a 12")
    ex = bot.execute_symbolic_transition(
        "robot va de casa a parque",
        [("at", "robot", "casa")],
    )

    sym_learned = any(s[1] == "operator_learned" for s in log if s[0] == "sym")
    proc_ok = proc.get("status") == "procedure_executed" and "13" in str(proc)
    plan_ok = plan.get("status") in ("plan_found", "planned", "solved", "ok") or bool(
        plan.get("steps") or plan.get("path")
    )

    out = {
        "version": "V8.1-symbolic-plan-spanish",
        "log": [(x[0], x[1]) for x in log],
        "sym_learned": sym_learned,
        "plan_status": plan.get("status"),
        "plan_steps": plan.get("steps") or plan.get("path"),
        "sym_exec": ex.get("status"),
        "proc_ok": proc_ok,
        "pass": sym_learned and proc_ok,
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v81_symbolic_plan.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"]
    print("PASS: V8.1 symbolic operators + procedure")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
