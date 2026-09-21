# Results

All commands were run from the repository root unless stated otherwise.
Backend: local Docker (`--env docker`). Harbor version: `harbor --version` → __FILL__.

## 1. Static checks

```bash
scripts/run_checks.sh
```
| check | result |
|---|---|
| check-canary | __ |
| check-instruction-suffix | __ |
| check-separate-verifier | __ |
| check-pip-pinning | __ |
| check-pytest-version | __ |
| check-test-file-references | __ |
| check-test-sh-sanity / verifier-tooling-baked / trial-network-fetch | __ |
| check-task-fields / slug / package-name / timeout / absolute-path | __ |
| check-dockerfile-* / nproc / allow-internet | __ |

## 2. Implementation rubric

```bash
harbor check tasks/freight-bill-audit -r docs/prompts/task-implementation.toml -m <model>
```
Result: __ (attach `checks/` output or summarise flagged criteria and fixes)

## 3. Oracle and nop

```bash
harbor run -p tasks/freight-bill-audit --agent oracle --env docker --yes
harbor run -p tasks/freight-bill-audit --agent nop    --env docker --yes
```
| run | reward | verifier time |
|---|---|---|
| oracle | __ | __ |
| nop | __ | __ |

## 4. Standard trials (3 per agent)

Config mirrors `.github/harbor-run-defaults.yml` at commit __.

```bash
harbor run -p tasks/freight-bill-audit --agent codex --model openai/gpt-5.6-sol \
  --env docker --yes --ae CODEX_FORCE_AUTH_JSON=1 --ak reasoning_effort=xhigh
harbor run -p tasks/freight-bill-audit --agent claude-code --model anthropic/claude-opus-5 \
  --env docker --yes --ae CLAUDE_FORCE_OAUTH=1 --ae CLAUDE_CODE_OAUTH_TOKEN=<token> \
  --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --ak reasoning_effort=max
```
| agent | trial | reward | wall time | failure type (genuine / infra) | failing tests |
|---|---|---|---|---|---|
| codex gpt-5.6-sol xhigh | 1 | __ | __ | __ | __ |
| codex gpt-5.6-sol xhigh | 2 | __ | __ | __ | __ |
| codex gpt-5.6-sol xhigh | 3 | __ | __ | __ | __ |
| claude-code opus-5 max | 1 | __ | __ | __ | __ |
| claude-code opus-5 max | 2 | __ | __ | __ | __ |
| claude-code opus-5 max | 3 | __ | __ | __ | __ |

Infra-failed trials that were rerun (rate limit / crash / timeout): __

## 5. Adversarial trials (hack prompt prepended, 1 per agent)

Prompt: `docs/prompts/hack-trial-prompt.md` at commit __.
| agent | reward | what the agent attempted | why it scored 0 |
|---|---|---|---|
| codex | __ | __ | __ |
| claude-code | __ | __ | __ |

## 6. Failure analysis

```bash
harbor analyze <job-dir> -m sonnet -r docs/prompts/trial-analysis.toml \
  --job-prompt docs/prompts/trial-analysis-job.txt
```
Per trap, which agents got it wrong and how (link to `harbor analyze` verdicts):

| trap | codex 1/2/3 | claude 1/2/3 | typical wrong assumption |
|---|---|---|---|
| T01 sailing-month index | | | |
| ... | | | |

Difficulty crux verdicts vs `difficulty_explanation`: __
