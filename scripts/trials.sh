#!/usr/bin/env bash
# Standard and adversarial trials. Usage:
#   scripts/trials.sh codex          # one standard codex trial
#   scripts/trials.sh claude         # one standard claude-code trial (needs CLAUDE_CODE_OAUTH_TOKEN)
#   CHEAT=1 scripts/trials.sh codex  # adversarial trial: hack prompt prepended to instruction
# Run ONE trial at a time; log every job dir in RESULTS.md.
set -euo pipefail
cd "$(dirname "$0")/.."
TASK=tasks/freight-bill-audit
if [ "${CHEAT:-0}" = "1" ]; then
  # Build a throwaway copy of the task with the hack prompt prepended (never commit it).
  rm -rf .cheat && mkdir -p .cheat && cp -r "$TASK" .cheat/freight-bill-audit
  { cat .tb3/docs/prompts/hack-trial-prompt.md; echo; cat "$TASK/instruction.md"; } > .cheat/freight-bill-audit/instruction.md
  TASK=.cheat/freight-bill-audit
fi
case "$1" in
  codex)
    harbor run -p "$TASK" --agent codex --model openai/gpt-5.6-sol --env docker --yes \
      --ae CODEX_FORCE_AUTH_JSON=1 --ak reasoning_effort=xhigh ;;
  claude)
    : "${CLAUDE_CODE_OAUTH_TOKEN:?run: claude setup-token}"
    harbor run -p "$TASK" --agent claude-code --model anthropic/claude-opus-5 --env docker --yes \
      --ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
      --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --ak reasoning_effort=max ;;
  *) echo "usage: $0 codex|claude"; exit 1 ;;
esac
