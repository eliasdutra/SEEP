import math
from core import protection


def fake_sc(bus, case):
    vals = {
        ('Barra6','max'):(10.2,8.8), ('Barra6','min'):(7.772,6.511),
        ('Barra4','max'):(13.4,11.6), ('Barra4','min'):(11.274,8.865),
        ('Barra5','max'):(9.5,8.2), ('Barra5','min'):(8.004,6.705),
        ('Barra3','max'):(14.1,12.2), ('Barra3','min'):(11.443,8.994),
    }
    f3,ll = vals[(bus,case)]
    return {'bus':bus,'3f_ka':f3,'ll_ka':ll,'lg_ka':None,'llg_ka':None,
            'phase_min_method':'IEC radial phase MIN · physical model' if case=='min' else None}


def test_iec_extremely_inverse_formula():
    # P241 / IEC EI: t = TMS*80/(M^2-1)
    t = protection.relay_time(460.0, 230.0, 0.325, 'IEC_EI')
    assert math.isclose(t, 0.325*80/(2**2-1), rel_tol=1e-12)


def test_relay11_secondary_settings_match_etap_screen():
    s = protection.reset_settings('Z-R11')
    ratio = s['ct_primary_a']/s['ct_secondary_a']
    assert ratio == 200.0
    assert math.isclose(s['phase_stage1_pickup_a']/ratio, 1.15)
    assert math.isclose(s['phase_stage1_pickup_a']/s['ct_primary_a'], 0.23)
    assert math.isclose(s['phase_stage3_pickup_a']/ratio, 38.8)
    assert math.isclose(s['phase_stage3_pickup_a']/s['ct_primary_a'], 7.76)


def test_protection_context_uses_calculated_short_not_static(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    d = protection.protection_context('Z-R11')
    assert d['faults']['3f_max_a'] == 10200.0
    assert d['faults']['phase_min_fault'] == 'LL'
    assert d['faults']['phase_min_a'] == 6511.0
    assert math.isclose(d['calculations']['sensitivity'], 6511/230)
    sc = d['calculations']['setting']
    assert sc['pickup_51_secondary_a'] == 1.15
    assert sc['pickup_51_multiple_ct'] == 0.23
    assert sc['formula'] == 't = TMS·K/(M^α−1)'
    assert sc['constants'] == {'K':80.0,'alpha':2.0,'L':0.0}


def test_editing_adjustment_changes_tcc_curve(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    protection.reset_settings('Z-R11')
    before = protection.build_concise_tcc('mb0')
    r0 = next(t for t in before['traces'] if t.get('zone_id')=='Z-R11')
    protection.update_settings('Z-R11', {'phase_stage1_pickup_a':300.0,'phase_time_setting':0.5})
    after = protection.build_concise_tcc('mb0')
    r1 = next(t for t in after['traces'] if t.get('zone_id')=='Z-R11')
    assert r0['x'][0] != r1['x'][0]
    assert r1['x'][0] > r0['x'][0]


def test_t1_curve_shift_6k6_to_13k8(monkeypatch):
    monkeypatch.setattr(protection, 'get_bus_short_circuit', fake_sc)
    protection.reset_settings('Z-R11')
    d = protection.build_concise_tcc('t1')
    r11 = next(t for t in d['traces'] if t.get('zone_id')=='Z-R11')
    # Native pickup 230 A at 6.6 kV -> ~110 A at 13.8 kV, trace starts slightly above pickup.
    assert 109.5 < r11['x'][0] < 111.5
    inrush = next(t for t in d['traces'] if t['name']=='T1 Inrush')
    assert inrush['x'] == [3681.7] and inrush['y'] == [0.0167]
