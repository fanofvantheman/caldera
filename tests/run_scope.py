"""What a run takes in, read from the landing (DEC-20261119-06) — no run; anything placed is removed again.

    uv run python -m tests.run_scope        # from build/, with the warehouse built

1. The map: every register the face writes names the models that read it, and the map is exactly the models' own
   references to `bronze.<register>`.
2. With nothing waiting, a run is the evaluation alone; a file placed in one register makes that register waiting and
   the run loads it alone and restates the models that read it; two registers waiting is the union; a file the table
   holds and the landing no longer has is waiting too; the file is listed as placed and not taken in.
3. Everything only when everything changed: no warehouse, or generated inputs newer than it.
4. The pages carry no run list of their own, and the app's run reads the landing.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUILD))
if os.environ.get("FACE_ROOT"):
    sys.path.insert(0, os.environ["FACE_ROOT"])

import chassis                                        # noqa: E402
from chassis.warehouse import q                       # noqa: E402

chassis.configure(root=BUILD, db="data/caldera.duckdb", receipts="data/receipts", landing="data/landing")

from ingest import pipeline as P                      # noqa: E402
from ingest import scope as S                         # noqa: E402
from face import __main__ as M                        # noqa: E402


def main() -> None:
    # 1 · the map
    refs: dict[str, set[str]] = {}
    for f in list((BUILD / "models").rglob("*.sql")) + list((BUILD / "models").rglob("*.py")):
        text = f.read_text()
        name = re.search(r"MODEL\s*\(\s*name\s+([a-z_]+\.[a-z_]+)", text) or re.search(r'name="([a-z_]+\.[a-z_]+)"', text)
        for reg in set(re.findall(r"bronze\.([a-z_]+)", text)):
            if name:
                refs.setdefault(reg, set()).add(name.group(1))
    written = set(P.PLAN) | {"price_list"}
    assert set(P.READ_BY) == written, set(P.READ_BY) ^ written
    assert all(set(P.READ_BY[r]) == refs.get(r, set()) for r in P.READ_BY), {r: (P.READ_BY[r], refs.get(r)) for r in P.READ_BY if set(P.READ_BY[r]) != refs.get(r, set())}
    print(f"map             {len(P.READ_BY)} registers the face writes, each with the models that read it — the models' own references, exactly")

    # 2 · what is waiting
    holds = S.held(lambda sql: q(sql))
    assert S.waiting(BUILD, holds) == [] and S.commands(BUILD, holds) == [S.EVALUATE], S.waiting(BUILD, holds)
    folder = BUILD / "data" / "landing" / "plan" / "reg_purchase_act"
    folder2 = BUILD / "data" / "landing" / "plan" / "reg_assumption_amend"
    made = []
    try:
        for fold, row in ((folder, "act_id,action\nPUR-SCOPE-TEST,set\n"), (folder2, "amend_id,version_id\nAA-SCOPE-TEST,F202705\n")):
            fold.mkdir(parents=True, exist_ok=True)
            f = fold / "29991231T000000-scope-test.csv"
            f.write_text(row)
            made.append(f)
            if len(made) == 1:
                assert S.waiting(BUILD, holds) == ["reg_purchase_act"]
                cmds = S.commands(BUILD, holds)
                assert cmds[0][-2:] == ["--only", "reg_purchase_act"] and "plan.purchase_act+" in cmds[1] and cmds[1].count("--restate-model") == 3, cmds
                assert S.waiting(BUILD, holds, files=True) == [f]
        cmds = S.commands(BUILD, holds)
        assert sorted(S.waiting(BUILD, holds)) == ["reg_assumption_amend", "reg_purchase_act"]
        assert set(cmds[0][cmds[0].index("--only") + 1:]) == {"reg_purchase_act", "reg_assumption_amend"}
        assert {cmds[1][i + 1] for i, x in enumerate(cmds[1]) if x == "--restate-model"} == {"plan.purchase_act+", "plan.purchase_published+", "plan.purchase_published_version+", "plan.assumption_in_force+", "dims.reg_assumption+", "plan.change_record+"}
        print("waiting         nothing → the evaluation alone; a purchase act placed → its register loaded alone and its three readers restated; "
              "an amendment beside it → the union of the two")
    finally:
        for f in made:
            f.unlink()
    gone = {**holds, "reg_capex": holds.get("reg_capex", set()) | {"29991231T000000-removed.csv"}}
    assert S.waiting(BUILD, gone) == ["reg_capex"], "a file the table holds and the landing has lost is waiting"
    assert S.waiting(BUILD, holds) == []
    print("removed         a file the table holds and the landing no longer has makes its register waiting")

    # 3 · everything
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "data").mkdir()
        assert S.commands(tmp) is S.EVERYTHING, "no warehouse"
        (tmp / "data" / "caldera.duckdb").write_text("")
        (tmp / "data" / "generated").mkdir()
        os.utime(tmp / "data" / "caldera.duckdb", (1, 1))
        (tmp / "data" / "generated" / "x.csv").write_text("a\n1\n")
        assert S.regenerated(tmp, tmp / "data" / "caldera.duckdb")
    finally:
        shutil.rmtree(tmp)
    print("everything      only with no warehouse, or generated inputs newer than it")

    # 4 · no page carries its own list
    for f in (BUILD / "face").glob("*.py"):
        text = f.read_text()
        assert not re.search(r'"--only"', text) and '"commands"' not in text, f.name
    assert M.run_commands() == [S.EVALUATE]
    print("pages           no page names the registers or models its run reaches; the app's run reads the landing")


if __name__ == "__main__":
    main()
