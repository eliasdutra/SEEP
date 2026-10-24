from core import protection


def test_cable2_damage_is_short_time_only():
    cable = next(c for c in protection._ctx()[3].values() if c['name'] == 'Cabo2')
    xs, ys = protection._cable_damage_trace(cable, cable.get('k_adiabatic'), 100000.0, min_current=10.0)
    assert xs and ys
    assert min(ys) >= 0.01 - 1e-9
    assert max(ys) <= 10.0 + 1e-9
    # Anchor expected from K²S² = 5.23 kA²s: at t=10 s, I≈723 A.
    i_at_max_t = xs[ys.index(max(ys))]
    assert 700.0 <= i_at_max_t <= 750.0


def test_cable8_damage_is_short_time_only():
    cable = next(c for c in protection._ctx()[3].values() if c['name'] == 'Cabo8')
    xs, ys = protection._cable_damage_trace(cable, cable.get('k_adiabatic'), 100000.0, min_current=10.0)
    assert xs and ys
    assert min(ys) >= 0.01 - 1e-9
    assert max(ys) <= 10.0 + 1e-9


def test_motor_view_keeps_motor_thermal_and_start_curves():
    traces = protection._motor_view_traces('M-B-0', 'Z-R11', 6.6, 'Cabo2')
    names = {t['name'] for t in traces}
    assert 'M-B-0' in names
    assert 'M-B-0-100%' in names
    assert 'Cabo2 - P' in names
