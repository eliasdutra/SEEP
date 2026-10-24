from pathlib import Path
from core import protection


def fake_sc(bus, case):
    table = {
        'Barra6': {'max':(10.2,8.8),'min':(7.772,6.511)},
        'Barra4':{'max':(13.4,11.6),'min':(11.274,8.865)},
        'Barra5': {'max':(9.5,8.2),'min':(8.004,6.705)},
        'Barra3': {'max':(14.1,12.2),'min':(11.443,8.994)},
    }
    a,b=table[bus][case]
    return {'bus':bus,'3f_ka':a,'ll_ka':b,'lg_ka':None,'llg_ka':None,'phase_min_method':'mock-min' if case=='min' else None}


def test_four_required_tcc_views_are_dynamic(monkeypatch):
    monkeypatch.setattr(protection,'get_bus_short_circuit',fake_sc)
    expected = {'mb0':6.6,'mb6':13.8,'t1':13.8,'general':13.8}
    for view,ref in expected.items():
        d=protection.build_concise_tcc(view)
        assert d['reference_kv']==ref
        assert d['traces']
        assert d['study_chain']==['Modelo físico','Fluxo de potência','Curto-circuito IEC 60909','Ajustes 50/51','Coordenograma']


def test_motor_tcc_contains_relay_start_cable_and_fault(monkeypatch):
    monkeypatch.setattr(protection,'get_bus_short_circuit',fake_sc)
    d=protection.build_concise_tcc('mb0')
    kinds={t['kind'] for t in d['traces']}
    assert {'relay_effective','motor_start','cable','fault_max','fault_min'} <= kinds
    assert any(t['name'].startswith('Relé11') for t in d['traces'])
    assert any(t['name']=='M-B-0-100%' for t in d['traces'])


def test_frontend_preserves_full_study_chain_and_adjustments():
    html=Path('templates/index.html').read_text(encoding='utf-8')
    js=Path('static/app.js').read_text(encoding='utf-8')
    assert 'Ajustes 50/51' in html
    assert 'Fluxo de potência' in html and 'Curto-circuito' in html
    for label in ('M-B-0 · 6,6 kV','M-B-6 · 13,8 kV','T1 · Trafo','Geral'):
        assert label in html
    assert 'pe-p51' in js and 'pe-p50' in js and 'pe-tms' in js
    assert '/api/protection-context/' in js
    assert '/api/tcc-concise/' in js


def test_solver_source_contains_pandapower_flow_and_short_circuit():
    src=Path('core/solver.py').read_text(encoding='utf-8')
    assert 'pp.runpp' in src
    assert 'pandapower.shortcircuit' in src
    assert 'sc.calc_sc' in src
