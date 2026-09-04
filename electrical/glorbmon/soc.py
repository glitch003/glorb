"""Estimate state of charge from resting cell voltage (Tesla NCA cells).

The TeslaBMS boards on the 24 V bank measure voltage and temperature only --
there is no current sensor and so no coulomb counting, which means no real
SOC. What they do give is accurate per-cell voltage, and for lithium NCA the
open-circuit voltage curve is steep enough to place charge to within a few
percent while the pack is resting.

The curve below is the usual NCA shape (3.0 V empty, 4.2 V full). Its one
independent check is a good one: glorb's 72 V drive pack is the same Tesla
module chemistry and carries a real Orion BMS, and on 2026-09-02 the Orion
reported 86% SOC with the pack sitting at 4.072 V/cell. This table returns
86.0% for that voltage, so the two agree at the one point where a comparison
is possible.

The estimate is only meaningful at rest. Under load the cells sag and it reads
low; on charge they are pushed up and it reads high. The 24 V bank has no
current measurement, so nothing here can detect that -- which is why every
value this module produces is labelled an estimate.
"""

# (open-circuit volts per cell, percent charged)
NCA_OCV_CURVE = [
    (3.00, 0.0), (3.30, 5.0), (3.40, 10.0), (3.45, 15.0), (3.50, 20.0),
    (3.55, 25.0), (3.57, 30.0), (3.60, 35.0), (3.63, 40.0), (3.66, 45.0),
    (3.70, 50.0), (3.74, 55.0), (3.79, 60.0), (3.84, 65.0), (3.89, 70.0),
    (3.94, 75.0), (4.00, 80.0), (4.06, 85.0), (4.12, 90.0), (4.16, 95.0),
    (4.20, 100.0),
]


def estimate_soc(cell_voltage):
    """Percent charged for one resting NCA cell, linearly interpolated.

    Returns None rather than a number for a voltage outside the curve by more
    than rounding -- a cell that reads 0 V or 5 V is a measurement problem,
    and clamping it to 0% or 100% would hide that.
    """
    if cell_voltage is None:
        return None
    low_v, low_pct = NCA_OCV_CURVE[0]
    high_v, high_pct = NCA_OCV_CURVE[-1]
    if cell_voltage < low_v - 0.5 or cell_voltage > high_v + 0.2:
        return None
    if cell_voltage <= low_v:
        return low_pct
    if cell_voltage >= high_v:
        return high_pct
    for (v0, p0), (v1, p1) in zip(NCA_OCV_CURVE, NCA_OCV_CURVE[1:]):
        if v0 <= cell_voltage <= v1:
            span = v1 - v0
            return p0 + (p1 - p0) * (cell_voltage - v0) / span
    return None
