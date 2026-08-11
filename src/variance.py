"""Period-over-period variance analysis.

This is the finance half of the project. It is deterministic arithmetic,
not model output, which is exactly why it is credible. Every number here
should reconcile to the filing.
"""

from dataclasses import dataclass


@dataclass
class Variance:
    metric: str
    prior: float
    current: float

    @property
    def absolute(self) -> float:
        return self.current - self.prior

    @property
    def percent(self) -> float | None:
        if self.prior == 0:
            return None
        return (self.current - self.prior) / abs(self.prior) * 100

    def describe(self) -> str:
        pct = f"{self.percent:+.1f}%" if self.percent is not None else "n/a"
        return f"{self.metric}: {self.prior:,.0f} to {self.current:,.0f} ({self.absolute:+,.0f}, {pct})"


def margin(numerator: float, denominator: float) -> float | None:
    """Margin as a percentage. Returns None on a zero denominator."""
    if denominator == 0:
        return None
    return numerator / denominator * 100


def decompose_gross_margin(
    prior_revenue: float,
    prior_cogs: float,
    current_revenue: float,
    current_cogs: float,
) -> dict:
    """Split a gross profit change into a volume effect and a rate effect.

    Volume effect  = revenue change held at the prior-period margin rate
    Rate effect    = margin rate change applied to current revenue

    The two effects sum to the total gross profit change. Verify that
    before trusting any output from this function.
    """
    prior_gp = prior_revenue - prior_cogs
    current_gp = current_revenue - current_cogs

    prior_rate = margin(prior_gp, prior_revenue)
    current_rate = margin(current_gp, current_revenue)

    if prior_rate is None or current_rate is None:
        raise ValueError("Cannot decompose with zero revenue in a period")

    volume_effect = (current_revenue - prior_revenue) * (prior_rate / 100)
    rate_effect = current_revenue * ((current_rate - prior_rate) / 100)

    total = current_gp - prior_gp
    residual = total - (volume_effect + rate_effect)

    return {
        "prior_gross_profit": prior_gp,
        "current_gross_profit": current_gp,
        "total_change": total,
        "volume_effect": volume_effect,
        "rate_effect": rate_effect,
        "residual": residual,
        "prior_margin_pct": prior_rate,
        "current_margin_pct": current_rate,
    }


def build_variance_table(prior: dict[str, float], current: dict[str, float]) -> list[Variance]:
    """Build variances for every metric present in both periods."""
    shared = [k for k in current if k in prior]
    return [Variance(metric=k, prior=prior[k], current=current[k]) for k in shared]


def flag_material(variances: list[Variance], threshold_pct: float = 10.0) -> list[Variance]:
    """Return only variances exceeding the materiality threshold.

    Ten percent is a starting convention, not a rule. Document whatever
    threshold you actually use and why.
    """
    return [
        v for v in variances
        if v.percent is not None and abs(v.percent) >= threshold_pct
    ]


if __name__ == "__main__":
    # Sanity check. Effects should sum to the total change.
    result = decompose_gross_margin(
        prior_revenue=1000, prior_cogs=600,
        current_revenue=1200, current_cogs=680,
    )
    for k, v in result.items():
        print(f"{k:>24}: {v:,.2f}")
    assert abs(result["residual"]) < 0.01, "Decomposition does not reconcile"
    print("\nDecomposition reconciles.")
