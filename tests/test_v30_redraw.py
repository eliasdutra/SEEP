"""V30: curto recalculado tem de redesenhar a tela que está aberta.

O defeito corrigido: cada tela só se remontava ao ser aberta pelo menu.
Recalcular o sistema (ou editar equipamento) com o coordenograma na
frente deixava o desenho antigo na tela, e só trocar de aba e voltar
mostrava o resultado novo.
"""
from pathlib import Path

import core.protection as protection
import core.solver as solver

JS = Path('static/app.js').read_text(encoding='utf-8')


def _bloco(texto, inicio, fim):
    i = texto.index(inicio)
    return texto[i:texto.index(fim, i)]


def test_recalcular_redesenha_a_tela_aberta():
    bloco = _bloco(JS, "$('#recalc-btn').onclick", "$('#print-btn')")
    assert '/api/recalculate' in bloco
    assert 'invalidateDerivedState()' in bloco
    assert 'reloadActiveView()' in bloco


def test_editar_equipamento_redesenha_a_tela_aberta():
    bloco = _bloco(JS, 'async function refreshAfterEquipmentChange()',
                   'function updateModelMetrics()')
    assert 'invalidateDerivedState()' in bloco
    assert 'reloadActiveView()' in bloco


def test_reload_cobre_todas_as_telas_com_resultado_eletrico():
    bloco = _bloco(JS, 'async function reloadActiveView()',
                   "$('#recalc-btn').onclick")
    for tela in ('powerflow', 'shortcircuit', 'protection', 'tcc',
                 'manual', 'expert'):
        assert f"v==='{tela}'" in bloco, tela


def test_invalidate_limpa_tambem_especialista_e_revisao():
    bloco = _bloco(JS, 'function invalidateDerivedState()', '\n//')
    # state.expertData só é buscado quando está nulo (ver loadExpert):
    # sem limpar aqui, o especialista mostra número velho a sessão toda.
    for chave in ('state.pf=null', 'state.sc={max:null,min:null}',
                  'state.expertData=null', 'state.review=null',
                  'state.lastTCC=null'):
        assert chave in bloco, chave


def test_folha_acompanha_o_curto_depois_de_invalidar(monkeypatch):
    """A folha é remontada a partir do curto, não de uma cópia guardada."""
    valor = {'ka': 10.0}

    def sem_pandapower(zone_id, case):
        raise RuntimeError('indisponível')

    def falta_falsa(bus, case):
        k = valor['ka'] * (1.0 if case == 'max' else 0.8)
        return {'bus': bus, '3f_ka': k, 'll_ka': k * 0.87,
                'lg_ka': k * 0.5, 'llg_ka': k * 0.9, 'method': 'stub'}

    monkeypatch.setattr(protection, 'run_zone_remote_fault',
                        sem_pandapower)
    monkeypatch.setattr(protection, 'get_bus_short_circuit', falta_falsa)

    def marcas():
        d = protection.build_concise_tcc('mb0')
        return {t['name']: round(float(t['x'][0]), 1)
                for t in d['traces']
                if t.get('name') and ' - 3P' in t['name']}

    antes = marcas()
    assert antes, 'a folha não desenhou a linha de falta'
    valor['ka'] = 22.0
    solver.clear_solver_cache()
    depois = marcas()
    assert depois != antes
    assert all(depois[k] > antes[k] for k in antes)


# ----------------------------------------------------------------------
# A seta da folha de motor é o curto na barra do equipamento
# ----------------------------------------------------------------------
# Antes a folha desenhava duas setas com a corrente PASSANTE pelo relé,
# que exclui o motor protegido — ele não alimenta um curto atrás do seu
# próprio cabo. O efeito colateral é que elas não se mexiam quando a
# placa do motor mudava. Hoje a folha desenha uma seta só, o curto na
# barra do equipamento, que é o que acompanha o estudo. Os dois números
# da proteção continuam calculados e saem escritos na nota.

def _fonte_de_falta(monkeypatch, passante_ka, contribuicao_ka):
    def zona(zone_id, case):
        k = passante_ka if case == 'max' else passante_ka * 0.75
        return {'3f_ka': k, 'll_ka': k * 0.75, 'lg_ka': k * 0.5,
                'llg_ka': k * 0.9, 'method': 'stub'}

    def barra(bus, case):
        k = passante_ka + (contribuicao_ka if case == 'max' else 0.0)
        return {'bus': bus, '3f_ka': k, 'll_ka': k * 0.75, 'lg_ka': k * 0.5,
                'llg_ka': k * 0.9, 'method': 'stub'}

    monkeypatch.setattr(protection, 'run_zone_remote_fault', zona)
    monkeypatch.setattr(protection, 'get_bus_short_circuit', barra)


def _setas(view):
    d = protection.build_concise_tcc(view)
    return {t['name']: round(float(t['x'][0]), 1)
            for t in d['traces'] if t.get('arrow')}


def test_folha_de_motor_tem_uma_seta_so_na_barra(monkeypatch):
    _fonte_de_falta(monkeypatch, 8.945, 6.040)
    assert list(_setas('mb0')) == ['Barra6 - 3P']
    assert list(_setas('mb6')) == ['Barra4 - 3P']


def test_a_seta_da_barra_anda_quando_o_motor_muda(monkeypatch):
    _fonte_de_falta(monkeypatch, 8.945, 6.040)
    antes = _setas('mb0')['Barra6 - 3P']
    _fonte_de_falta(monkeypatch, 8.945, 8.660)
    depois = _setas('mb0')['Barra6 - 3P']
    assert depois > antes


def test_a_seta_e_a_falta_total_da_barra(monkeypatch):
    """Inclui o motor protegido — é esse o ponto da troca."""
    _fonte_de_falta(monkeypatch, 8.945, 6.040)
    d = protection.build_concise_tcc('mb0')
    seta = next(t for t in d['traces'] if t.get('name') == 'Barra6 - 3P')
    assert seta['bus'] == 'Barra6' and seta['case'] == 'max'
    assert abs(float(seta['ka']) - (8.945 + 6.040)) < 1e-9


def test_as_folhas_sem_motor_nao_mudaram(monkeypatch):
    _fonte_de_falta(monkeypatch, 8.945, 6.040)
    assert 'Barra5 - 3P' in _setas('t1')
    assert 'Barra5 - LL' in _setas('t1')
    assert _setas('general')


def test_a_nota_guarda_os_numeros_que_sairam_do_desenho(monkeypatch):
    """A passante e o mínimo saíram da folha; não podem sumir do estudo."""
    _fonte_de_falta(monkeypatch, 8.945, 6.040)
    nota = next((n for n in protection.build_concise_tcc('mb0')['notes']
                 if n.startswith('Barra6 - 3P =')), None)
    assert nota
    assert '14,985 kA' in nota          # falta total da barra
    assert '8,945 kA' in nota           # passante pelo Relé11
    assert 'Sensibilidade' in nota
    assert 'M-B-0' in nota and 'Relé11' in nota
