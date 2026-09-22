"""Copy the grading evidence of selected Harbor jobs into results/ for the repo.

    python tools/collect_results.py <job dir> [<job dir> ...]

jobs/ is git-ignored (agent transcripts are large). This keeps, per trial,
only what shows the verdict: result.json, the verifier's reward, per-test
CTRF report and the hidden-batch tool log, plus any exception. Every copied
file is scanned for credentials first; the script refuses to copy on a hit.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

KEEP = ["result.json", "exception.txt", "verifier/reward.txt", "verifier/ctrf.json",
        "verifier/batch_b_tool.log"]
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|\"(access|refresh|id)_token\"")


def main() -> int:
    out_root = Path("results")
    for job in map(Path, sys.argv[1:]):
        dest_job = out_root / job.name
        if (job / "result.json").exists():
            dest_job.mkdir(parents=True, exist_ok=True)
            shutil.copy(job / "result.json", dest_job / "job_result.json")
        for trial in sorted(p for p in job.iterdir() if p.is_dir()):
            for rel in KEEP:
                src = trial / rel
                if not src.exists():
                    continue
                text = src.read_text(encoding="utf-8", errors="replace")
                if SECRET.search(text):
                    print(f"REFUSED (credential pattern): {src}")
                    return 1
                dst = dest_job / trial.name / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
        print(f"{job.name}: collected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
