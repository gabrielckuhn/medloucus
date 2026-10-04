"""
Painel de apuração 2026 para TV — Presidente (BR) + Governador, Senador e
Deputado Federal (SE). Atualiza sozinho a cada 5 s lendo o JSON público do TSE.

Rodar:      streamlit run app.py
Modo demo:  abra a URL com ?demo=1  (dados fictícios que "andam", para testar o layout)
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# ───────────────────────── CONFIGURAÇÃO ─────────────────────────
REFRESH_S = 5
BASE = "https://resultados.tse.jus.br/oficial/ele2026"
ELE_FEDERAL = 6257   # eleição do Presidente (visto na URL do TSE: #/eleicao/6257/uf/br)
ELE_ESTADUAL = 6259  # eleição dos cargos estaduais (visto nas fotos: /ele2026/6259/fotos/se)
UF = "se"

# (chave, título, abrangência, código da eleição, uf do arquivo, código do cargo)
CARGOS = [
    ("pres", "Presidente", "Brasil", ELE_FEDERAL, "br", 1),
    ("gov", "Governador", "Sergipe", ELE_ESTADUAL, UF, 3),
    ("sen", "Senador", "Sergipe", ELE_ESTADUAL, UF, 5),
    ("depf", "Deputado federal", "Sergipe", ELE_ESTADUAL, UF, 6),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (painel-apuracao-tv)",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
}
TZ = ZoneInfo("America/Maceio")  # Aracaju = UTC-3


def url_json(ele: int, uf: str, cargo: int) -> str:
    # Padrão do TSE: /oficial/ele{ano}/{eleição}/dados-simplificados/{uf}/{uf}-c{cargo:04}-e{eleição:06}-r.json
    return f"{BASE}/{ele}/dados-simplificados/{uf}/{uf}-c{cargo:04d}-e{ele:06d}-r.json"


def url_foto(ele: int, uf: str, sqcand: str) -> str:
    return f"{BASE}/{ele}/fotos/{uf}/{sqcand}.jpeg"


# ───────────────────────── LEITURA DOS DADOS ─────────────────────────
def num(v) -> float:
    """Converte '1.234,56' / '1234' / 51.07 em float."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def achar_candidatos(d) -> list:
    """Pega a lista 'cand'; se o formato mudar, procura qualquer lista de dicts com 'vap'."""
    if isinstance(d, dict):
        if isinstance(d.get("cand"), list):
            return d["cand"]
        for v in d.values():
            r = achar_candidatos(v)
            if r:
                return r
    elif isinstance(d, list):
        if d and isinstance(d[0], dict) and "vap" in d[0]:
            return d
        for v in d:
            r = achar_candidatos(v)
            if r:
                return r
    return []


def partido(c: dict) -> str:
    for k in ("sgp", "sg", "partido"):
        if c.get(k):
            return str(c[k])
    cc = str(c.get("cc") or "")
    # 'cc' costuma vir como "PT - Federação ..." → fica só a sigla
    return cc.split(" - ")[0].split("(")[0].strip()[:18]


def normalizar(raw: dict, ele: int, uf: str) -> dict:
    total = num(raw.get("s"))
    totalizadas = num(raw.get("st"))
    pst = num(raw.get("pst")) or (100 * totalizadas / total if total else 0.0)

    cands = []
    for c in achar_candidatos(raw):
        cands.append({
            "nome": str(c.get("nm") or c.get("nmu") or "—"),
            "numero": str(c.get("n") or ""),
            "partido": partido(c),
            "votos": int(num(c.get("vap"))),
            "pct": num(c.get("pvap")),
            "situacao": str(c.get("st") or ""),
            "eleito": str(c.get("e") or "").lower() == "s",
            "foto": url_foto(ele, uf, str(c.get("sqcand"))) if c.get("sqcand") else "",
        })
    cands.sort(key=lambda x: x["votos"], reverse=True)

    hora = raw.get("hg") or raw.get("ht") or ""
    data = raw.get("dg") or raw.get("dt") or ""
    return {
        "pst": pst,
        "secoes": (int(totalizadas), int(total)),
        "atualizado": f"{data} {hora}".strip(),
        "top": cands[:2],
    }


