"""Run the tests in parallel, each worker on its own copy of the build.  python partest.py [-j N] [tests…]

The tests share one landing and one warehouse file, so two cannot run at once in the build itself. Here each worker
gets a copy of the build — the source as it stands (or as committed, --source head) and the data — and runs its tests
there, one after another, exactly as the suite runs them in place. Nothing in the build's own data is touched, so
this is also safe to run while the app or another run is using the build.

    python partest.py                      every test, four workers
    python partest.py -j 6 cost_pools actual_cost
    python partest.py --source head        the committed source, not the working tree
    python partest.py --keep               leave the copies and the outputs in place afterwards

The copies share the build's own environment (.venv); completed load packages under data/.dlt are not copied.
Exit status is 0 when every test passed.
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

BUILD = Path(__file__).resolve().parent
SKIP_DIRS = {".venv", "__pycache__", ".cache", "logs", ".sqlmesh", ".git"}
WAREHOUSE = BUILD / "data" / "caldera.duckdb"


def _ignore(directory: str, names: list[str]) -> set[str]:
    skip = {n for n in names if n in SKIP_DIRS}
    if Path(directory).name == "load" and ".dlt" in Path(directory).parts:
        skip.add("loaded")                              # completed load packages: large, never read again
    return skip


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["UV_PROJECT_ENVIRONMENT"] = str(BUILD / ".venv")  # every copy runs in the build's own environment …
    env["UV_NO_SYNC"] = "1"                               # … as it is: a copy must never re-install into it
    return env


def _wait_quiet(limit: int) -> None:
    """Wait until nothing is writing the warehouse, so the copy is of a whole file."""
    probe = "import duckdb,sys; duckdb.connect(sys.argv[1], read_only=True).close()"
    start = time.time()
    while True:
        r = subprocess.run(["uv", "run", "python", "-c", probe, str(WAREHOUSE)], cwd=BUILD, env=_env(), capture_output=True, text=True)
        if r.returncode == 0:
            return
        if time.time() - start > limit:
            sys.exit(f"the warehouse was still being written after {limit}s — try again when the run has finished\n{r.stderr[-300:]}")
        time.sleep(10)


def _copy(dest: Path, source: str) -> None:
    if source == "tree":
        shutil.copytree(BUILD, dest, ignore=_ignore, symlinks=True)
        return
    dest.mkdir(parents=True)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=BUILD, capture_output=True, text=True, check=True).stdout.strip()
    rel = BUILD.relative_to(top).as_posix()
    arch = subprocess.Popen(["git", "archive", f"HEAD:{rel}"], cwd=top, stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest)], stdin=arch.stdout, check=True)
    if arch.wait() != 0:
        sys.exit("git archive failed")
    shutil.copytree(BUILD / "data", dest / "data", ignore=_ignore, symlinks=True)   # the data is not in git


def _repoint(dest: Path, was: Path) -> None:
    """The ingest keeps its own record of where the warehouse is, as a full path: point the copy's at the copy, or a
    load in the copy would write to the build's warehouse."""
    for f in (dest / "data" / ".dlt").rglob("*.json"):
        if "loaded" in f.parts or f.stat().st_size > 5_000_000:
            continue
        text = f.read_text(errors="ignore")
        if str(was) in text:
            f.write_text(text.replace(str(was), str(dest)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tests", nargs="*", help="test names (tests/<name>.py); every test when none is given")
    ap.add_argument("-j", "--workers", type=int, default=4)
    ap.add_argument("--source", choices=("tree", "head"), default="tree", help="the working tree (default) or the committed source")
    ap.add_argument("--timeout", type=int, default=900, help="seconds a single test may take")
    ap.add_argument("--wait", type=int, default=600, help="seconds to wait for the warehouse to be quiet before copying")
    ap.add_argument("--keep", action="store_true", help="keep the copies and outputs")
    a = ap.parse_args()

    names = a.tests or sorted(p.stem for p in (BUILD / "tests").glob("*.py") if not p.stem.startswith("_"))
    missing = [n for n in names if not (BUILD / "tests" / f"{n}.py").exists()]
    if missing:
        sys.exit(f"no such test: {', '.join(missing)}")
    workers = max(1, min(a.workers, len(names)))
    base = Path(tempfile.mkdtemp(prefix="caldera-tests-"))
    out = base / "out"
    out.mkdir()

    t0 = time.time()
    _wait_quiet(a.wait)
    first = base / "w0"
    _copy(first, a.source)
    _repoint(first, BUILD)
    for i in range(1, workers):                         # the others from the first, which nothing is writing
        shutil.copytree(first, base / f"w{i}", symlinks=True)
        _repoint(base / f"w{i}", first)
    stray = subprocess.run(["grep", "-rl", "--include=*.json", "--exclude-dir=loaded", str(BUILD) + "/data", str(base)], capture_output=True, text=True).stdout.strip()
    if stray:
        sys.exit(f"a copy still names the build's own data — not running:\n{stray}")
    print(f"{workers} copies of the build ({a.source}) in {base} — {time.time() - t0:.0f}s", flush=True)

    todo: queue.Queue[str] = queue.Queue()
    for n in names:
        todo.put(n)
    results: dict[str, tuple[int, float]] = {}
    lock = threading.Lock()

    def work(i: int) -> None:
        root = base / f"w{i}"
        while True:
            try:
                n = todo.get_nowait()
            except queue.Empty:
                return
            s = time.time()
            try:
                r = subprocess.run(["uv", "run", "python", "-m", f"tests.{n}"], cwd=root, env=_env(), capture_output=True, text=True, timeout=a.timeout)
                rc, text = r.returncode, r.stdout + r.stderr
            except subprocess.TimeoutExpired as e:
                rc, text = 124, (e.stdout or b"").decode(errors="replace") + f"\ntimed out after {a.timeout}s"
            (out / f"{n}.txt").write_text(text)
            with lock:
                results[n] = (rc, time.time() - s)
                print(f"{'ok  ' if rc == 0 else 'FAIL'} {n}  {time.time() - s:.0f}s  (w{i}, {len(results)}/{len(names)})", flush=True)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    failed = sorted(n for n, (rc, _) in results.items() if rc != 0)
    print(f"\n{len(names) - len(failed)} of {len(names)} passed in {time.time() - t0:.0f}s"
          f" (the tests' own time: {sum(d for _, d in results.values()):.0f}s)")
    for n in failed:
        tail = (out / f"{n}.txt").read_text().strip().splitlines()[-6:]
        print(f"\n--- {n} (rc={results[n][0]})\n" + "\n".join(tail))
    if a.keep or failed:
        print(f"\noutputs kept in {out}" + ("" if a.keep else " (the copies are removed)"))
    if not a.keep:
        for i in range(workers):
            shutil.rmtree(base / f"w{i}", ignore_errors=True)
        if not failed:
            shutil.rmtree(base, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
