"""
Painel de apuração 2026 para TV — Presidente (BR) + Governador, Senador e
Deputado Federal (SE). Atualiza sozinho a cada 5 s lendo o JSON público do TSE.

Rodar:      streamlit run app.py
Modo demo:  abra a URL com ?demo=1  (dados fictícios que "andam", para testar o layout)
Diagnóstico: ?debug=1  (mostra o que o TSE devolve em cada URL)
"""
from __future__ import annotations

import base64
import gzip
import json
import random
import zlib
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


def urls_candidatas(ele: int, uf: str, cargo: int) -> list[str]:
    """Formatos possíveis, em ordem. O de 2026 (visto no Network) é /dados/...-u.jws."""
    c, e = f"c{cargo:04d}", f"e{ele:06d}"
    return [
        f"{BASE}/{ele}/dados/{uf}/{uf}-{c}-{e}-u.jws",
        f"{BASE}/{ele}/dados/{uf}/{uf}-{c}-{e}-v.jws",
        f"{BASE}/{ele}/dados-simplificados/{uf}/{uf}-{c}-{e}-r.jws",
        f"{BASE}/{ele}/dados-simplificados/{uf}/{uf}-{c}-{e}-r.json",
    ]


def url_foto(ele: int, uf: str, sqcand: str) -> str:
    return f"{BASE}/{ele}/fotos/{uf}/{sqcand}.jpeg"


# ───────────────────────── LEITURA DOS DADOS ─────────────────────────
def num(v) -> float:
    """Converte '1.234,56' / '1234' / 51.07 em float."""
    if v is None or v == "" or isinstance(v, (dict, list)):
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


def _b64url(seg: str) -> bytes:
    seg = seg.strip()
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def _bytes_para_json(b: bytes):
    if b[:2] == b"\x1f\x8b":            # gzip
        b = gzip.decompress(b)
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                   # zlib/deflate cru
        return json.loads(zlib.decompress(b, -15).decode("utf-8"))


def decodificar(texto: str):
    """Aceita JSON puro, JWS compacto (xxx.yyy.zzz) ou JWS em JSON ({"payload": ...})."""
    t = texto.strip().lstrip("\ufeff")
    if t.startswith("{") or t.startswith("["):
        obj = json.loads(t)
        if isinstance(obj, dict) and "payload" in obj and isinstance(obj["payload"], str):
            return _bytes_para_json(_b64url(obj["payload"]))
        return obj
    partes = t.split(".")
    if len(partes) >= 2:
        return _bytes_para_json(_b64url(partes[1]))
    return _bytes_para_json(_b64url(t))


# Nomes/partidos tirados das páginas que você salvou — usados só se o arquivo do TSE vier sem nome.
NOMES = {
    "pres": {"22": ("FLAVIO BOLSONARO", "PL"), "13": ("LULA", "PT"), "70": ("ESCRITOR AUGUSTO CURY", "AVANTE"),
             "55": ("RONALDO CAIADO", "PSD"), "14": ("RENAN SANTOS", "MISSÃO"), "30": ("ZEMA", "NOVO"),
             "80": ("SAMARA", "UP"), "27": ("CLARIANA BARAO", "DC"), "16": ("HERTZ DIAS", "PSTU"),
             "21": ("EDMILSON COSTA", "PCB"), "35": ("VETERINÁRIO WILSON GRASSI", "DEMOCRATA"),
             "29": ("RUI COSTA PIMENTA", "PCO")},
    "gov": {"55": ("FÁBIO", "PSD"), "10": ("VALMIR DE FRANCISQUINHO", "REPUBLICANOS"),
            "50": ("DR. HELTON", "PSOL"), "27": ("TATY CRISTINA DE JESUS", "DC")},
    "sen": {"131": ("ROGERIO CARVALHO", "PT"), "155": ("DELEGADO ALESSANDRO", "MDB"),
            "101": ("DELEGADO ANDRÉ DAVID", "REPUBLICANOS"), "444": ("ANDRÉ MOURA", "UNIÃO"),
            "123": ("EDVALDO", "PDT"), "100": ("EDUARDO AMORIM", "REPUBLICANOS"), "222": ("RODRIGO VALADARES", "PL"),
            "500": ("IRAN BARBOSA", "PSOL"), "221": ("CORONEL ROCHA", "PL"), "277": ("RENATINHA", "DC")},
    "depf": {"4040": ("CLAUDIO MITIDIERI", "PSB"), "1311": ("JOAO DANIEL", "PT"), "4444": ("YANDRA MOURA", "UNIÃO"),
             "1313": ("MARCIO MACEDO", "PT"), "5505": ("DELEGADA KATARINA", "PSD"), "4422": ("CAPITÃO SAMUEL", "UNIÃO"),
             "2200": ("LUIZÃO DONA TRAMPI", "PL"), "1000": ("ICARO DE VALMIR", "REPUBLICANOS"),
             "1011": ("THIAGO DE JOALDO", "REPUBLICANOS"), "5515": ("ANDERSON DE ZÉ DAS CANAS", "PSD"),
             "2222": ("MOANA VALADARES", "PL"), "1111": ("LEVI OLIVEIRA", "PP"), "4004": ("BRENO GARIBALDE", "PSB"),
             "1177": ("GUSTINHO RIBEIRO", "PP"), "1033": ("JORNALISTA SUSANE VIDAL", "REPUBLICANOS"),
             "5555": ("FÁBIO REIS", "PSD"), "5577": ("NITINHO", "PSD"), "4015": ("MARCOS FRANCO", "PSB"),
             "4000": ("MARCOS SANTANA", "PSB"), "4010": ("ELBER BATALHA", "PSB"), "4420": ("SHEYLA GALBA", "UNIÃO"),
             "4056": ("ROBSON VIANA", "PSB"), "5050": ("DELEGADO MÁRIO LEONY", "PSOL"), "5588": ("NETO BATALHA", "PSD")},
}


