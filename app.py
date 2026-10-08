"""Camada web do SEEP: servidor Flask e API REST.

Posição no pipeline do estudo:

    data.py  ->  storage.py  ->  network.py  ->  solver.py  ->
    protection.py  ->  **app.py**

É a borda do sistema. Não calcula nada: recebe requisição HTTP, chama a
função do núcleo, devolve JSON. Toda a engenharia está em ``core/``;
aqui só existem rotas, validação de entrada e tradução de exceção em
código de status.

Essa fina camada é o que permite três coisas ao mesmo tempo: a interface
gráfica funcionar no navegador, o estudo ser automatizado por script sem
abrir tela nenhuma, e o núcleo ser testado sem subir servidor.

Famílias de rotas
-----------------
``/api/network``, ``/api/model``, ``/api/summary``
    O caso físico e o resumo do estudo.
``/api/powerflow``, ``/api/shortcircuit``
    Resultados elétricos, servidos do cache do solver.
``/api/equipment/<categoria>/<nome>``
    Edição de parâmetro de equipamento. ``GET`` lê, ``POST`` grava.
``/api/protection/<zona>``, ``/api/zones``, ``/api/relay-library``
    Ajustes 50/51 e a biblioteca de relés.
``/api/tcc/...``, ``/api/tcc-master``, ``/api/tcc-concise/<vista>``
    Coordenogramas, por zona, por caminho e na folha estilo ETAP STAR.
``/api/expert``, ``/api/coordination-review/<caminho>``
    Sugestão de ajustes e verificação de coordenação em cascata.

Detalhe de implementação que vale explicar
------------------------------------------
Salvar um equipamento elétrico (gerador, trafo, cabo, motor) invalida o
cache e refaz o cálculo antes de responder, porque a rede do pandapower
mudou. Salvar um TC não: é metrologia de proteção, não entra na rede.
Essa distinção evita disparar dezenas de chamadas pesadas de
curto-circuito à toa.

Execução
--------
``python app.py`` sobe o servidor em 127.0.0.1:5000 e abre o navegador.
É aplicação local de engenharia, não serviço exposto na rede.
"""
from __future__ import annotations
import sys
import threading
import webbrowser
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from core.data import (
    EQUIPMENT_FIELD_SCHEMA,
    default_model,
    enrich_model,
    find_equipment,
    validate_equipment_payload,
)
from core.storage import (
    delete_equipment_override,
    export_all_settings,
    get_equipment_override,
    get_model,
    list_equipment_overrides,
    save_equipment_override,
)
from core.protection import (
    build_tcc,
    build_path_tcc,
    build_master_tcc,
    build_concise_tcc,
    protection_context,
    breaker_duty_for_zone,
    manual_51,
    paths_payload,
    preview_zone_settings,
    review_coordination,
    relay_library_payload,
    reset_settings,
    settings_for_zone,
    suggest_all_phase_settings,
    suggest_phase_settings,
    update_settings,
    zones_payload,
)
from core.solver import clear_solver_cache, run_power_flow, run_short_circuit, run_phase_min_validated, study_summary, solver_cache_status, run_zone_remote_fault

# Quando empacotado com PyInstaller (modo --onedir), sys.frozen fica
# True e __file__ não aponta mais pra pasta certa dos templates/static —
# usa a pasta do executável nesse caso. Rodando normal (python app.py),
# continua igual.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config["JSON_SORT_KEYS"] = False
_cache = {}


def cached(key, fn):
    """Objetivo: memória de resposta do processo, por chave.

    Guarda o resultado da primeira chamada e devolve o mesmo objeto
    depois. É o cache de *apresentação*, separado do cache elétrico do
    solver: aqui mora o que já foi serializado para a tela.

    Limpo por ``invalidate`` sempre que o modelo físico muda.
    """
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]


def invalidate():
    """Objetivo: esquecer tudo que foi calculado, nos dois níveis.

        _cache (respostas)  +  clear_solver_cache (elétrico)

    Chamado quando o modelo físico muda. Os dois precisam cair juntos:
    um cache de resposta que sobrevive à mudança da rede é a tela
    mostrando um número que já não corresponde ao caso.
    """
    _cache.clear()
    clear_solver_cache()


