# freight-bill-audit — a Terminal-Bench 3 task

Take-home for the Klavis AI Founding Engineer application. One original TB3 task:
audit a batch of ocean-freight invoices (text PDFs, four vendor layouts) against
rate contracts, a shipment register and a house audit policy, deliver a reusable
audit tool, and allocate approved cost to sales orders. The verifier re-runs the
tool on a hidden second batch.

| | |
|---|---|
| Task directory | [`tasks/freight-bill-audit/`](tasks/freight-bill-audit/) — drop-in for the TB3 repo layout |
| Design decisions | [`DESIGN.md`](DESIGN.md) |
| Check + trial results, failure analysis | [`RESULTS.md`](RESULTS.md) |
| Data generator (dev only) | [`tools/generator/`](tools/generator/) |
| Reproduce checks / oracle / trials | [`scripts/`](scripts/) |

## Status

- [ ] generator complete, both batches committed
- [ ] oracle 1.0 / nop 0
- [ ] static checks + implementation rubric pass
- [ ] 3 × codex, 3 × claude-code standard trials — all genuine fails
- [ ] 1 × codex, 1 × claude-code adversarial trials — reward 0
- [ ] failure analysis written
