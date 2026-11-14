"""Flag snapshot company names that are also ordinary words (Junction, Bolt, Garage).

A LinkedIn contact at "Junction" is very likely not at the startup called Junction, so the app words those
matches as "same name, check". Writes app/common_names.txt: one company key per line, only keys that appear in the
snapshot, so the file stays small and the server needs no word list at runtime.

Run: python3 pipeline/common_names.py /path/to/snapshot.json [/usr/share/dict/words]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from merge import company_key  # noqa: E402


def main(snapshot_path: str, words_path: str = "/usr/share/dict/words") -> None:
    snap = json.loads(Path(snapshot_path).read_text())
    words = {w.strip().lower() for w in Path(words_path).read_text().splitlines() if w.strip()}
    keys = {r.get("ckey") or company_key(r["company"]) for r in snap["rounds"]}
    common = sorted(k for k in keys if len(k) >= 4 and k in words)
    out = ROOT / "app" / "common_names.txt"
    out.write_text("\n".join(common) + "\n")
    print(f"{len(common)} of {len(keys)} company keys are ordinary words -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