def model_payload():
    """Objetivo: o modelo efetivo, com as grandezas derivadas.

        storage.get_model (fábrica + edições)  ->  data.enrich_model

    É o modelo que o resto do programa deve ler.
    """
    return enrich_model(get_model())


@app.get("/")
def index():
    """Objetivo: servir a página única da aplicação.

    Passa o ``BUILD_TAG`` para o carimbo do rodapé. Toda tela e todo
    gráfico exportado saem identificados pela versão que os gerou, para
    o estudo poder ser conferido depois.
    """
    from core.data import BUILD_TAG
    return render_template("index.html", build_tag=BUILD_TAG)


@app.get("/api/network")
def api_network():
    """Objetivo: o modelo com as grandezas derivadas.

        GET /api/network  ->  get_model  ->  enrich_model  ->  JSON

    É o que o unifilar e as fichas de equipamento consomem.
    """
    return jsonify(model_payload())


@app.get("/api/model")
def api_model():
    """Objetivo: o modelo cru, sem nenhuma derivada.

        GET /api/model  ->  get_model  ->  JSON

    Diferente de ``/api/network``: aqui saem só os dados de placa, como
    estão guardados. Serve para separar o que é dado do que é cálculo.
    """
    return jsonify(get_model())


@app.get("/api/summary")
def api_summary():
    """Objetivo: o consolidado da tela inicial.

        GET /api/summary  ->  solver.study_summary (do cache)

    Convergência do fluxo, menor tensão, maior corrente de curto e
    estado dos dois casos da norma, mais o estado do cache elétrico.
    Abrir a tela inicial não dispara cálculo novo.
    """
    payload = dict(cached("summary", study_summary))
    payload["cache"] = solver_cache_status()
    return jsonify(payload)


def _recalculate_electrical() -> dict:
    """Recalcula o estudo elétrico completo uma única vez.

    Usado tanto pelo botão "Recalcular sistema" quanto pelo
    salvamento/reset de um equipamento (V29), já que os dois casos
    invalidam o mesmo cache elétrico e precisam repetir fluxo + curto
    MAX/MIN + pré-aquecimento.
    """
    import time
    t0 = time.perf_counter()
    invalidate()
    pf = run_power_flow()
    mx = run_short_circuit("max")
    mn = run_short_circuit("min")
    # Pré-aquece somente as faltas remotas usadas pelos dois TCCs de
    # motor. Assim, depois do recálculo elétrico, trocar pickup/TMS e
    # abrir TCC não dispara novos solves do Pandapower.
    warm_errors = []
    try:
        model = model_payload()
        for zone in model.get("zones", []):
            if zone.get("motor"):
                for case in ("max", "min"):
                    try:
                        run_zone_remote_fault(zone["id"], case)
                    except Exception as exc:
                        warm_errors.append(f"{zone['id']} {case}: {exc}")
    except Exception as exc:
        warm_errors.append(str(exc))
    summary = study_summary()
    _cache["powerflow"] = pf
    _cache["sc_max"] = mx
    _cache["sc_min"] = mn
    _cache["summary"] = summary
    return {"ok": True, "elapsed_s": time.perf_counter() - t0, "cache": solver_cache_status(), "summary": summary, "warm_errors": warm_errors}


@app.post("/api/recalculate")
def api_recalculate():
    """Recalcula o estudo elétrico completo uma única vez.

    Alterações de proteção não passam por este endpoint. O usuário usa
    esta ação somente quando deseja invalidar/reexecutar Pandapower.
    """
    return jsonify(_recalculate_electrical())


@app.get("/api/equipment-schema")
def api_equipment_schema():
    """Objetivo: dizer quais campos o front-end pode editar.

    GET /api/equipment-schema  ->  EQUIPMENT_FIELD_SCHEMA

    Rótulo, unidade, tipo e faixa de cada campo de gerador, trafo,
    cabo, motor e TC. É a mesma lista que gera o formulário e a que
    valida o que volta dele.
    """
    return jsonify(EQUIPMENT_FIELD_SCHEMA)


@app.get("/api/equipment-overrides")
def api_equipment_overrides():
    """Objetivo: dizer quais equipamentos estão editados.

    GET /api/equipment-overrides  ->  list_equipment_overrides

    É o que acende o selo "editado" na tela.
    """
    return jsonify(list_equipment_overrides())


