"""Documents waiting to be taken in: the renegotiated agreement for Caldera Foods, as text.

The labour demo leads with the renegotiation. The current agreement is on the register as rows; the new one arrives as a
document, the way the promotions system's next export arrives as a file, and waits under data/generated/documents/ until
People and culture take it in: the first pass reads it and proposes its entitlements as rows under the kinds, each with
its clause quoted, for a person to accept or alter. Synthetic, as the agreements are: written as an agreement would word
it, with one clause that fits no kind (paid parental leave), and clauses that grant nothing (definitions, consultation).
Draws nothing.
"""
from __future__ import annotations

from pathlib import Path

from .costs import CLASSIFICATIONS

NAME = "CFPA-2027.txt"
INSTRUMENT, INSTRUMENT_NAME, ENTITY = "CFPA-2027", "Caldera Food Processing Agreement 2027", "CF"
COMMENCES = "2027-07-01"
NEW_RATES = {"PO1": 36.00, "PO2": 38.60, "PO3": 42.25, "TT": 49.55, "ST": 35.45, "LT": 44.35, "LOG": 45.90}


def renegotiated_agreement() -> str:
    names = {c: n for c, n, _ in CLASSIFICATIONS}
    schedule = "\n".join(f"  {i}. {names[c]}: ${r:.2f} per ordinary hour." for i, (c, r) in enumerate(NEW_RATES.items(), start=1))
    return f"""CALDERA FOOD PROCESSING AGREEMENT 2027

Part 1 — Application and operation

1.1 Title. This agreement is the Caldera Food Processing Agreement 2027.

1.2 Parties. This agreement covers Caldera Foods Pty Ltd and its employees at the Echuca site engaged in the
classifications in Schedule A.

1.3 Commencement. This agreement commences on 1 July 2027 and replaces the Caldera Food Processing Agreement 2025.

2. Definitions. In this agreement, ordinary hours means the hours worked within the span of hours in clause 8, and a
shift worker is an employee rostered on afternoon or night shift.

Part 2 — Consultation

5. Consultation. The employer will consult with affected employees and their representatives before introducing a major
change to production, organisation or structure.

Part 3 — Hours and rates

8. Ordinary hours. Ordinary hours are 38 per week, worked between 6.00 am and 6.00 pm Monday to Friday.

9. Rates of pay. Employees are paid the ordinary hourly rate for their classification in Schedule A.

10.3 Casual employees. A casual employee is paid the ordinary hourly rate for their classification plus a casual loading
of 25%.

11.1 Afternoon shift. An employee working an afternoon shift is paid a loading of 15% of the ordinary hourly rate for
each hour of that shift.

11.2 Night shift. An employee working a night shift is paid a loading of 30% of the ordinary hourly rate for each hour of
that shift.

12.2 Wage increase. Rates in Schedule A increase by 3.0% from the first full pay period commencing on or after 1 July 2028.

Part 4 — Allowances and payments

14.1 Meal allowance. An employee required to work more than two hours of overtime after their ordinary hours is paid a
meal allowance of $18.50.

15. Sign-on payment. Each employee covered by this agreement on the day it is approved is paid a one-off payment of $750.

Part 5 — Leave

20. Paid parental leave. An employee with twelve months' continuous service who is the primary carer of a newborn or
newly adopted child is entitled to 14 weeks' paid parental leave at the ordinary hourly rate.

Schedule A — Rates of pay from 1 July 2027
{schedule}
"""


# the register the agreement door writes its proposals to: nothing is proposed until a document is taken in, so the
# generated master is its header alone — the contract the landing reads
PROPOSAL_COLUMNS = ["proposal_id", "document", "instrument", "instrument_name", "entity_code", "instrument_kind", "placed", "kind",
                    "classification", "classification_name", "applies_to", "value", "from_date", "valid_from_period", "clause_ref", "clause",
                    "confidence", "rationale", "refused_because", "taken_in_by", "taken_in_at"]


def write(out: Path) -> Path:
    p = out / "documents" / NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(renegotiated_agreement(), encoding="utf-8")
    (out / "plan" / "reg_entitlement_proposal.csv").write_text(",".join(PROPOSAL_COLUMNS) + "\n", encoding="utf-8")
    return p
