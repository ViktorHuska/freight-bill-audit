#!/usr/bin/env bash
# Oracle must score 1.0, nop must score 0. Run after every change to data, policy or tests.
set -euo pipefail
cd "$(dirname "$0")/.."
harbor run -p tasks/freight-bill-audit --agent oracle --env docker --yes "$@"
harbor run -p tasks/freight-bill-audit --agent nop    --env docker --yes "$@"
