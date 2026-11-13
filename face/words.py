"""What a permission is called where a person reads it: receipts, refusals and hints say what the right lets someone do,
never its code. The codes stay the keys of the role register; this is how they are said."""
from __future__ import annotations

SAID = {
    "overlay.finance.enter": "the right to type Finance's figures",
    "schedule.line.enter": "the right to type a cost centre's months on the opex schedule",
    "register.cost_input.maintain": "the right to set a schedule line's driver and rate",
    "register.terms.maintain": "the right to amend the terms register",
    "register.price_list.maintain": "the right to change the price lists",
    "register.promo_calendar.maintain": "the right to keep the promotions calendar",
    "register.assumptions.maintain": "the right to change the assumptions",
    "mapping.accept": "the right to accept a proposed mapping",
    "mapping.alter": "the right to alter a mapping",
    "run.plan": "the right to run the plan",
    "read.pay": "the right to read individual pay",
    "version.name": "the right to name a version",
    "version.freeze": "the right to close and reopen a version",
    "version.declare_reference": "the right to declare a version's reference",
    "forecast.take_in": "the right to take in a forecasting run",
    "submission.submit": "the right to submit a unit's plan",
}


def said(verb: str | None) -> str:
    """The right a permission code gives, in words."""
    if not verb:
        return "no right"
    if verb in SAID:
        return SAID[verb]
    bits = verb.split(".")
    if bits[0] == "layer" and len(bits) == 3:
        return f"the right to {bits[2]} on layer {bits[1]}"
    if bits[0] == "register" and len(bits) == 3:
        return f"the right to {bits[2]} the {bits[1].replace('_', ' ')} register"
    if len(bits) >= 2:
        return f"the right to {bits[-1].replace('_', ' ')} {' '.join(b.replace('_', ' ') for b in bits[:-1])}"
    return f"the right to {verb.replace('_', ' ')}"
