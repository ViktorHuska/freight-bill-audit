# Generator (dev tooling — not part of the task)

Produces both batches and their ground truth. Run from the repo root:

```bash
python tools/generator/generate.py --batch a --seed 20240301 \
  --data-out tasks/freight-bill-audit/environment/data \
  --truth-out tasks/freight-bill-audit/tests/data/truth/batch_a.json
python tools/generator/generate.py --batch b --seed 20240902 \
  --data-out tasks/freight-bill-audit/tests/data/batch_b \
  --truth-out tasks/freight-bill-audit/tests/data/truth/batch_b.json
```

Modules: `models.py` (schema), `pricing.py` (planting-time rules), `traps.py`
(difficulty budget), `generate.py` (world + orchestration), `render.py` (PDF
layouts), `io_utils.py` (data files). Requires `reportlab` pinned in
`requirements-dev.txt`.

Ground truth is derived twice: here at planting time, and independently by
`tasks/freight-bill-audit/solution/audit.py`. The oracle run must score 1.0 on
both batches before any agent trial is launched.
