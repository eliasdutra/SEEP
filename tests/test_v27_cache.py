from pathlib import Path
from core import solver


def test_powerflow_is_memory_cached():
    assert hasattr(solver.run_power_flow, 'cache_info')
    assert hasattr(solver.run_power_flow, 'cache_clear')


def test_clear_solver_cache_includes_powerflow():
    src = Path('core/solver.py').read_text(encoding='utf-8')
    block = src[src.index('def clear_solver_cache():'):src.index('def solver_cache_status() -> dict:')]
    assert 'run_power_flow.cache_clear()' in block
    assert 'run_short_circuit.cache_clear()' in block


def test_protection_save_does_not_rebuild_tcc_or_clear_electrical_cache():
    src = Path('app.py').read_text(encoding='utf-8')
    start = src.index('def api_protection(zone_id):')
    end = src.index('@app.post("/api/protection/<zone_id>/reset")')
    block = src[start:end]
    assert 'build_tcc(zone_id)' not in block
    assert 'clear_solver_cache' not in block
    assert 'electrical_cache' in block


def test_front_labels_explicit_system_recalculation_and_fast_protection_save():
    html = Path('templates/index.html').read_text(encoding='utf-8')
    js = Path('static/app.js').read_text(encoding='utf-8')
    assert 'Recalcular sistema' in html
    # A tela precisa dizer que salvar ajuste NÃO roda o Pandapower de novo.
    # O texto foi reescrito na V29 ("não executa Pandapower novamente" saiu);
    # o que o teste trava é a afirmação, não a frase antiga.
    assert 'não recalcula a rede elétrica' in html
    assert 'Pandapower não recalculado' in js
