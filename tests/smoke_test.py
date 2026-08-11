"""Offline smoke test. No API key, no network, no filings needed.

Run this first. If it passes, your Python environment and the variance
math are working, and any later failure is a network, key, or data issue
rather than a broken install.

Usage:
    python -m tests.smoke_test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.variance import (
    Variance,
    build_variance_table,
    decompose_gross_margin,
    flag_material,
    margin,
)

PASS, FAIL = "  PASS", "  FAIL"
failures = []


def check(label: str, condition: bool, detail: str = ""):
    print(f"{PASS if condition else FAIL}  {label}")
    if detail:
        print(f"         {detail}")
    if not condition:
        failures.append(label)


print("\nVariance math")

v = Variance(metric="revenue", prior=1000, current=1150)
check("absolute change", v.absolute == 150, v.describe())
check("percent change", abs(v.percent - 15.0) < 1e-9)

zero = Variance(metric="thing", prior=0, current=50)
check("zero prior returns None instead of crashing", zero.percent is None)

check("margin calculation", abs(margin(400, 1000) - 40.0) < 1e-9)
check("margin handles zero denominator", margin(400, 0) is None)


print("\nGross margin decomposition")

r = decompose_gross_margin(
    prior_revenue=1000, prior_cogs=600,
    current_revenue=1200, current_cogs=680,
)
check(
    "effects reconcile to total change",
    abs(r["residual"]) < 0.01,
    f"volume {r['volume_effect']:,.1f} + rate {r['rate_effect']:,.1f} "
    f"= {r['total_change']:,.1f}",
)

# Revenue up, margin rate flat. All of the change should be volume.
flat = decompose_gross_margin(1000, 600, 1500, 900)
check(
    "flat margin rate puts all change in volume",
    abs(flat["rate_effect"]) < 0.01 and abs(flat["volume_effect"] - 200) < 0.01,
)

# Revenue flat, margin rate up. All of the change should be rate.
same_rev = decompose_gross_margin(1000, 600, 1000, 500)
check(
    "flat revenue puts all change in rate",
    abs(same_rev["volume_effect"]) < 0.01 and abs(same_rev["rate_effect"] - 100) < 0.01,
)

try:
    decompose_gross_margin(0, 0, 1000, 600)
    check("zero prior revenue raises a clear error", False)
except ValueError:
    check("zero prior revenue raises a clear error", True)


print("\nVariance table and materiality")

prior = {"revenue": 1000, "opex": 700, "headcount_cost": 200}
current = {"revenue": 1150, "opex": 705, "headcount_cost": 260}

table = build_variance_table(prior, current)
check("builds one row per shared metric", len(table) == 3)

material = flag_material(table, threshold_pct=10.0)
names = sorted(x.metric for x in material)
check(
    "materiality filter catches the right rows",
    names == ["headcount_cost", "revenue"],
    f"flagged: {names}  (opex moved 0.7%, correctly excluded)",
)


print("\nProject files")

root = Path(__file__).resolve().parent.parent
for f in ["README.md", "requirements.txt", ".gitignore", ".env.example",
          "app.py", "eval/eval_set.csv"]:
    check(f"{f} present", (root / f).exists())

check(".env is gitignored", ".env" in (root / ".gitignore").read_text())


print("\n" + "=" * 46)
if failures:
    print(f"{len(failures)} FAILED")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed. Environment and variance math are working.")
print("Next: add your GEMINI_API_KEY to .env, then fetch filings.")
print("=" * 46)