CHAVES_PARTIDO = ("sgp", "sg", "sigla", "sgpart", "partido")


def _sigla(d: dict) -> str:
    for k in CHAVES_PARTIDO:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _eh_candidato(d: dict) -> bool:
    if "vap" not in d and "pvap" not in d:
        return False
    if "sqcand" in d:
        return True
    # grupo (partido/federação) também pode ter 'vap', mas carrega listas dentro
    return "n" in d and not any(isinstance(v, list) for v in d.values())


def achar_candidatos(d, _sigla_herdada: str = "") -> list:
    """Junta TODOS os candidatos do arquivo, em qualquer nível.

    Em 2026 os candidatos vêm agrupados por partido/federação; pegar só a
    primeira lista mostrava apenas o 1º grupo. Aqui o partido do grupo é
    herdado pelo candidato quando ele não traz a sigla.
    """
    out = []
    if isinstance(d, dict):
        if _eh_candidato(d):
            c = dict(d)
            if _sigla_herdada and not _sigla(c):
                c["_partido"] = _sigla_herdada
            return [c]
        herdada = _sigla(d) or _sigla_herdada
        for v in d.values():
            if isinstance(v, (dict, list)):
                out.extend(achar_candidatos(v, herdada))
    elif isinstance(d, list):
        for v in d:
            out.extend(achar_candidatos(v, _sigla_herdada))
    return out


def achar_dict_com(d, chave: str):
    """Primeiro dicionário (em qualquer nível) que tenha a chave pedida com valor simples."""
    if isinstance(d, dict):
        if chave in d and not isinstance(d[chave], (dict, list)):
            return d
        for v in d.values():
            r = achar_dict_com(v, chave)
            if r is not None:
                return r
    elif isinstance(d, list):
        for v in d:
            r = achar_dict_com(v, chave)
            if r is not None:
                return r
    return None


def recortar_abrangencia(raw, uf: str):
    """Se o arquivo trouxer várias abrangências ('abr'), fica só com a da UF/BR pedida."""
    if isinstance(raw, dict) and isinstance(raw.get("abr"), list):
        for a in raw["abr"]:
            if isinstance(a, dict) and str(a.get("cdabr", "")).lower() == uf.lower():
                return a
        if raw["abr"]:
            return raw["abr"][0]
    return raw


# Número do partido (2 primeiros dígitos do candidato) → sigla. Usado só como último recurso.
PARTIDOS = {
    "10": "REPUBLICANOS", "11": "PP", "12": "PDT", "13": "PT", "14": "MISSÃO", "15": "MDB", "16": "PSTU",
    "18": "REDE", "19": "PODE", "20": "PODE", "21": "PCB", "22": "PL", "23": "CIDADANIA", "25": "PRD",
    "27": "DC", "28": "PRTB", "29": "PCO", "30": "NOVO", "33": "PMN", "35": "DEMOCRATA", "36": "AGIR",
    "40": "PSB", "43": "PV", "44": "UNIÃO", "45": "PSDB", "50": "PSOL", "55": "PSD", "65": "PC do B",
    "70": "AVANTE", "77": "SOLIDARIEDADE", "80": "UP",
}


def partido(c: dict) -> str:
    sig = _sigla(c) or c.get("_partido", "")
    if sig:
        return str(sig)
    cc = str(c.get("cc") or "")
    if cc:
        return cc.split(" - ")[0].split("(")[0].strip()[:18]
    return PARTIDOS.get(str(c.get("n") or "")[:2], "")


