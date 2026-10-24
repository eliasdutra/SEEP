from core import protection


def fake_sc(bus, case):
    vals = {
        'Barra6': {'max':(10.33,8.737),'min':(7.772,6.511)},
        'Barra4':{'max':(14.99,11.99),'min':(11.274,8.865)},
        'Barra5': {'max':(9.50,8.20),'min':(8.004,6.705)},
        'Barra3': {'max':(14.10,12.20),'min':(11.443,8.994)},
    }
    a,b = vals[bus][case]
    return {'bus':bus,'3f_ka':a,'ll_ka':b,'lg_ka':None,'llg_ka':None,'phase_min_method':'mock'}


def test_motor_views_include_visible_start_and_exact_thermal(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    for view, motor in [('mb0','M-B-0'),('mb6','M-B-6')]:
        d = protection.build_concise_tcc(view)
        start = next(t for t in d['traces'] if t['name'] == f'{motor}-100%')
        thermal = next(t for t in d['traces'] if t['name'] == motor)
        assert start['kind'] == 'motor_start'
        assert start['mode'] == 'lines'
        assert len(start['x']) >= 5 and len(start['x']) == len(start['y'])
        assert thermal['kind'] == 'motor_thermal_exact'
        assert thermal['mode'] == 'lines'
        assert len(thermal['x']) == 6
        assert thermal['y'] == [1000.0, 500.0, 300.0, 150.0, 87.0, 60.0]
