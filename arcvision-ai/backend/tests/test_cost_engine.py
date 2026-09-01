"""Unit-level test of the cost engine math (without DB)."""

from decimal import Decimal


def _line(qty, waste, material, labor, equip):
    q = Decimal(str(qty)) * (Decimal("1") + Decimal(str(waste)))
    return q * (Decimal(str(material)) + Decimal(str(labor)) + Decimal(str(equip)))


def test_cost_breakdown_math():
    # 100 m3 concrete at 320 mat + 80 labor + 40 equip, waste 0.05
    direct = _line(100, 0.05, 320, 80, 40)
    # 100 * 1.05 * (320+80+40) = 105 * 440 = 46200
    assert direct == Decimal("46200.000")

    indirect_pct = Decimal("0.08")
    contingency_pct = Decimal("0.05")
    margin_pct = Decimal("0.14")

    indirect = direct * indirect_pct
    contingency = (direct + indirect) * contingency_pct
    total = direct + indirect + contingency
    bid = total * (Decimal("1") + margin_pct)

    assert indirect == Decimal("3696.00000")
    assert round(float(contingency), 2) == 2494.80
    assert round(float(total), 2) == 52390.80
    assert round(float(bid), 2) == 59725.51