@app.get("/api/equipment/<category>/<name>")
def api_equipment_get(category, name):
    """Objetivo: a ficha de um equipamento, para o formulário.

        GET /api/equipment/<categoria>/<nome>

    Devolve os valores atuais, quais campos são editáveis e se o item
    está editado em relação ao caso ETAP. É esse último campo que acende
    o selo "editado" na tela.

    404 quando o equipamento não existe; 400 quando a categoria não é
    editável.
    """
    if category not in EQUIPMENT_FIELD_SCHEMA:
        return jsonify({"error": "Categoria não editável"}), 400
    item = find_equipment(get_model(), category, name)
    if item is None:
        return jsonify({"error": "Equipamento não encontrado"}), 404
    return jsonify({
        "values": item,
        "editable_fields": [f["key"] for f in EQUIPMENT_FIELD_SCHEMA[category]],
        "overridden": get_equipment_override(category, name) is not None,
    })


@app.post("/api/equipment/<category>/<name>")
def api_equipment_save(category, name):
    """Salva parâmetros editados de um equipamento.

    Para equipamento elétrico de verdade (motor, trafo, cabo, gerador),
    o modelo do Pandapower mudou, então o cache é invalidado e refeito
    antes de responder. TCs são exceção: são só metrologia/proteção, não
    entram na rede do Pandapower — salvar um TC não deve disparar a
    recalculada pesada (~19 chamadas de curto-circuito), só invalidar o
    cache de configurações.
    """
    if category not in EQUIPMENT_FIELD_SCHEMA:
        return jsonify({"error": "Categoria não editável"}), 400
    if find_equipment(default_model(), category, name) is None:
        return jsonify({"error": "Equipamento não encontrado"}), 404
    try:
        clean = validate_equipment_payload(category, request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    existing = get_equipment_override(category, name) or {}
    existing.update(clean)
    save_equipment_override(category, name, existing)
    if category == "cts":
        _cache.clear()
        return jsonify({"ok": True, "values": existing, "recalculation": None})
    recalculation = _recalculate_electrical()
    return jsonify({"ok": True, "values": existing, "recalculation": recalculation})


@app.post("/api/equipment/<category>/<name>/reset")
def api_equipment_reset(category, name):
    """Descarta as edições do equipamento (volta ao caso ETAP original).

    TCs não entram na rede do Pandapower (ver nota em
    api_equipment_save) — resetar um TC não precisa da recalculada
    pesada.
    """
    if category not in EQUIPMENT_FIELD_SCHEMA:
        return jsonify({"error": "Categoria não editável"}), 400
    if find_equipment(default_model(), category, name) is None:
        return jsonify({"error": "Equipamento não encontrado"}), 404
    delete_equipment_override(category, name)
    if category == "cts":
        _cache.clear()
        return jsonify({"ok": True, "recalculation": None})
    recalculation = _recalculate_electrical()
    return jsonify({"ok": True, "recalculation": recalculation})


@app.get("/api/cache-status")
def api_cache_status():
    """Objetivo: dizer o que está guardado no cache agora.

        GET /api/cache-status  ->  solver.solver_cache_status

    Serve à tela de diagnóstico, onde o efeito do cache pode ser medido
    ligando e desligando, em vez de apenas explicado.
    """
    return jsonify(solver_cache_status())


@app.get("/api/powerflow")
def api_powerflow():
    """Objetivo: tensões por barra e carregamento dos ramos.

        GET /api/powerflow  ->  cache  ->  solver.run_power_flow
    """
    return jsonify(cached("powerflow", run_power_flow))


@app.get("/api/shortcircuit")
def api_shortcircuit():
    """Objetivo: a tabela de curto-circuito de um caso da norma.

        GET /api/shortcircuit?case=max|min  ->  run_short_circuit

    Qualquer valor diferente de ``min`` cai em ``max``: um parâmetro
    digitado errado não deve devolver em silêncio o caso mínimo, que é o
    mais otimista para dever de interrupção.
    """
    case = "min" if request.args.get("case", "max").lower() == "min" else "max"
    return jsonify(cached(f"sc_{case}", lambda: run_short_circuit(case)))

@app.get("/api/phase-min-validated")
def api_phase_min_validated():
    """Objetivo: as faltas de fase mínimas, conferidas à parte.

        GET /api/phase-min-validated  ->  run_phase_min_validated

    Segundo número de referência para a coordenação de fase, calculado
    pelo caminho nodal de sequência, independente do Pandapower.
    Divergência entre os dois aparece, em vez de passar despercebida.
    """
    return jsonify(cached("phase_min_validated", run_phase_min_validated))


@app.get("/api/zones")
def api_zones():
    """Objetivo: as zonas de proteção com equipamentos e ajustes.

        GET /api/zones  ->  protection.zones_payload
    """
    return jsonify({"zones": zones_payload()})


@app.get("/api/tcc/<zone_id>")
def api_tcc(zone_id):
    """Objetivo: o coordenograma de uma zona só.

        GET /api/tcc/<zona>?mode=phase|neutral  ->  build_tcc
        ->  traços  ->  Plotly
    """
    try:
        mode = request.args.get("mode", "phase")
        return jsonify(build_tcc(zone_id, mode))
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/breaker-duty/<zone_id>")
def api_breaker_duty(zone_id):
    """Objetivo: verificar se o disjuntor interrompe a pior falta.

        GET /api/breaker-duty/<zona>  ->  breaker_duty_for_zone

    Compara a maior corrente de falta que pode aparecer no disjuntor com
    a corrente nominal de interrupção em curto-circuito dele — o caso é
    de média tensão, então a referência é a IEC 62271-100.
    """
    try:
        return jsonify(breaker_duty_for_zone(zone_id))
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/expert/<zone_id>")
def api_expert_zone(zone_id):
    """Objetivo: sugerir pickup e TMS de fase para uma zona.

        GET /api/expert/<zona>  ->  suggest_phase_settings

    Propõe; não grava. O ajuste só muda quando o usuário salva.
    """
    try:
        return jsonify(suggest_phase_settings(zone_id))
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/expert")
def api_expert_all():
    """Objetivo: rodar o especialista em todas as zonas de uma vez.

        GET /api/expert  ->  suggest_all_phase_settings

    Zona com erro volta com o motivo, em vez de derrubar a resposta.
    """
    try:
        return jsonify(suggest_all_phase_settings())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/manual51/<zone_id>")
def api_manual51(zone_id):
    """Objetivo: mostrar o cálculo do estágio 51 passo a passo.

        GET /api/manual51/<zona>?current=  ->  manual_51

    Sem ``current``, usa o LRC do motor ou 2 × pickup. Material de
    apoio — a tela que consome esta rota está oculta no menu.
    """
    try:
        current = request.args.get("current")
        mode = request.args.get("mode", "phase")
        return jsonify(manual_51(zone_id, current, mode))
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/protection/<zone_id>", methods=["GET", "POST"])
def api_protection(zone_id):
    """Objetivo: ler e salvar os ajustes de uma zona.

        GET   /api/protection/<zona>  ->  settings_for_zone
        POST  /api/protection/<zona>  ->  update_settings

    Salvar ajuste **não** recalcula o Pandapower: mudou a proteção, não
    a rede. A resposta devolve o estado do cache elétrico, para a tela
    poder mostrar que ele continua válido.
    """
    if request.method == "GET":
        try:
            return jsonify(settings_for_zone(zone_id))
        except KeyError:
            return jsonify({"error": "Zona não encontrada"}), 404
    try:
        saved = update_settings(zone_id, request.get_json(silent=True) or {})
        # V27: salvar pickup/TMS/50 não recalcula Pandapower e não monta
        # um TCC que o frontend nem usa. O gráfico será montado sob
        # demanda com os resultados elétricos já cacheados.
        return jsonify({"ok": True, "settings": saved, "electrical_cache": solver_cache_status()})
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/protection/<zone_id>/reset")
def api_protection_reset(zone_id):
    """Objetivo: devolver a zona ao ajuste preliminar.

        POST /api/protection/<zona>/reset  ->  reset_settings

    Descarta o que foi salvo e grava de novo o que o programa propõe.
    """
    try:
        settings = reset_settings(zone_id)
        return jsonify({"ok": True, "settings": settings, "electrical_cache": solver_cache_status()})
    except KeyError:
        return jsonify({"error": "Zona não encontrada"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/protection/<zone_id>/auto")
def api_protection_auto_compat(zone_id):
    """Compatibilidade V9: /auto só restaura o ajuste preliminar."""
    return api_protection_reset(zone_id)


@app.get("/api/protection-context/<zone_id>")
def api_protection_context(zone_id):
    """Objetivo: reunir o que o ajuste precisa ter em vista.

        GET /api/protection-context/<zona>  ->  protection_context

    Equipamento protegido, correntes de falta da zona, TC e relés
    vizinhos — o contexto que justifica o ajuste.
    """
    try:
        return jsonify(protection_context(zone_id))
    except KeyError:
        return jsonify({"error": "Relé/zona não encontrado"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/paths")
def api_paths():
    """Objetivo: os caminhos de coordenação cadastrados.

        GET /api/paths  ->  protection.paths_payload
    """
    return jsonify({"paths": paths_payload()})


@app.get("/api/relay-library")
def api_relay_library():
    """Objetivo: as curvas normalizadas e os modelos de relé.

        GET /api/relay-library  ->  relay_library_payload
    """
    return jsonify(relay_library_payload())


@app.get("/api/tcc-path/<path_id>")
def api_tcc_path(path_id):
    """Objetivo: um coordenograma com os relés do caminho juntos.

        GET /api/tcc-path/<caminho>?reference_kv=  ->  build_path_tcc

    Sem ``reference_kv`` usa a tensão de referência do caminho.
    """
    try:
        mode = request.args.get("mode", "phase")
        reference_kv = request.args.get("reference_kv")
        return jsonify(build_path_tcc(path_id, mode, reference_kv))
    except KeyError:
        return jsonify({"error": "Caminho não encontrado"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/tcc-master")
def api_tcc_master():
    """Objetivo: todos os relés do sistema num gráfico só.

        GET /api/tcc-master?mode=&reference_kv=  ->  build_master_tcc

    Base padrão 6,6 kV. Motor fora de serviço não desenha curva: o
    gráfico mostra a configuração que está rodando, não o cadastro.
    """
    try:
        mode = request.args.get("mode", "phase")
        reference_kv = request.args.get("reference_kv", 6.6)
        return jsonify(build_master_tcc(mode, reference_kv))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.get("/api/tcc-concise/<view>")
def api_tcc_concise(view):
    """Objetivo: as quatro folhas de coordenograma do estudo.

        GET /api/tcc-concise/<folha>  ->  build_concise_tcc

    ``folha`` é ``mb0``, ``mb6``, ``t1`` ou ``general``.
    """
    try:
        return jsonify(build_concise_tcc(view))
    except KeyError:
        return jsonify({"error": "Coordenograma não encontrado"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.get("/api/coordination-review/<path_id>")
def api_coordination_review(path_id):
    """Objetivo: a verificação em cascata de um caminho.

        GET /api/coordination-review/<caminho>  ->  review_coordination

    Casos 1, 2 e 3: cada par principal/retaguarda com a sua margem, e o
    motivo quando reprova ou fica pendente.
    """
    try:
        return jsonify(review_coordination(path_id))
    except KeyError:
        return jsonify({"error": "Caminho não encontrado"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/tcc-concise/<view>/preview")
def api_tcc_concise_preview(view):
    """Mesma folha, montada com ajustes que o usuário ainda não salvou.

    Corpo da requisição::

        {"overrides": {"Z-R11": {"phase_stage1_pickup_a": 240}}}

    Nada é gravado: os ajustes valem só durante a montagem desta
    resposta.
    """
    body = request.get_json(silent=True) or {}
    overrides = body.get("overrides") or {}
    if not isinstance(overrides, dict):
        return jsonify({"error": "overrides deve ser um objeto por zona"}), 400
    limpo = {str(z): (p or {}) for z, p in overrides.items() if isinstance(p, dict)}
    try:
        with preview_zone_settings(limpo):
            payload = build_concise_tcc(view)
        payload["preview"] = True
        return jsonify(payload)
    except KeyError:
        return jsonify({"error": "Coordenograma não encontrado"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/settings/export")
def api_settings_export():
    """Objetivo: despejar todos os ajustes salvos, versionados.

        GET /api/settings/export  ->  storage.export_all_settings

    Para anexar ao estudo ou reaplicar em outra instalação.
    """
    return jsonify({"version": "V01", "settings": export_all_settings()})


if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
