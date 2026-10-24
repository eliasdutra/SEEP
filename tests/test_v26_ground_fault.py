import pytest
from core import solver


def test_physical_ground_network_splits_at_dyn_transformer():
    solver.run_ground_sequence_fallback.cache_clear()
    d = solver.run_ground_sequence_fallback('max')
    rows = {r['bus']: r for r in d['rows']}
    assert d['ok']
    # Rede AT: gerador Y aterrado -> Cabo1 -> Cabo8.
    assert rows['Barra1']['lg_ka'] > 0
    assert rows['Barra3']['lg_ka'] > 0
    assert rows['Barra4']['lg_ka'] > 0
    # Rede BT: o Dyn cria um novo caminho Z0 local no Y aterrado.
    assert rows['Barra5']['lg_ka'] > 0
    assert rows['Barra6']['lg_ka'] > 0
    assert 'delta bloqueia AT' in rows['Barra5']['z0_path']
    # Ordem esperada no lado AT: os cabos aumentam a impedância e reduzem LG.
    assert rows['Barra1']['lg_ka'] > rows['Barra3']['lg_ka'] > rows['Barra4']['lg_ka']


def test_run_short_circuit_replaces_zero_1ph_with_ground_fallback(monkeypatch):
    solver.clear_solver_cache()
    fb = {r['bus']: r for r in solver.run_ground_sequence_fallback('max')['rows']}

    def fake_run_fault(case, fault):
        out = {}
        for bus, r in fb.items():
            if fault == '3ph':
                out[bus] = {'ikss_ka': 10.0}
            elif fault == '2ph':
                out[bus] = {
                    'ikss_ka': 8.0,
                    'rk_ohm': r['r1_ohm'], 'xk_ohm': r['x1_ohm'],
                    'rk2_ohm': r['r2_ohm'], 'xk2_ohm': r['x2_ohm'],
                }
            else:
                # Simula a limitação observada: PP devolve 0 na rede AT,
                # mas valores válidos no lado 6,6 kV.
                if bus in {'Barra1', 'Barra3', 'Barra4'}:
                    out[bus] = {'ikss_ka': 0.0}
                else:
                    out[bus] = {
                        'ikss_ka': 9.9,
                        'rk0_ohm': r['r0_ohm'], 'xk0_ohm': r['x0_ohm'],
                    }
        return out

    monkeypatch.setattr(solver, '_run_fault', fake_run_fault)
    solver.run_short_circuit.cache_clear()
    d = solver.run_short_circuit('max')
    rows = {r['bus']: r for r in d['rows']}
    for bus in ('Barra1', 'Barra3', 'Barra4'):
        assert rows[bus]['lg_ka'] > 0
        assert 'fallback físico Z0' in rows[bus]['lg_method']
        assert rows[bus]['lg_ka_pandapower'] == 0.0
    for bus in ('Barra5', 'Barra6'):
        assert rows[bus]['lg_ka'] == 9.9
        assert rows[bus]['lg_method'] == 'Pandapower IEC 60909'


def test_segundo_gerador_dobra_a_contribuicao_na_barra_principal():
    """V30: duas máquinas iguais em paralelo na Barra3 metade da impedância vista.

    Com GE1 e GE2 em serviço, a Z1 de Thévenin na barra principal cai pela
    metade em relação a uma máquina só — e a corrente de falta dobra. Abaixo do
    transformador o efeito é menor, porque ali quem domina é a impedância do
    próprio T1. É esse contraste que a aula demonstra.
    """
    from core.data import enrich_model
    from core.storage import get_model

    modelo = enrich_model(get_model())
    z_dois, _ = solver._thevenin_por_sequencia(modelo, 1)

    um = {**modelo, "generators": [g for g in modelo["generators"] if g["name"] == "GE1"]}
    z_um, _ = solver._thevenin_por_sequencia(um, 1)

    assert abs(z_dois["Barra3"]) == pytest.approx(abs(z_um["Barra3"]) / 2.0, rel=1e-9)
    # No lado de 6,6 kV a redução existe, mas é bem menor que a metade.
    reducao_bt = abs(z_dois["Barra5"]) / abs(z_um["Barra5"])
    assert 0.5 < reducao_bt < 1.0


def test_sem_gerador_em_servico_o_estudo_e_recusado():
    """V30: sem fonte não há curto-circuito — e o erro tem de ser explícito."""
    from core.data import enrich_model
    from core.storage import get_model

    modelo = enrich_model(get_model())
    modelo = {**modelo, "generators": [dict(g, in_service=False) for g in modelo["generators"]]}
    try:
        solver._fontes_em_servico(modelo)
    except RuntimeError as exc:
        assert "Nenhum gerador em serviço" in str(exc)
    else:
        raise AssertionError("deveria ter recusado o estudo sem fonte")
