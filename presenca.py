"""Contagem anônima de audiência e a página escondida /sensor.

Cada navegador guarda um código aleatório (localStorage) e o envia ao abrir o painel. Não há nome,
IP nem qualquer dado pessoal: só o código, se a aba está visível e o modo (celular/computador).
Enquanto a aba está aberta, o painel roda a cada 5 s no servidor e isso serve de "ping".

  agora     aparelhos com ping nos últimos 20 s e aba visível
  no total  aparelhos diferentes desde o início da contagem
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

JANELA_S = 20                 # sem ping há mais que isso = saiu
AMOSTRA_S = 30                # um ponto do gráfico a cada 30 s
ARQUIVO = Path(__file__).parent / ".presenca.json"   # sobrevive a recarregamentos do app (não vai para o git)
FUSO = ZoneInfo("America/Sao_Paulo")      # o servidor do Streamlit Cloud fica em UTC


@st.cache_resource
def _estado() -> dict:
    e = {"dev": {}, "serie": [], "pico": (0, 0.0), "lock": threading.Lock(), "salvo": 0.0, "amostra": 0.0}
    try:
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        e["dev"] = {k: {**v, "ultimo": 0.0} for k, v in dados.get("dev", {}).items()}
        e["serie"] = [tuple(x) for x in dados.get("serie", [])][-3000:]
        e["pico"] = tuple(dados.get("pico", (0, 0.0)))
    except Exception:  # noqa: BLE001  (primeira vez, ou arquivo ilegível)
        pass
    return e


def _ativos(e: dict, agora: float) -> list[dict]:
    return [d for d in e["dev"].values() if agora - d.get("ultimo", 0) <= JANELA_S and d.get("visivel", True)]


def _salvar(e: dict, agora: float):
    if agora - e["salvo"] < 60:
        return
    e["salvo"] = agora
    try:
        corpo = {"dev": {k: {kk: vv for kk, vv in v.items() if kk != "ultimo"} for k, v in e["dev"].items()},
                 "serie": e["serie"][-3000:], "pico": e["pico"]}
        tmp = ARQUIVO.with_suffix(".tmp")
        tmp.write_text(json.dumps(corpo), encoding="utf-8")
        tmp.replace(ARQUIVO)
    except Exception:  # noqa: BLE001  (disco só de leitura: segue só em memória)
        pass


def registrar(valor) -> None:
    """Chamado a cada atualização do painel com o que o navegador mandou ({id, visivel, modo})."""
    if not isinstance(valor, dict) or not valor.get("id"):
        return
    e, agora = _estado(), time.time()
    with e["lock"]:
        d = e["dev"].setdefault(str(valor["id"])[:64], {"primeiro": agora})
        d["ultimo"] = agora
        d["visivel"] = bool(valor.get("visivel", True))
        if valor.get("modo") in ("pc", "mobile"):
            d["modo"] = valor["modo"]
        _amostrar(e, agora)
        _salvar(e, agora)


def _amostrar(e: dict, agora: float):
    if agora - e["amostra"] < AMOSTRA_S:
        return
    e["amostra"] = agora
    n = len(_ativos(e, agora))
    e["serie"].append((agora, n))
    if n >= e["pico"][0]:
        e["pico"] = (n, agora)


def resumo() -> dict:
    e, agora = _estado(), time.time()
    with e["lock"]:
        _amostrar(e, agora)
        at = _ativos(e, agora)
        return {
            "agora": len(at), "agora_cel": sum(d.get("modo") == "mobile" for d in at),
            "agora_pc": sum(d.get("modo") == "pc" for d in at),
            "total": len(e["dev"]), "total_cel": sum(d.get("modo") == "mobile" for d in e["dev"].values()),
            "total_pc": sum(d.get("modo") == "pc" for d in e["dev"].values()),
            "abertas_ocultas": sum(1 for d in e["dev"].values()
                                   if agora - d.get("ultimo", 0) <= JANELA_S and not d.get("visivel", True)),
            "pico": e["pico"], "serie": list(e["serie"][-720:]),
        }


# ───────────────────────── PÁGINA /sensor ─────────────────────────
CSS = """<style>
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"]{display:none!important;}
html, body, .stApp, [data-testid="stAppViewContainer"]{background:#0E100F!important;}
.block-container, [data-testid="stMainBlockContainer"]{padding:4vh 4vw!important;max-width:1100px!important;}
[data-stale="true"], .stale-element{opacity:1!important;filter:none!important;transition:none!important;}
.sn{font-family:'Archivo',system-ui,sans-serif;color:#FFFCE1;font-variant-numeric:tabular-nums;}
.sn-topo{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #2A2C28;padding-bottom:12px;}
.sn-topo b{font-weight:800;font-size:22px;} .sn-topo span{color:#A6A48F;font-size:14px;}
.sn-grade{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:28px;}
.sn-grade > div{padding:8px 24px 8px 0;} .sn-grade > div + div{border-left:1px solid #2A2C28;padding-left:24px;}
.sn-num{font-size:clamp(64px,13vw,150px);font-weight:850;line-height:.9;letter-spacing:-.03em;}
.sn-rot{color:#A6A48F;font-size:16px;margin-top:10px;}
.sn-div{display:flex;gap:22px;margin-top:14px;font-size:15px;color:#A6A48F;} .sn-div b{color:#FFFCE1;font-weight:700;}
.sn-graf{margin-top:40px;border-top:1px solid #2A2C28;padding-top:16px;}
.sn-graf p{margin:0 0 10px;color:#A6A48F;font-size:14px;}
.sn-graf svg{width:100%;height:180px;display:block;}
.sn-nota{margin-top:28px;color:#A6A48F;font-size:13px;line-height:1.5;max-width:70ch;}
@media (max-width:640px){ .sn-grade{grid-template-columns:1fr;} .sn-grade > div + div{border-left:0;border-top:1px solid #2A2C28;padding:20px 0 0;margin-top:20px;} }
</style>"""


def _fi(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _grafico(serie: list) -> str:
    if len(serie) < 2:
        return '<svg viewBox="0 0 1000 180"><text x="500" y="95" text-anchor="middle" fill="#A6A48F" font-size="16">O gráfico se forma com o tempo</text></svg>'
    t0, t1 = serie[0][0], serie[-1][0]
    top = max(1, max(n for _, n in serie))
    X = lambda t: 40 + 950 * (t - t0) / max(1, t1 - t0)          # noqa: E731
    Y = lambda n: 165 - 150 * n / top                            # noqa: E731
    pts = " ".join(f"{X(t):.1f},{Y(n):.1f}" for t, n in serie)
    area = f"40,165 {pts} {X(t1):.1f},165"
    hora = lambda t: datetime.fromtimestamp(t, FUSO).strftime("%Hh%M")   # noqa: E731
    return (f'<svg viewBox="0 0 1000 180" preserveAspectRatio="none">'
            f'<line x1="40" x2="990" y1="165" y2="165" stroke="#2A2C28"/>'
            f'<polygon points="{area}" fill="rgba(132,117,190,.25)"/>'
            f'<polyline points="{pts}" fill="none" stroke="#8475BE" stroke-width="2.5" vector-effect="non-scaling-stroke"/>'
            f'<text x="34" y="20" text-anchor="end" fill="#A6A48F" font-size="13">{top}</text>'
            f'<text x="40" y="180" fill="#A6A48F" font-size="13">{hora(t0)}</text>'
            f'<text x="990" y="180" text-anchor="end" fill="#A6A48F" font-size="13">{hora(t1)}</text></svg>')


def pagina():
    st.markdown(CSS, unsafe_allow_html=True)

    @st.fragment(run_every=10)
    def ao_vivo():
        tz = FUSO
        r = resumo()
        pico_n, pico_t = r["pico"]
        serie = [(t, n) for t, n in r["serie"]]
        hora_pico = datetime.fromtimestamp(pico_t, tz).strftime("%Hh%M") if pico_t else "—"
        agora = datetime.now(tz).strftime("%H:%M:%S")
        st.markdown(f"""<div class="sn">
  <div class="sn-topo"><b>Sensor</b><span>atualizado às {agora}, a cada 10 s</span></div>
  <div class="sn-grade">
    <div><div class="sn-num">{_fi(r["agora"])}</div><div class="sn-rot">aparelhos assistindo agora</div>
      <div class="sn-div"><span><b>{_fi(r["agora_cel"])}</b> no celular</span><span><b>{_fi(r["agora_pc"])}</b> no computador ou TV</span></div></div>
    <div><div class="sn-num">{_fi(r["total"])}</div><div class="sn-rot">aparelhos diferentes no total</div>
      <div class="sn-div"><span><b>{_fi(r["total_cel"])}</b> no celular</span><span><b>{_fi(r["total_pc"])}</b> no computador ou TV</span></div></div>
  </div>
  <div class="sn-graf"><p>Aparelhos assistindo ao longo do tempo · pico de <b style="color:#FFFCE1">{_fi(pico_n)}</b> às {hora_pico}</p>{_grafico(serie)}</div>
  <p class="sn-nota">"Agora" conta quem está com o painel aberto e visível na tela (último sinal há menos de {JANELA_S} s).
  Abas abertas em segundo plano não entram: são {_fi(r["abertas_ocultas"])} neste momento. Cada navegador conta como um aparelho;
  o mesmo celular em duas abas conta uma vez. O modo de demonstração não entra na contagem.</p>
</div>""", unsafe_allow_html=True)

    ao_vivo()
