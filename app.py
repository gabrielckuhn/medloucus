"""
Apuração 2026 — 2º turno, Presidente. Painel para TV que atualiza sozinho a cada 5 s.

  tse.py     leitura dos arquivos públicos do TSE e coletor municipal em segundo plano
  modelo.py  certeza matemática, projeção por transferência de votos, probabilidade, recortes
  demo.py    apuração fictícia coerente (município → UF → Brasil) para testar
  front/     interface (HTML/CSS/JS) carregada uma vez; recebe só os dados novos

Endereços úteis:
  ?demo=1            demonstração (&passo=40 congela num ponto; ~90 passos até 100%)
  ?aba=mapa          abre direto numa tela (geral, agora, mapa, estados, modelo); sem isso abre na Geral
  ?videos=ID1,ID2    troca as transmissões da tela Geral sem mexer no código
  ?rotacao=30        troca de tela sozinha a cada 30 s (para TV)
  ?modo=pc           pula a escolha inicial (?modo=celular abre direto a versão para celular)
  ?debug=1           mostra o que o TSE devolve
  /sensor            página escondida com quantos aparelhos estão assistindo agora e no total
O painel do 1º turno está em app_1turno.py.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
import streamlit as st
import streamlit.components.v1 as components

import modelo
import presenca
import tse
from demo import PASSOS, carregar_demo

st.set_page_config(page_title="Apuração 2026 — 2º turno", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")

_painel = components.declare_component("painel_2turno", path=str(Path(__file__).parent / "front"))

NOME_EXIBICAO = {"22": "Flávio Bolsonaro", "13": "Lula"}   # o TSE grava sem acento
# Transmissões da tela Geral (id do vídeo no YouTube). Trocar aqui, ou sem commit pelo
# endereço: ?videos=ID1,ID2
VIDEOS = [{"titulo": "SBT News ao vivo", "id": "n5pX4SW9v7k"},
          {"titulo": "CNN Brasil ao vivo", "id": "wwLxIO0zTP8"}]
Q = st.query_params
DEMO = Q.get("demo") in ("1", "true", "sim")
DEBUG = Q.get("debug") in ("1", "true", "sim")

st.markdown("""<style>
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"]{display:none!important;}
html, body, .stApp, [data-testid="stAppViewContainer"]{background:#0E100F!important;}
.block-container, [data-testid="stMainBlockContainer"]{padding:0!important;max-width:100%!important;}
[data-stale="true"], .stale-element{opacity:1!important;filter:none!important;transition:none!important;}
.st-key-tela iframe{position:fixed!important;inset:0;height:100vh!important;height:100dvh!important;width:100vw!important;border:0;display:block;}
.st-key-tela, .st-key-tela > div{gap:0!important;}
</style>""", unsafe_allow_html=True)


# ───────────────────────── HISTÓRICO DA NOITE ─────────────────────────
@st.cache_resource
def historico() -> dict:
    """Uma série por modo (real/demonstração): % do eleitorado apurado, vantagem agora e projetada."""
    return {"real": [], "demo": []}


def registrar(serie: list, ap: float, et: int, d_now: float | None, d_proj: float | None, prob: float | None):
    if serie and et < serie[-1]["et"]:            # demonstração recomeçou
        serie.clear()
    if serie and et == serie[-1]["et"]:
        serie[-1].update(dn=d_now, dp=d_proj, p=prob)
        return
    serie.append({"t": time.time(), "ap": ap, "et": et, "dn": d_now, "dp": d_proj, "p": prob})
    if len(serie) > 2000:
        del serie[::2]


# ───────────────────────── MONTAGEM DOS DADOS ─────────────────────────
def limpo(o):
    """Tipos do numpy e infinitos → JSON."""
    if isinstance(o, dict):
        return {str(k): limpo(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpo(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


@st.cache_data
def ids_geo() -> list[int]:
    with open(Path(__file__).parent / "front" / "geo.json", encoding="utf-8") as f:
        return json.load(f)["ids"]


@st.cache_data
def grupos_1turno() -> dict:
    b = modelo.base_1turno()
    v = sum(m["vec"] for m in b["mun"].values()) + b["zz"]
    return {"F": float(v[0]), "L": float(v[1]), "O": float(v[2]), "BN": float(v[3]), "A": float(v[4])}


def montar() -> dict:
    if DEMO:
        passo = float(Q["passo"]) if Q.get("passo") else (time.time() / tse.REFRESH_S) % PASSOS
        nac, ufs, votos, andamento = carregar_demo(passo)
        coleta = None
        hora = datetime.now(tse.TZ).strftime("%H:%M:%S")
    else:
        nac, ufs = tse.carregar()
        col = tse.coletor()
        votos, andamento = col.copia()
        coleta = {"municipios": len(votos), "fila": col.fila, "erro": col.erro}
        h = (nac["dados"] or {}).get("atualizado", "").split(" ")[-1]
        hora = h or datetime.now(tse.TZ).strftime("%H:%M:%S")

    sit = modelo.situacao_nacional(nac, ufs)
    proj = modelo.projetar(votos, andamento, ufs)
    rec = modelo.recortes(ufs, votos, proj)
    mapa = modelo.dados_mapa(ids_geo(), votos, andamento)

    d = (sit or {}).get("d") or nac.get("dados") or {}
    cand = None
    if d.get("cands"):
        por_num = {c["numero"]: c for c in d["cands"]}
        cand = {k: {"nome": NOME_EXIBICAO.get(n) or por_num.get(n, {}).get("nome", "—"), "votos": por_num.get(n, {}).get("votos", 0),
                    "pct": por_num.get(n, {}).get("pct", 0.0), "eleito": por_num.get(n, {}).get("eleito", False)}
                for k, n in (("F", modelo.NUM_F), ("L", modelo.NUM_L))}

    serie = historico()["demo" if DEMO else "real"]
    if cand and d.get("eleitorado"):
        v = cand["F"]["votos"] + cand["L"]["votos"]
        d_now = 100 * (cand["F"]["votos"] - cand["L"]["votos"]) / v if v else None
        d_proj = 100 * proj["D"] / (proj["F"] + proj["L"]) if proj.get("ok") else None
        registrar(serie, 100 * d["eleitorado_tot"] / d["eleitorado"], d["eleitorado_tot"], d_now, d_proj,
                  proj.get("prob_f"))

    eta = None
    if sit:
        e = modelo.previsao_decisao(serie, sit, proj)
        if e:
            hora_eta = None
            if e["seg"] and e["seg"] < 6 * 3600:
                hora_eta = datetime.fromtimestamp(time.time() + e["seg"], tse.TZ).strftime("%Hh%M")
            eta = {"frac": e["frac"], "hora": hora_eta}

    lider = None
    if sit:
        lider = "F" if sit["a"]["numero"] == modelo.NUM_F else "L"
    prob = proj.get("prob_f")
    if sit and (sit["certeza"] or sit["oficial"]):
        prob = 1.0 if lider == "F" else 0.0

    return limpo({
        "demo": DEMO, "hora": hora,
        "falha": bool(nac.get("erro")) or bool(coleta and coleta["erro"]),
        "erro": nac.get("erro") or (coleta or {}).get("erro"),
        "aba": Q.get("aba", "geral"), "rotacao": int(Q.get("rotacao", 0) or 0),
        "cand": cand,
        "nac": {"pst": d.get("pst", 0.0), "secoes": list(d.get("secoes", (0, 0))), "te": d.get("eleitorado", 0),
                "et": d.get("eleitorado_tot", 0), "validos": d.get("validos", 0), "sj": d.get("sub_judice", 0),
                "R": (sit or {}).get("R")},
        "sit": None if not sit else {"lider": lider, "dif": sit["dif"], "dif_pp": sit["dif_pp"],
                                     "virar_est": sit["virar_est"], "virar_max": sit["virar_max"],
                                     "certeza": sit["certeza"], "oficial": sit["oficial"]},
        "proj": {k: v for k, v in {**proj, "prob_f": prob}.items() if k not in ("por_mun", "zz")},
        "eta": eta,
        "hist": [[h["ap"], h["dn"], h["dp"], h["p"]] for h in serie],
        "rec": rec, "mapa": mapa, "grupos": grupos_1turno(),
        "coleta": coleta,
        "videos": videos(),
    })


def videos() -> list[dict]:
    if Q.get("videos"):
        ids = [v.strip() for v in str(Q["videos"]).split(",") if v.strip()][:2]
        return [{"titulo": (VIDEOS[k]["titulo"] if k < len(VIDEOS) else f"Ao vivo {k + 1}"), "id": i}
                for k, i in enumerate(ids)]
    return VIDEOS


# ───────────────────────── DIAGNÓSTICO ─────────────────────────
def tela_diagnostico():
    st.markdown("<style>.stApp *{color:#FFFCE1}.block-container{padding:2rem!important}</style>", unsafe_allow_html=True)
    st.title("Diagnóstico — 2º turno (eleição 6258)")
    for uf in ["br", "sp", "se"]:
        st.subheader(uf.upper())
        for u in tse.urls(uf):
            try:
                r = requests.get(u, headers=tse.HEADERS, timeout=6)
                st.write(f"`{u}` → HTTP {r.status_code}, {len(r.content)} bytes")
                if r.ok:
                    d = tse.ler(tse.decodificar(r.text), uf)
                    st.json({k: v for k, v in d.items() if k != "cands"})
                    st.json(d["cands"][:2])
                    break
            except Exception as e:  # noqa: BLE001
                st.write(f"`{u}` → {type(e).__name__}: {e}")
    col = tse.coletor()
    st.subheader("Coletor municipal")
    st.write({"municipios_lidos": len(col.votos), "fila": col.fila, "erro": col.erro,
              "codigos_tse_ibge": len(col.cd_ibge), "ultimo_ciclo": col.ultimo})


# ───────────────────────── PÁGINA ─────────────────────────
@st.fragment(run_every=tse.REFRESH_S)
def painel():
    with st.container(key="tela"):
        sinal = _painel(dados=montar(), altura=1080, key="painel", default=None)
    if not DEMO:
        presenca.registrar(sinal)   # contagem anônima de audiência (ver presenca.py e a página /sensor)


def pagina_painel():
    if DEBUG:
        tela_diagnostico()
        return
    if not DEMO:
        tse.coletor()           # começa a ler os municípios em segundo plano
    painel()


# /sensor: página escondida (sem link nem menu) com a audiência ao vivo
st.navigation([st.Page(pagina_painel, title="Apuração 2026 — 2º turno", default=True),
               st.Page(presenca.pagina, title="Sensor", url_path="sensor")], position="hidden").run()
