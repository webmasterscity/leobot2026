"""V8.8 Non-isomorphic transfer: move-world prior vs stack-world learning cost.

Move: at(agent,loc) changes location.
Stack: clear/on facts — structurally different predicates and arity patterns.

Hypothesis: move prior reduces episodes to operator_learned on stack.
Refutation: same episode count as control (analogy does not cross non-isomorphic domains).
"""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def teach_move(bot: Bot) -> list[str]:
    statuses = []
    locs = ["casa", "parque", "escuela"]
    pairs = [(locs[i], locs[(i + 1) % 3]) for i in range(3)] * 2
    for a, b in pairs:
        r = bot.observe_symbolic_transition(
            f"robot va de {a} a {b}",
            [("at", "robot", a)],
            [("at", "robot", b)],
        )
        statuses.append(r.get("status"))
    return statuses


def teach_stack(bot: Bot) -> list[str]:
    """Stack block X on Y: requires clear(X), clear(Y); results on(X,Y), not clear(Y)."""
    statuses = []
    # Multiple episodes with different blocks — same linguistic pattern
    episodes = [
        ("pon caja sobre mesa",
         [("clear", "caja"), ("clear", "mesa")],
         [("on", "caja", "mesa"), ("clear", "caja")]),  # mesa no longer clear
        ("pon libro sobre silla",
         [("clear", "libro"), ("clear", "silla")],
         [("on", "libro", "silla"), ("clear", "libro")]),
        ("pon vaso sobre caja",
         [("clear", "vaso"), ("clear", "caja")],
         [("on", "vaso", "caja"), ("clear", "vaso")]),
        ("pon plato sobre libro",
         [("clear", "plato"), ("clear", "libro")],
         [("on", "plato", "libro"), ("clear", "plato")]),
        ("pon taza sobre plato",
         [("clear", "taza"), ("clear", "plato")],
         [("on", "taza", "plato"), ("clear", "taza")]),
        ("pon lápiz sobre vaso",
         [("clear", "lapiz"), ("clear", "vaso")],
         [("on", "lapiz", "vaso"), ("clear", "lapiz")]),
    ]
    for text, before, after in episodes:
        r = bot.observe_symbolic_transition(text, before, after)
        statuses.append(r.get("status"))
    return statuses


def ep_until(statuses: list[str], target: str = "operator_learned") -> int | None:
    for i, s in enumerate(statuses, 1):
        if s == target:
            return i
    return None


def run():
    treatment = Bot()
    control = Bot()

    move_stat = teach_move(treatment)
    # control: no move prior

    t_stack = teach_stack(treatment)
    c_stack = teach_stack(control)

    t_ep = ep_until(t_stack)
    c_ep = ep_until(c_stack)

    reduction = (
        t_ep is not None and c_ep is not None and t_ep < c_ep
    )
    both_learn = t_ep is not None and c_ep is not None

    out = {
        "version": "V8.8-nonisomorphic-transfer",
        "hypothesis": "move prior reduces stack operator episodes",
        "move_prior_learned_at": ep_until(move_stat),
        "treatment_stack_episodes": t_ep,
        "control_stack_episodes": c_ep,
        "treatment_stack_statuses": t_stack,
        "control_stack_statuses": c_stack,
        "episode_reduction": reduction,
        "both_learn": both_learn,
        # Completion is separate from support for the transfer hypothesis.
        "measurement_completed": both_learn,
        "hypothesis_supported": reduction,
        "pass": both_learn,
        "cost_transfer_nonisomorphic": reduction,
        "interpretation": (
            "analogy transfers across non-isomorphic domains"
            if reduction else
            "no episode reduction: analogy limited to isomorphic/similar effect structure"
        ),
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v88_nonisomorphic_transfer.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"]
    print("MEASUREMENT COMPLETE: non-isomorphic transfer " +
          ("observed" if reduction else "not observed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
