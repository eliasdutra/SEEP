import math
from core.data import default_model, enrich_model


def test_reduced_physical_model():
    m = enrich_model(default_model())
    # V30: barras renumeradas em sequência, segundo gerador (GE2) e dois motores
    # espelhados do M-B-0 nos terminais novos de 6,6 kV.
    assert [b['name'] for b in m['buses']] == ['Barra1','Barra2','Barra3','Barra4',
                                               'Barra5','Barra6','Barra7','Barra8']
    assert {g['name'] for g in m['generators']} == {'GE1','GE2'}
    assert all(g.get('in_service') is True for g in m['generators'])
    # O nome da exportação do ETAP continua registrado, para rastreabilidade.
    assert {b['name']: b.get('etap_name') for b in m['buses']} == {
        'Barra1': 'Bus01', 'Barra2': None, 'Barra3': 'Bus1',
        'Barra4': 'Bus10', 'Barra5': 'Bus2', 'Barra6': 'Bus4',
        'Barra7': None, 'Barra8': None}
    assert len(m['transformers']) == 1
    assert {c['name'] for c in m['cables']} == {'Cabo1','Cabo2','Cabo3','Cabo4','Cabo5','Cabo8'}
    assert {c['name']: c.get('etap_name') for c in m['cables']} == {
        'Cabo1': 'Cable1', 'Cabo2': 'Cable2', 'Cabo3': None,
        'Cabo4': None, 'Cabo5': None, 'Cabo8': 'Cable8'}
    assert {x['name'] for x in m['motors']} == {'M-B-0','M-B-1','M-B-2','M-B-6'}
    assert {z['relay'] for z in m['zones']} == {'Relé1','Relé2','Relé3','Relé4','Relé5',
                                                'Relé10','Relé11','Relé12'}
    # Cada zona referencia um TC e um disjuntor que existem de fato no modelo.
    assert {z['ct'] for z in m['zones']} <= {c['name'] for c in m['cts']}
    djs = {s['breaker'] for s in m['switchgear']}
    assert {z['breaker'] for z in m['zones'] if z['breaker']} <= djs
    assert len(djs) == len(m['switchgear'])


def test_motores_novos_sao_copias_do_mb0_e_entram_desligados():
    """M-B-1 e M-B-2 têm que ser o M-B-0 em outro terminal, e nada além disso.

    Se alguém editar o M-B-0 (placa, impedância, curva térmica) sem replicar nos
    espelhos, a demonstração de aula deixa de comparar iguais com iguais — este
    teste é que segura isso.
    """
    m = enrich_model(default_model())
    por_nome = {x['name']: x for x in m['motors']}
    assert por_nome['M-B-0']['in_service'] is True
    assert por_nome['M-B-6']['in_service'] is True
    ignorar = {'name', 'bus', 'in_service', 'source', 'thermal_points_source'}
    for espelho in ('M-B-1', 'M-B-2'):
        alvo = por_nome[espelho]
        assert alvo['in_service'] is False
        assert alvo['kv'] == 6.6
        chaves = (set(por_nome['M-B-0']) | set(alvo)) - ignorar
        assert all(por_nome['M-B-0'].get(k) == alvo.get(k) for k in chaves)
    # Cada motor no seu próprio terminal, um terminal por motor.
    barras = [x['bus'] for x in m['motors']]
    assert len(barras) == len(set(barras))


def test_current_etap_motor_and_t1_data():
    m = enrich_model(default_model())
    mb0 = next(x for x in m['motors'] if x['name']=='M-B-0')
    mb6 = next(x for x in m['motors'] if x['name']=='M-B-6')
    t1 = m['transformers'][0]
    # 'amp' passou a ser DERIVADO de kW/kV/fp/rendimento (ver enrich_model),
    # não mais copiado arredondado da planilha. Confere com o valor que o
    # ETAP exibe dentro da precisão dos dados de placa de onde sai: fp e
    # rendimento vêm com duas decimais, o que já move a terceira casa da
    # corrente. Daí 0,1 % em vez de igualdade exata.
    #   M-B-0: derivado 154,415 A · ETAP 154,40 A
    #   M-B-6: derivado 284,319 A · ETAP 284,44 A
    assert math.isclose(mb0['amp'], 154.40, rel_tol=1e-3)
    assert mb0['lrc_percent'] == 650.0 and mb0['start_time_s'] == 1.0
    assert mb0['stall_hot_s'] == 10.0 and mb0['stall_cold_s'] == 30.0
    assert math.isclose(mb6['amp'], 284.44, rel_tol=1e-3)
    assert mb6['lrc_percent'] == 650.0
    assert t1['sn_mva'] == 11.0 and t1['vk_percent'] == 8.0
    assert t1['inrush_pu'] == 8.0 and math.isclose(t1['inrush_time_s'], 0.0167, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(t1['inrush_primary_a'], 3681.7, rel_tol=0, abs_tol=1e-6)


def test_etap_seed_relay_settings_exact():
    """Transcrição dos OC1 do ETAP: pickup 51, TMS, pickup 50 e delay 50.

    O TC saiu de ``etap_settings`` na V29: virou equipamento próprio, em
    ``model['cts']``, para poder ser editado na tela "Modelo físico". Por
    isso a relação do TC é conferida no teste seguinte, lendo de lá.
    """
    zones = {z['relay']: z for z in default_model()['zones']}
    expected = {
        'Relé1': (372, 1.175, 14712, 0.01),
        'Relé10': (320, 1.0, 14000, 0.0),
        'Relé12': (340, 0.575, 9800, 0.0),
        'Relé11': (230, 0.325, 7760, 0.0),
        'Relé3': (315, 0.8, 6990, 0.0),
    }
    for relay, vals in expected.items():
        e = zones[relay]['etap_settings']
        got = (e['pickup_51_a'], e['time_setting'],
               e['pickup_50_a'], e['delay_50_s'])
        assert got == vals, relay
        assert e['curve'] == 'IEC_EI'


def test_cada_zona_aponta_para_um_tc_cadastrado():
    """A relação do TC vem do cadastro de TC, e a zona tem de achá-lo.

    ATENÇÃO — um valor a conferir na folha do ETAP: a transcrição da V20
    registrava 1000/5 no Relé10, e o cadastro de TC criado na V29 traz
    ``TC-Relé10`` como 1500/5. Isso não desloca nenhuma curva do TCC,
    porque os pickups são guardados em amperes primários, mas muda os
    valores de secundário mostrados na tela "Cálculo 51". Este teste
    trava a consistência interna; qual dos dois números é o certo é
    decisão de quem tem a folha na mão.
    """
    model = default_model()
    cts = {c['name']: c for c in model['cts']}
    for zone in model['zones']:
        nome = zone.get('ct')
        assert nome, zone['id']
        assert nome in cts, f"{zone['id']} aponta para TC inexistente: {nome}"
        ct = cts[nome]
        assert float(ct['primary_a']) > 0 and float(ct['secondary_a']) in (1.0, 5.0)