def normalizar(raw, chave: str, ele: int, uf: str) -> dict:
    corpo = recortar_abrangencia(raw, uf)

    d_sec = achar_dict_com(corpo, "pst") or {}
    pst = num(d_sec.get("pst"))
    total = num(d_sec.get("ts") or d_sec.get("s"))
    totalizadas = num(d_sec.get("st"))
    if not pst and total:
        pst = 100 * totalizadas / total

    tabela = NOMES.get(chave, {})
    cands, vistos = [], set()
    for c in achar_candidatos(corpo):
        numero = str(c.get("n") or "")
        ident = str(c.get("sqcand") or numero)
        if ident in vistos:
            continue
        vistos.add(ident)
        nome_tab, part_tab = tabela.get(numero, ("", ""))
        cands.append({
            "nome": str(c.get("nmu") or nome_tab or c.get("nm") or f"Candidato {numero}"),
            "numero": numero,
            "partido": partido(c) or part_tab,
            "votos": int(num(c.get("vap"))),
            "pct": num(c.get("pvap")),
            "situacao": str(c.get("st") or ""),
            "eleito": str(c.get("e") or "").lower() == "s",
            "foto": url_foto(ele, uf, str(c.get("sqcand"))) if c.get("sqcand") else "",
        })
    cands.sort(key=lambda x: (x["votos"], x["pct"]), reverse=True)

    d_h = achar_dict_com(raw, "hg") or achar_dict_com(raw, "ht") or {}
    hora = d_h.get("hg") or d_h.get("ht") or ""
    data = d_h.get("dg") or d_h.get("dt") or ""
    return {
        "pst": pst,
        "secoes": (int(totalizadas), int(total)),
        "atualizado": f"{data} {hora}".strip(),
        "top": cands[:2],
    }


@st.cache_data(ttl=REFRESH_S - 1, show_spinner=False)
def baixar(url: str):
    r = requests.get(url, headers=HEADERS, params={"nocache": int(time.time() * 1000)}, timeout=4)
    r.raise_for_status()
    return decodificar(r.text)


@st.cache_resource
def ultimo_bom() -> dict:
    """Último resultado válido de cada cargo + qual URL funcionou."""
    return {"dados": {}, "url": {}}


def baixar_cargo(cargo):
    """Tenta a URL que já funcionou; senão, percorre os formatos possíveis."""
    chave, _, _, ele, uf, cod = cargo
    mem = ultimo_bom()
    urls = urls_candidatas(ele, uf, cod)
    if chave in mem["url"]:
        urls = [mem["url"][chave]] + [u for u in urls if u != mem["url"][chave]]
    erros = []
    for u in urls:
        try:
            raw = baixar(u)
            if not achar_candidatos(recortar_abrangencia(raw, uf)):
                raise ValueError("arquivo sem lista de candidatos")
            mem["url"][chave] = u
            return u, raw, None
        except Exception as e:  # noqa: BLE001
            erros.append(f"{u.rsplit('/', 1)[-1]}: {type(e).__name__} {str(e)[:80]}")
    return None, None, erros


def carregar_tudo() -> dict:
    mem = ultimo_bom()

    def um(cargo):
        chave, _, _, ele, uf, _ = cargo
        url, raw, erros = baixar_cargo(cargo)
        if raw is not None:
            try:
                dados = normalizar(raw, chave, ele, uf)
                mem["dados"][chave] = dados
                return chave, dados, None
            except Exception as e:  # noqa: BLE001
                erros = [f"leitura: {type(e).__name__} {e}"]
        return chave, mem["dados"].get(chave), (erros[0] if erros else "erro")

    with ThreadPoolExecutor(max_workers=4) as ex:
        return {chave: {"dados": d, "erro": e} for chave, d, e in ex.map(um, CARGOS)}


def tela_diagnostico():
    """?debug=1 — mostra o que o TSE está devolvendo, para ajustar o leitor se preciso."""
    st.markdown("<style>.stApp *{color:#EEF2F6}</style>", unsafe_allow_html=True)
    st.title("Diagnóstico das URLs do TSE")
    for cargo in CARGOS:
        chave, titulo, abrang, ele, uf, cod = cargo
        st.subheader(f"{titulo} — {abrang}")
        for u in urls_candidatas(ele, uf, cod):
            try:
                r = requests.get(u, headers=HEADERS, timeout=6)
                st.write(f"`{u}` → HTTP {r.status_code}, {len(r.content)} bytes")
                if r.ok:
                    st.code(r.text[:300], language="text")
                    obj = decodificar(r.text)
                    corpo = recortar_abrangencia(obj, uf)
                    st.write("Chaves do topo:", list(obj.keys())[:40] if isinstance(obj, dict) else type(obj).__name__)
                    cands = achar_candidatos(corpo)
                    st.write(f"Candidatos encontrados: {len(cands)}")
                    if cands:
                        st.json(cands[:2])
                    st.write("Resultado lido pelo painel:")
                    st.json(normalizar(obj, chave, ele, uf))
                    break
            except Exception as e:  # noqa: BLE001
                st.write(f"`{u}` → {type(e).__name__}: {e}")


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
DEBUG = st.query_params.get("debug") in ("1", "true", "sim")


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


if DEBUG:
    tela_diagnostico()
else:
    painel()
