import math
from core import protection


def fake_sc(bus, case):
    table = {
        'Barra6': {'max':(10.33,8.737),'min':(7.772,6.511)},
        'Barra4':{'max':(14.99,11.99),'min':(11.274,8.865)},
        'Barra5': {'max':(9.50,8.20),'min':(8.004,6.705)},
        'Barra3': {'max':(14.10,12.20),'min':(11.443,8.994)},
    }
    a,b = table[bus][case]
    return {'bus':bus,'3f_ka':a,'ll_ka':b,'lg_ka':None,'llg_ka':None,'phase_min_method':'mock-min' if case=='min' else None}


def _stub_study(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    monkeypatch.setattr(protection, 'run_power_flow', lambda: {'ok': True})
    monkeypatch.setattr(protection, 'run_short_circuit', lambda case: {'ok': True})


def _trace(d, name):
    return next(t for t in d['traces'] if t['name'] == name)


def test_mb0_uses_exact_etap_stator_hot_points(monkeypatch):
    _stub_study(monkeypatch)
    d = protection.build_concise_tcc('mb0')
    t = _trace(d, 'M-B-0')
    assert t['kind'] == 'motor_thermal_exact'
    expected_x = [154.40*m for m in (1.55,1.70,1.90,2.40,3.00,3.60)]
    expected_y = [1000.0,500.0,300.0,150.0,87.0,60.0]
    assert len(t['x']) == 6
    for a,b in zip(t['x'], expected_x): assert math.isclose(a,b,rel_tol=0,abs_tol=1e-9)
    assert t['y'] == expected_y


def test_mb6_uses_exact_etap_stator_hot_points(monkeypatch):
    _stub_study(monkeypatch)
    d = protection.build_concise_tcc('mb6')
    t = _trace(d, 'M-B-6')
    assert t['kind'] == 'motor_thermal_exact'
    expected_x = [284.44*m for m in (1.55,1.70,1.90,2.40,3.00,3.60)]
    expected_y = [1000.0,500.0,300.0,150.0,87.0,60.0]
    assert len(t['x']) == 6
    for a,b in zip(t['x'], expected_x): assert math.isclose(a,b,rel_tol=0,abs_tol=1e-9)
    assert t['y'] == expected_y


def test_no_cold_curve_is_fabricated(monkeypatch):
    _stub_study(monkeypatch)
    for view in ('mb0','mb6'):
        d = protection.build_concise_tcc(view)
        names = [t['name'].lower() for t in d['traces']]
        assert not any('cold' in name for name in names)
