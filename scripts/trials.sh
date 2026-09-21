#!/usr/bin/env bash
# Standard and adversarial trials, mirroring TB3's .github/harbor-run-defaults.yml
# (3 trials per agent; claude-code opus-5 reasoning_effort=max with a 128k output
# cap; codex gpt-5.6-sol reasoning_effort=xhigh) and run-cheat-trials.yml (the
# hack prompt is APPENDED to the instruction, one trial per agent).
#
#   scripts/trials.sh codex            # 3 standard codex trials
#   scripts/trials.sh claude           # 3 standard claude-code trials
#   CHEAT=1 scripts/trials.sh codex    # 1 adversarial codex trial
#   CHEAT=1 scripts/trials.sh claude   # 1 adversarial claude-code trial
#
# N_CONCURRENT (default 3) caps parallel trials; lower it for claude if the
# subscription rate-limits (a rate-limited trial is an infra failure, not a
# model failure, and must be rerun). Record every job dir in RESULTS.md.
set -euo pipefail
cd "$(dirname "$0")/.."

TASK=tasks/freight-bill-audit
ATTEMPTS=3
if [ "${CHEAT:-0}" = "1" ]; then
  [ -f .tb3/docs/prompts/hack-trial-prompt.md ] || { echo "run scripts/run_checks.sh first (clones .tb3)"; exit 1; }
  # Throwaway copy with the hack prompt appended, exactly as CI does. Never commit it.
  rm -rf .cheat && mkdir -p .cheat && cp -r "$TASK" .cheat/freight-bill-audit
  cat .tb3/docs/prompts/hack-trial-prompt.md >> .cheat/freight-bill-audit/instruction.md
  TASK=.cheat/freight-bill-audit
  ATTEMPTS=1
fi
N="${N_CONCURRENT:-$ATTEMPTS}"
# Unique job dir per run: two runs launched in the same second would otherwise
# collide on Harbor's timestamp-based default name.
SUFFIX=""
if [ "${CHEAT:-0}" = "1" ]; then SUFFIX="-cheat"; fi
JOB="$(date +%Y-%m-%d__%H-%M-%S)-${1:-x}${SUFFIX}"
# Absolute output dir. With Harbor's default relative "jobs/", Docker Compose on
# Windows resolves the copy target against the task's environment/ or tests/
# directory, so `compose cp` fails and Harbor falls back to `docker cp` / a tar
# stream. The fallback works (the oracle scores 1.0 through it), but an absolute
# path makes the first attempt succeed and keeps the logs clean.
OUT="$(pwd -W 2>/dev/null || pwd)/jobs"

case "${1:-}" in
  codex)
    harbor run -p "$TASK" --agent codex --model openai/gpt-5.6-sol --env docker --yes \
      -k "$ATTEMPTS" -n "$N" --job-name "$JOB" -o "$OUT" \
      --ae CODEX_FORCE_AUTH_JSON=1 --ak reasoning_effort=xhigh ;;
  claude)
    : "${CLAUDE_CODE_OAUTH_TOKEN:?export CLAUDE_CODE_OAUTH_TOKEN (from: claude setup-token)}"
    harbor run -p "$TASK" --agent claude-code --model anthropic/claude-opus-5 --env docker --yes \
      -k "$ATTEMPTS" -n "$N" --job-name "$JOB" -o "$OUT" \
      --ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
      --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --ak reasoning_effort=max ;;
  *) echo "usage: [CHEAT=1] [N_CONCURRENT=n] $0 codex|claude"; exit 1 ;;
esac