@st.cache_data(ttl=REFRESH_S - 1, show_spinner=False)
def baixar(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, params={"_": int(time.time())}, timeout=4)
    r.raise_for_status()
    return r.json()


@st.cache_resource
def ultimo_bom() -> dict:
    """Guarda o último resultado válido de cada cargo (se o TSE engasgar, a TV não fica vazia)."""
    return {}


def carregar_tudo() -> dict:
    memoria = ultimo_bom()

    def um(cargo):
        chave, _, _, ele, uf, cod = cargo
        try:
            dados = normalizar(baixar(url_json(ele, uf, cod)), ele, uf)
            memoria[chave] = dados
            return chave, dados, None
        except Exception as e:  # noqa: BLE001
            return chave, memoria.get(chave), f"{type(e).__name__}"

    with ThreadPoolExecutor(max_workers=4) as ex:
        out = {}
        for chave, dados, erro in ex.map(um, CARGOS):
            out[chave] = {"dados": dados, "erro": erro}
    return out


# ───────────────────────── MODO DEMO ─────────────────────────
DEMO_BASE = {
    "pres": [("FLAVIO BOLSONARO", "22", "PL", 51.07), ("LULA", "13", "PT", 40.82)],
    "gov": [("FÁBIO", "55", "PSD", 58.77), ("VALMIR DE FRANCISQUINHO", "10", "REPUBLICANOS", 36.71)],
    "sen": [("ROGERIO CARVALHO", "131", "PT", 20.65), ("DELEGADO ALESSANDRO", "155", "MDB", 18.19)],
    "depf": [("CLAUDIO MITIDIERI", "4040", "PSB", 7.89), ("JOAO DANIEL", "1311", "PT", 7.68)],
}


def carregar_demo() -> dict:
    t = (time.time() / REFRESH_S) % 200
    pst_br, pst_se = min(100.0, 21.96 + t * 0.4), min(100.0, 18.59 + t * 0.45)
    agora = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
    out = {}
    for chave, *_ in CARGOS:
        pst = pst_br if chave == "pres" else pst_se
        base_votos = 120_000_000 if chave == "pres" else 1_100_000
        top = []
        for nome, n, p, pct in DEMO_BASE[chave]:
            pct_j = max(0.0, pct + random.uniform(-0.25, 0.25))
            top.append({"nome": nome, "numero": n, "partido": p, "pct": pct_j,
                        "votos": int(base_votos * pst / 100 * pct_j / 100),
                        "situacao": "", "eleito": False, "foto": ""})
        top.sort(key=lambda x: x["pct"], reverse=True)
        out[chave] = {"dados": {"pst": pst, "secoes": (0, 0), "atualizado": agora, "top": top}, "erro": None}
    return out


# ───────────────────────── VISUAL ─────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Barlow:wght@400;500;600&display=swap');

:root{
  --tinta:#0C2340;      /* azul-urna */
  --painel:#132F52;
  --linha:#24476F;
  --tecla:#EEF2F6;      /* teclas brancas da urna */
  --apagado:#8FA6C1;
  --confirma:#2BB673;   /* tecla CONFIRMA */
  --corrige:#F08A24;    /* tecla CORRIGE */
}

/* some com o "chrome" do Streamlit */
header[data-testid="stHeader"], footer, #MainMenu,
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"]{display:none!important;}
html, body, .stApp, [data-testid="stAppViewContainer"]{background:var(--tinta)!important;}
.block-container, [data-testid="stMainBlockContainer"]{padding:1.6vh 1.8vw!important;max-width:100%!important;}
[data-testid="stVerticalBlock"]{gap:0!important;}
/* evita o "piscar" esmaecido durante o refresh */
[data-stale="true"], .stale-element{opacity:1!important;filter:none!important;transition:none!important;}

.painel{font-family:'Barlow',system-ui,sans-serif;color:var(--tecla);
  height:calc(100vh - 3.2vh);display:flex;flex-direction:column;gap:1.4vh;}

.topo{display:flex;align-items:baseline;justify-content:space-between;
  border-bottom:2px solid var(--linha);padding-bottom:.8vh;}
