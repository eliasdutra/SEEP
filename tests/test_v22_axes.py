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


def test_tcc_views_expose_fixed_etap_axis(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    expected = {
        'mb0': (10.0, [5.0, 1.0e5]),
        'mb6': (100.0, [50.0, 1.0e6]),
        't1': (10.0, [5.0, 1.0e5]),
        'general': (100.0, [50.0, 1.0e6]),
    }
    for view, (mult, xr) in expected.items():
        d = protection.build_concise_tcc(view)
        assert d['x_range'] == xr
        assert d['etap_axis']['display_multiplier'] == mult
        assert d['etap_axis']['x_tick_text'] == ['0,5', '1', '3', '5', '10', '30', '50', '100', '300', '1K', '3K', '5K', '10K']
        assert d['etap_axis']['y_tick_vals'][0] == 0.01
        assert d['etap_axis']['y_tick_vals'][-1] == 1000
