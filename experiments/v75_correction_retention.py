"""V7.5 Correction demotes only the conflicting family; other families retained."""
from __future__ import annotations
import json
from pathlib import Path
from leobot.bot import Bot


def run():
    bot = Bot()
    # Family A
    for t, b, a in [("suma uno a 2", (2,), (3,)), ("suma uno a 4", (4,), (5,)), ("suma uno a 6", (6,), (7,))]:
        bot.observe_transition(t, b, a)
    # Family B
    for t, b, a in [("duplica 2", (2,), (4,)), ("duplica 3", (3,), (6,)), ("duplica 5", (5,), (10,))]:
        bot.observe_transition(t, b, a)

    assert bot.respond("suma uno a 10").get("status") == "procedure_executed"
    assert bot.respond("duplica 7").get("status") == "procedure_executed"

    # Correct A only
    dem = bot.correct_transition("suma uno a 10", (10,), (99,))
    assert dem.get("status") == "procedure_demoted"

    # B must still work
    b_ok = bot.respond("duplica 8").get("status") == "procedure_executed"
    # A should not execute until retaught
    a_down = bot.respond("suma uno a 10").get("status") != "procedure_executed"

    # Reteach A
    for t, b, a in [("suma uno a 1", (1,), (2,)), ("suma uno a 3", (3,), (4,)), ("suma uno a 5", (5,), (6,))]:
        bot.observe_transition(t, b, a)
    # The learned family recovers on new inputs, while the explicitly corrected
    # input must not silently revert to the old rule.
    a_ok = bot.respond("suma uno a 8").get("status") == "procedure_executed"
    corrected = bot.respond("suma uno a 10")
    corrected_still_contested = corrected.get("status") == "procedure_corrected_conflict"
    b_still = bot.respond("duplica 9").get("status") == "procedure_executed"

    out = {
        "version": "V7.5 replay with retained counterevidence",
        "demote": dem.get("status"),
        "B_survives_demotion": b_ok,
        "A_down_after_demotion": a_down,
        "A_recovered_on_uncontested_input": a_ok,
        "corrected_input_remains_contested": corrected_still_contested,
        "legacy_same_input_recovery": corrected.get("status") == "procedure_executed",
        "B_still_after_relearn_A": b_still,
        "pass": b_ok and a_down and a_ok and corrected_still_contested and b_still,
    }
    Path("results_v3").mkdir(exist_ok=True)
    Path("results_v3/v75_correction_retention.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["pass"]
    print("PASS: V7.5 correction retention")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