.marca{font-family:'Barlow Condensed',sans-serif;font-weight:800;margin:0;padding:0;
  font-size:clamp(28px,4.6vh,64px);letter-spacing:.01em;color:var(--tecla);line-height:1;}
.marca small{font-weight:500;color:var(--apagado);font-size:.55em;margin-left:.6em;}
.relogio{font-family:'Barlow Condensed',sans-serif;font-size:clamp(20px,3.4vh,48px);
  font-weight:600;color:var(--apagado);display:flex;align-items:center;gap:.5em;}
.vivo{display:inline-block;width:.55em;height:.55em;border-radius:50%;background:var(--confirma);
  box-shadow:0 0 0 0 rgba(43,182,115,.6);animation:pulso 2s infinite;}
.vivo.off{background:var(--corrige);animation:none;}
@keyframes pulso{0%{box-shadow:0 0 0 0 rgba(43,182,115,.55)}70%{box-shadow:0 0 0 .7em rgba(43,182,115,0)}100%{box-shadow:0 0 0 0 rgba(43,182,115,0)}}

.grade{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:1.4vh 1.4vw;min-height:0;}
.cargo{background:var(--painel);border:1px solid var(--linha);border-radius:14px;
  padding:1.6vh 1.4vw;display:flex;flex-direction:column;gap:1.2vh;min-height:0;}

.cab{display:flex;justify-content:space-between;align-items:flex-end;gap:1vw;}
.titulo{font-family:'Barlow Condensed',sans-serif!important;font-weight:800!important;margin:0!important;padding:0!important;line-height:1!important;
  font-size:clamp(26px,4.4vh,62px)!important;color:var(--tecla)!important;}
.titulo span{font-weight:500;color:var(--apagado);font-size:.6em;margin-left:.35em;}
.urnas{text-align:right;line-height:1;}
.urnas b{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(26px,4.4vh,62px);color:var(--tecla);}
.urnas small{display:block;color:var(--apagado);font-size:clamp(12px,1.6vh,22px);margin-top:.3vh;}
.trilho{height:1vh;min-height:6px;background:var(--linha);border-radius:99px;overflow:hidden;}
.trilho i{display:block;height:100%;background:var(--tecla);border-radius:99px;transition:width .8s ease;}

.cands{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;gap:1vh;min-height:0;}
.cand{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:1.1vw;}
.foto{--c:var(--confirma);position:relative;width:clamp(48px,9vh,130px);aspect-ratio:3/4;border-radius:10px;
  background:var(--linha);border:3px solid var(--c);overflow:hidden;display:grid;place-items:center;
  font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(18px,3.4vh,48px);color:var(--apagado);}
