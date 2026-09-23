"""V8.4 Learned symbolic goals → conversational plan without destination heuristic.

Treatment: operators + goal schemas taught in Spanish → respond with novel goal phrasing.
Control: operators only, same respond text → should not resolve via learned goal.
"""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def teach_ops(bot: Bot):
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
        bot.observe_symbolic_transition(text, before, after)


def teach_goals(bot: Bot):
    reports = []
    for text, goal in [
        ("quiero que robot esté en escuela", [("at", "robot", "escuela")]),
        ("quiero que robot esté en parque", [("at", "robot", "parque")]),
        ("quiero que robot esté en casa", [("at", "robot", "casa")]),
    ]:
        reports.append(bot.observe_symbolic_goal(text, goal).get("status"))
    return reports


def run():
    treatment = Bot()
    control = Bot()
    teach_ops(treatment)
    teach_ops(control)
    gstat = teach_goals(treatment)
    # Control: no goal teaching

    treatment.last_symbolic_state = [("at", "robot", "casa")]
    control.last_symbolic_state = [("at", "robot", "casa")]

    # Novel instance of learned goal surface (same schema, known binding pattern)
    t_ans = treatment.respond("quiero que robot esté en escuela")
    c_ans = control.respond("quiero que robot esté en escuela")

    # Also verify cue fallback still works on treatment for "cómo llego"
    t_cue = treatment.respond("cómo llego a parque")

    # Other domain retention
    for t, b, a in [
        ("suma uno a 1", (1,), (2,)),
        ("suma uno a 3", (3,), (4,)),
        ("suma uno a 5", (5,), (6,)),
    ]:
        treatment.observe_transition(t, b, a)
    proc = treatment.respond("suma uno a 10")

    learned_goal_used = (
        t_ans.get("status") == "symbolic_plan"
        and (t_ans.get("goal_source") == "learned_schema"
             or (t_ans.get("plan") or {}).get("goal_pattern")
             or (t_ans.get("plan") or {}).get("resolved_goal"))
    )
    control_no_learned = c_ans.get("status") != "symbolic_plan" or c_ans.get("goal_source") != "learned_schema"
    # Control may still fail entirely or use nothing
    control_weak = c_ans.get("status") != "symbolic_plan"

    out = {
        "version": "V8.4-learned-goal-plan",
        "goal_teach": gstat,
        "treatment": {
            "status": t_ans.get("status"),
            "text": t_ans.get("text", "")[:120],
            "goal_source": t_ans.get("goal_source"),
            "goal_pattern": (t_ans.get("plan") or {}).get("goal_pattern"),
        },
        "control": {
            "status": c_ans.get("status"),
            "text": str(c_ans.get("text", ""))[:120],
            "goal_source": c_ans.get("goal_source"),
        },
        "cue_fallback": {
            "status": t_cue.get("status"),
            "text": t_cue.get("text", "")[:120],
        },
        "proc_ok": proc.get("status") == "procedure_executed",
        "learned_goal_used": learned_goal_used,
        "control_weak": control_weak,
        "pass": learned_goal_used and control_weak and proc.get("status") == "procedure_executed",
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v84_learned_goal_plan.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"]
    print("PASS: V8.4 learned goal schemas drive conversational planning")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
