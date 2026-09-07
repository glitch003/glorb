"""Estimate state of charge from resting cell voltage.

Two chemistries need this:

The TeslaBMS boards on the 24 V bank (Tesla NCA) measure voltage and
temperature only -- there is no current sensor and so no coulomb counting,
which means no real SOC. What they do give is accurate per-cell voltage, and
for lithium NCA the open-circuit voltage curve is steep enough to place charge
to within a few percent while the pack is resting.

The 12 V EG4 packs (LiFePO4) do carry a coulomb counter, but it drifts badly:
on 2026-09-07 a pack reporting 22% was resting near 3.37 V/cell, which for
LiFePO4 is nearly full. So the 12 V side ignores the BMS's SOC and derives its
own from cell voltage too.

The NCA curve is the usual shape (3.0 V empty, 4.2 V full). Its one
independent check is a good one: glorb's 72 V drive pack is the same Tesla
module chemistry and carries a real Orion BMS, and on 2026-09-02 the Orion
reported 86% SOC with the pack sitting at 4.072 V/cell. This table returns
86.0% for that voltage, so the two agree at the one point where a comparison
is possible.

The LiFePO4 curve follows the commonly published 12 V resting chart (2.5 V
empty, 3.4 V full per cell). LiFePO4 is famously flat between 20% and 90% --
tens of millivolts cover tens of percent -- so mid-range values are coarse.
The endpoints are the trustworthy part, which is why eg4.py pins 100% from the
charger-tail-current watermark rather than from this table alone.

Either estimate is only meaningful at rest. Under load the cells sag and it
reads low; on charge they are pushed up and it reads high. The 24 V bank has
no current measurement, so nothing there can detect that; the 12 V packs do
measure current, and eg4.py uses it.
"""

# (open-circuit volts per cell, percent charged)
NCA_OCV_CURVE = [
    (3.00, 0.0), (3.30, 5.0), (3.40, 10.0), (3.45, 15.0), (3.50, 20.0),
    (3.55, 25.0), (3.57, 30.0), (3.60, 35.0), (3.63, 40.0), (3.66, 45.0),
    (3.70, 50.0), (3.74, 55.0), (3.79, 60.0), (3.84, 65.0), (3.89, 70.0),
    (3.94, 75.0), (4.00, 80.0), (4.06, 85.0), (4.12, 90.0), (4.16, 95.0),
    (4.20, 100.0),
]


# (open-circuit volts per cell, percent charged), per the widely published
# 12 V LiFePO4 resting chart. The 3.29->3.30 step really is 10% in 10 mV;
# that is the flat zone, not a typo.
LFP_OCV_CURVE = [
    (2.50, 0.0), (3.00, 5.0), (3.13, 10.0), (3.19, 15.0), (3.22, 20.0),
    (3.25, 30.0), (3.27, 40.0), (3.28, 50.0), (3.29, 60.0), (3.30, 70.0),
    (3.32, 80.0), (3.35, 90.0), (3.37, 95.0), (3.40, 100.0),
]


def _interpolate(curve, cell_voltage, low_slack, high_slack):
    """Percent charged for one resting cell, linearly interpolated.

    Returns None rather than a number for a voltage outside the curve by more
    than the slack -- a cell that reads 0 V or 5 V is a measurement problem,
    and clamping it to 0% or 100% would hide that.
    """
    if cell_voltage is None:
        return None
    low_v, low_pct = curve[0]
    high_v, high_pct = curve[-1]
    if cell_voltage < low_v - low_slack or cell_voltage > high_v + high_slack:
        return None
    if cell_voltage <= low_v:
        return low_pct
    if cell_voltage >= high_v:
        return high_pct
    for (v0, p0), (v1, p1) in zip(curve, curve[1:]):
        if v0 <= cell_voltage <= v1:
            span = v1 - v0
            return p0 + (p1 - p0) * (cell_voltage - v0) / span
    return None


def estimate_soc(cell_voltage):
    """Percent charged for one resting Tesla NCA cell."""
    return _interpolate(NCA_OCV_CURVE, cell_voltage, 0.5, 0.2)


def estimate_soc_lfp(cell_voltage):
    """Percent charged for one resting LiFePO4 cell.

    The high-side slack is wider than NCA's because a LiFePO4 charger may
    legitimately hold up to 3.65 V/cell during absorption; only beyond that
    is a reading treated as a measurement problem.
    """
    return _interpolate(LFP_OCV_CURVE, cell_voltage, 0.5, 0.3)
