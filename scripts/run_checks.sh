#!/usr/bin/env bash
# Run the upstream TB3 static checks against this task, exactly as CI does.
# Clones/updates a shallow copy of the terminal-bench repo into .tb3/ (gitignored).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TB="$ROOT/.tb3"
if [ ! -d "$TB/.git" ]; then
  git clone --depth 1 https://github.com/harbor-framework/terminal-bench "$TB"
else
  git -C "$TB" pull --ff-only
fi
echo "terminal-bench @ $(git -C "$TB" rev-parse --short HEAD)"
# Upstream checks word-split their arguments, so an absolute path containing a
# space (e.g. "Klavis AI") silently expands into two bogus task dirs and the
# check passes vacuously. Run from the repo root and pass a relative path.
cd "$ROOT"
FAIL=0
for check in "$TB"/scripts/checks/check-*.sh; do
  name=$(basename "$check")
  if bash "$check" tasks/freight-bill-audit >/tmp/chk.log 2>&1; then
    echo "PASS $name"
  else
    echo "FAIL $name"; sed 's/^/    /' /tmp/chk.log; FAIL=1
  fi
done
exit $FAIL