.foto::after{content:"";position:absolute;inset:0;background-image:var(--foto);background-size:cover;background-position:center top;}
.cand.seg .foto{--c:var(--corrige);}
.info{min-width:0;}
.nome{font-family:'Barlow Condensed',sans-serif;font-weight:700;line-height:1.02;
  font-size:clamp(22px,4vh,58px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.meta{color:var(--apagado);font-size:clamp(13px,1.9vh,26px);margin-top:.3vh;}
.meta .tag{display:inline-block;margin-left:.6em;padding:.05em .5em;border-radius:6px;
  background:var(--confirma);color:var(--tinta);font-weight:600;}
.meta .tag.alerta{background:var(--corrige);}
.barra{height:.9vh;min-height:5px;background:var(--linha);border-radius:99px;margin-top:.8vh;overflow:hidden;}
.barra i{display:block;height:100%;background:var(--confirma);transition:width .8s ease;}
.cand.seg .barra i{background:var(--corrige);}
.pct{font-family:'Barlow Condensed',sans-serif;font-weight:800;line-height:1;text-align:right;
  font-size:clamp(34px,7.4vh,110px);font-variant-numeric:tabular-nums;color:var(--confirma);}
.cand.seg .pct{color:var(--corrige);}
.pct small{font-size:.45em;font-weight:600;}

.vazio{flex:1;display:grid;place-items:center;text-align:center;color:var(--apagado);
  font-size:clamp(16px,2.4vh,32px);}
.aviso{color:var(--corrige);font-size:clamp(12px,1.5vh,20px);}

@media (max-width:900px){
  .painel{height:auto;}
  .grade{grid-template-columns:1fr;grid-template-rows:none;}
  .cargo{min-height:42vh;}
}
@media (prefers-reduced-motion:reduce){.vivo{animation:none}.trilho i,.barra i{transition:none}}
</style>
"""


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_pct(p: float) -> str:
    return f"{p:.2f}".replace(".", ",")


def iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p[0].isalpha()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def html_cand(c: dict, pos: int) -> str:
    foto_css = f"--foto:url('{escape(c['foto'])}')" if c["foto"] else ""
    situ = c["situacao"].lower()
    tag = ""
    if c["eleito"] or situ.startswith("eleito"):
        tag = '<span class="tag">Eleito</span>'
    elif "2º turno" in situ or "2o turno" in situ:
        tag = '<span class="tag">2º turno</span>'
    elif "sub judice" in situ:
        tag = '<span class="tag alerta">Sub judice</span>'
    largura = max(0.0, min(100.0, c["pct"]))
    partido_num = " – ".join(x for x in (escape(c["partido"]), escape(c["numero"])) if x)
    return f"""
    <div class="cand {'seg' if pos else ''}">
      <div class="foto" style="{foto_css}">{escape(iniciais(c['nome']))}</div>
      <div class="info">
        <div class="nome">{escape(c['nome'])}</div>
        <div class="meta">{partido_num} &nbsp; {fmt_int(c['votos'])} votos{tag}</div>
        <div class="barra"><i style="width:{largura:.2f}%"></i></div>
      </div>
      <div class="pct">{fmt_pct(c['pct'])}<small>%</small></div>
    </div>"""


def html_cargo(cargo, bloco) -> str:
    chave, titulo, abrang, *_ = cargo
    dados, erro = bloco["dados"], bloco["erro"]
    if not dados:
        corpo = f'<div class="vazio"><div>Aguardando dados do TSE…<br><span class="aviso">{escape(erro or "")}</span></div></div>'
        return f'<div class="cargo"><div class="cab"><div class="titulo">{titulo}<span>{abrang}</span></div></div>{corpo}</div>'

    pst = dados["pst"]
    tot, total = dados["secoes"]
    sub = f"{fmt_int(tot)} de {fmt_int(total)} seções" if total else "urnas apuradas"
    if erro:
        sub = f'<span class="aviso">sem conexão — mostrando o último dado</span>'
    cands = "".join(html_cand(c, i) for i, c in enumerate(dados["top"])) or \
        '<div class="vazio">Ainda sem votos totalizados</div>'
    return f"""
    <div class="cargo">
      <div class="cab">
        <div class="titulo">{titulo}<span>{abrang}</span></div>
        <div class="urnas"><b>{fmt_pct(pst)}%</b><small>{sub}</small></div>
      </div>
      <div class="trilho"><i style="width:{min(pst, 100):.2f}%"></i></div>
      <div class="cands">{cands}</div>
    </div>"""


# ───────────────────────── PÁGINA ─────────────────────────
st.set_page_config(page_title="Apuração 2026", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

DEMO = st.query_params.get("demo") in ("1", "true", "sim")


@st.fragment(run_every=REFRESH_S)
def painel():
    blocos = carregar_demo() if DEMO else carregar_tudo()
    algum_erro = any(b["erro"] for b in blocos.values())
    agora = datetime.now(TZ).strftime("%H:%M:%S")
    tse_hora = next((b["dados"]["atualizado"].split(" ")[-1] for b in blocos.values()
                     if b["dados"] and b["dados"]["atualizado"]), "")
    rotulo = f"TSE {tse_hora}" if tse_hora else agora
    cards = "".join(html_cargo(c, blocos[c[0]]) for c in CARGOS)
    st.markdown(f"""
    <div class="painel">
      <div class="topo">
        <div class="marca">Apuração 2026<small>1º turno{' — demonstração' if DEMO else ''}</small></div>
        <div class="relogio"><span class="vivo {'off' if algum_erro else ''}"></span>{rotulo}</div>
      </div>
      <div class="grade">{cards}</div>
    </div>""", unsafe_allow_html=True)


painel()
