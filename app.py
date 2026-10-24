"""
Apuração 2026 — 2º turno, Presidente. Painel para TV que atualiza sozinho a cada 5 s.

O que ele faz:
  • lê o resultado nacional e o de cada UF direto dos arquivos públicos do TSE (eleição 6258);
  • mostra votos apurados, diferença entre os dois candidatos e quanto ainda pode entrar;
  • crava "MATEMATICAMENTE ELEITO" quando a vantagem já é maior que todos os votos que ainda
    podem ser contados — mesmo antes de o TSE proclamar;
  • projeta o resultado final por UF (mantém o % de cada candidato em cada estado e escala
    pelo eleitorado que falta apurar ali).

Rodar:       streamlit run app.py
Demonstração: ?demo=1   (dados fictícios que vão até 100%)
Diagnóstico:  ?debug=1  (mostra o que o TSE devolve)
Mapa:         aba "Mapa" no topo — municípios coloridos pela margem do vencedor (pasta mapa_br/)
O painel do 1º turno está em app_1turno.py.
"""
from __future__ import annotations

import base64
import gzip
import json
import random
import re
import threading
import time
import unicodedata
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import streamlit.components.v1 as components

# ───────────────────────── CONFIGURAÇÃO ─────────────────────────
REFRESH_S = 5
BASE = "https://resultados.tse.jus.br/oficial/ele2026"
ELE = 6258   # 2º turno presidencial (visto no Network: /ele2026/6258/dados/br/br-c0001-e006258-u.jws)
CARGO = 1    # Presidente
UFS = [
    ("ac", "Acre"), ("al", "Alagoas"), ("ap", "Amapá"), ("am", "Amazonas"), ("ba", "Bahia"),
    ("ce", "Ceará"), ("df", "Distrito Federal"), ("es", "Espírito Santo"), ("go", "Goiás"),
    ("ma", "Maranhão"), ("mt", "Mato Grosso"), ("ms", "Mato Grosso do Sul"), ("mg", "Minas Gerais"),
    ("pa", "Pará"), ("pb", "Paraíba"), ("pr", "Paraná"), ("pe", "Pernambuco"), ("pi", "Piauí"),
    ("rj", "Rio de Janeiro"), ("rn", "Rio Grande do Norte"), ("rs", "Rio Grande do Sul"),
    ("ro", "Rondônia"), ("rr", "Roraima"), ("sc", "Santa Catarina"), ("sp", "São Paulo"),
    ("se", "Sergipe"), ("to", "Tocantins"), ("zz", "Exterior"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (painel-apuracao-tv)", "Accept": "*/*", "Cache-Control": "no-cache"}
TZ = ZoneInfo("America/Maceio")
OURO = "#F5C542"


def urls(uf: str) -> list[str]:
    c, e = f"c{CARGO:04d}", f"e{ELE:06d}"
    return [
        f"{BASE}/{ELE}/dados/{uf}/{uf}-{c}-{e}-u.jws",
        f"{BASE}/{ELE}/dados/{uf}/{uf}-{c}-{e}-v.jws",
        f"{BASE}/{ELE}/dados-simplificados/{uf}/{uf}-{c}-{e}-r.json",
    ]


def url_foto(uf: str, sqcand: str) -> str:
    return f"{BASE}/{ELE}/fotos/{uf}/{sqcand}.jpeg"


# ───────────────────────── LEITURA DO ARQUIVO DO TSE ─────────────────────────
def num(v) -> float:
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
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return json.loads(zlib.decompress(b, -15).decode("utf-8"))


def decodificar(texto: str):
    """JSON puro, JWS compacto (xxx.yyy.zzz) ou JWS em JSON ({"payload": ...})."""
    t = texto.strip().lstrip("﻿")
    if t[:1] in "{[":
        obj = json.loads(t)
        if isinstance(obj, dict) and isinstance(obj.get("payload"), str):
            return _bytes_para_json(_b64url(obj["payload"]))
        return obj
    partes = t.split(".")
    return _bytes_para_json(_b64url(partes[1] if len(partes) >= 2 else t))


def _eh_candidato(d: dict) -> bool:
    if "vap" not in d and "pvap" not in d:
        return False
    return "sqcand" in d or ("n" in d and not any(isinstance(v, list) for v in d.values()))


CHAVES_PARTIDO = ("sgp", "sg", "sigla", "sgpart", "partido")


def _sigla(d: dict) -> str:
    for k in CHAVES_PARTIDO:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def achar_candidatos(d, herdada: str = "") -> list:
    """Todos os candidatos, em qualquer nível (o arquivo de 2026 agrupa por partido)."""
    out = []
    if isinstance(d, dict):
        if _eh_candidato(d):
            c = dict(d)
            if herdada and not _sigla(c):
                c["_partido"] = herdada
            return [c]
        h = _sigla(d) or herdada
        for v in d.values():
            if isinstance(v, (dict, list)):
                out.extend(achar_candidatos(v, h))
    elif isinstance(d, list):
        for v in d:
            out.extend(achar_candidatos(v, herdada))
    return out


def achar_dict_com(d, chave: str):
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


def achar_num(d, chaves: tuple[str, ...]) -> float:
    """Primeiro valor > 0 de uma das chaves, em qualquer nível, sem olhar dentro dos candidatos."""
    if isinstance(d, dict):
        if _eh_candidato(d):
            return 0.0
        for k in chaves:
            if k in d and not isinstance(d[k], (dict, list)) and num(d[k]) > 0:
                return num(d[k])
        for k, v in d.items():
            if k != "cand" and isinstance(v, (dict, list)):
                r = achar_num(v, chaves)
                if r:
                    return r
    elif isinstance(d, list):
        for v in d:
            r = achar_num(v, chaves)
            if r:
                return r
    return 0.0


def recortar_abrangencia(raw, uf: str):
    if isinstance(raw, dict) and isinstance(raw.get("abr"), list) and raw["abr"]:
        for a in raw["abr"]:
            if isinstance(a, dict) and str(a.get("cdabr", "")).lower() == uf.lower():
                return a
        return raw["abr"][0]
    return raw


PARTIDOS = {"10": "REPUBLICANOS", "11": "PP", "12": "PDT", "13": "PT", "14": "MISSÃO", "15": "MDB",
            "22": "PL", "30": "NOVO", "40": "PSB", "44": "UNIÃO", "45": "PSDB", "50": "PSOL", "55": "PSD",
            "70": "AVANTE"}
NOMES = {"22": "FLAVIO BOLSONARO", "13": "LULA"}


def partido(c: dict) -> str:
    sig = _sigla(c) or c.get("_partido", "")
    if sig:
        return sig
    cc = str(c.get("cc") or "")
    if cc:
        return cc.split(" - ")[0].split("(")[0].strip()[:18]
    return PARTIDOS.get(str(c.get("n") or "")[:2], "")


def sub_judice(c: dict) -> bool:
    return "sub judice" in str(c.get("situacao", "")).lower()


def ler(raw, uf: str) -> dict:
    """Normaliza um arquivo (Brasil ou UF)."""
    corpo = recortar_abrangencia(raw, uf)
    d_sec = achar_dict_com(corpo, "pst") or {}
    pst = num(d_sec.get("pst"))
    total = num(d_sec.get("ts") or d_sec.get("s"))
    totalizadas = num(d_sec.get("st"))
    if not pst and total:
        pst = 100 * totalizadas / total

    cands, vistos = [], set()
    for c in achar_candidatos(corpo):
        n = str(c.get("n") or "")
        ident = str(c.get("sqcand") or n)
        if ident in vistos:
            continue
        vistos.add(ident)
        cands.append({
            "nome": str(c.get("nmu") or c.get("nmurna") or NOMES.get(n) or c.get("nm") or f"Candidato {n}"),
            "numero": n,
            "partido": partido(c),
            "votos": int(num(c.get("vap"))),
            "pct": num(c.get("pvap")),
            "situacao": str(c.get("st") or ""),
            # e="s" também marca quem foi ao 2º turno; eleito só quando a situação diz "Eleito"
            "eleito": str(c.get("st") or "").strip().lower().startswith("eleit"),
            "foto": url_foto(uf, str(c.get("sqcand"))) if c.get("sqcand") else "",
        })
    cands.sort(key=lambda x: (x["votos"], x["pct"]), reverse=True)

    validos_c = sum(c["votos"] for c in cands if not sub_judice(c))
    sj_c = sum(c["votos"] for c in cands if sub_judice(c))
    d_h = achar_dict_com(raw, "hg") or achar_dict_com(raw, "ht") or {}
    return {
        "pst": pst,
        "secoes": (int(totalizadas), int(total)),
        "cands": cands,
        "eleitorado": int(achar_num(corpo, ("te", "eleitorado"))),         # eleitorado apto total
        "eleitorado_tot": int(achar_num(corpo, ("est", "ea"))),            # apto das seções totalizadas
        "validos": int(max(achar_num(corpo, ("vv",)), validos_c)),
        "sub_judice": int(max(achar_num(corpo, ("vansj",)), sj_c)),        # anulados sub judice
        "atualizado": f'{d_h.get("dg") or d_h.get("dt") or ""} {d_h.get("hg") or d_h.get("ht") or ""}'.strip(),
    }


# ───────────────────────── DOWNLOAD ─────────────────────────
@st.cache_data(ttl=REFRESH_S - 1, show_spinner=False)
def baixar(url: str):
    r = requests.get(url, headers=HEADERS, params={"nocache": int(time.time() * 1000)}, timeout=4)
    r.raise_for_status()
    return decodificar(r.text)


@st.cache_resource
def memoria() -> dict:
    """Última leitura boa de cada abrangência e a URL que funcionou."""
    return {"dados": {}, "url": {}}


def carregar_uf(uf: str):
    mem = memoria()
    lista = urls(uf)
    if uf in mem["url"]:
        lista = [mem["url"][uf]] + [u for u in lista if u != mem["url"][uf]]
    erro = None
    for u in lista:
        try:
            raw = baixar(u)
            d = ler(raw, uf)
            if not d["cands"]:
                raise ValueError("sem candidatos")
            mem["url"][uf], mem["dados"][uf] = u, d
            return uf, d, None
        except Exception as e:  # noqa: BLE001
            erro = erro or f"{u.rsplit('/', 1)[-1]}: {type(e).__name__}"
    return uf, mem["dados"].get(uf), erro


def carregar() -> tuple[dict, dict]:
    with ThreadPoolExecutor(max_workers=15) as ex:
        res = list(ex.map(carregar_uf, ["br"] + [u for u, _ in UFS]))
    nac = {"dados": res[0][1], "erro": res[0][2]}
    ufs = {uf: {"dados": d, "erro": e} for uf, d, e in res[1:]}
    return nac, ufs


# ───────────────────────── DEMONSTRAÇÃO ─────────────────────────
ELEITORADO_DEMO = {
    "sp": 34_700_000, "mg": 16_300_000, "rj": 12_800_000, "ba": 11_300_000, "rs": 8_600_000, "pr": 8_500_000,
    "pe": 7_000_000, "ce": 6_800_000, "pa": 6_100_000, "sc": 5_500_000, "ma": 5_000_000, "go": 4_900_000,
    "pb": 3_000_000, "es": 2_900_000, "am": 2_600_000, "pi": 2_600_000, "mt": 2_500_000, "rn": 2_500_000,
    "al": 2_300_000, "df": 2_200_000, "ms": 2_000_000, "se": 1_740_000, "ro": 1_200_000, "to": 1_100_000,
    "zz": 700_000, "ac": 600_000, "ap": 550_000, "rr": 370_000,
}


def carregar_demo() -> tuple[dict, dict]:
    rnd = random.Random(7)
    passo = (time.time() / REFRESH_S) % 90          # ~7 min até 100%, depois recomeça
    if st.query_params.get("passo"):                # ?demo=1&passo=60 congela num ponto da apuração
        passo = float(st.query_params["passo"])
    ufs, soma = {}, {"E": 0, "Et": 0, "V": 0, "a": 0, "b": 0, "st": 0, "s": 0}
    for uf, _ in UFS:
        lean = rnd.uniform(-14, 14) + (6 if uf in ("sc", "pr", "go", "mt", "df", "ro", "rr", "ac") else 0) \
            - (8 if uf in ("ba", "pe", "ce", "ma", "pi", "pb", "rn", "se", "al") else 0)
        pa = max(25.0, min(75.0, 51.2 + lean))
        pst = min(100.0, rnd.uniform(2, 25) + passo * rnd.uniform(1.4, 2.2))
        e = ELEITORADO_DEMO[uf]
        et = int(e * pst / 100)
        v = int(et * 0.77)
        va, vb = int(v * pa / 100), v - int(v * pa / 100)
        sec = e // 400
        cands = sorted([
            {"nome": "FLAVIO BOLSONARO", "numero": "22", "partido": "PL", "votos": va, "pct": pa,
             "situacao": "", "eleito": False, "foto": ""},
            {"nome": "LULA", "numero": "13", "partido": "PT", "votos": vb, "pct": 100 - pa,
             "situacao": "", "eleito": False, "foto": ""}], key=lambda c: -c["votos"])
        ufs[uf] = {"dados": {"pst": pst, "secoes": (int(sec * pst / 100), sec), "cands": cands, "eleitorado": e,
                             "eleitorado_tot": et, "validos": v, "sub_judice": 0, "atualizado": ""}, "erro": None}
        for k, x in (("E", e), ("Et", et), ("V", v), ("a", va), ("b", vb), ("st", int(sec * pst / 100)), ("s", sec)):
            soma[k] += x
    v = soma["V"] or 1
    cands = sorted([
        {"nome": "FLAVIO BOLSONARO", "numero": "22", "partido": "PL", "votos": soma["a"], "pct": 100 * soma["a"] / v,
         "situacao": "", "eleito": False, "foto": ""},
        {"nome": "LULA", "numero": "13", "partido": "PT", "votos": soma["b"], "pct": 100 * soma["b"] / v,
         "situacao": "", "eleito": False, "foto": ""}], key=lambda c: -c["votos"])
    nac = {"pst": 100 * soma["st"] / soma["s"], "secoes": (soma["st"], soma["s"]), "cands": cands,
           "eleitorado": soma["E"], "eleitorado_tot": soma["Et"], "validos": soma["V"], "sub_judice": 0,
           "atualizado": datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")}
    return {"dados": nac, "erro": None}, ufs


# ───────────────────────── CÁLCULOS ─────────────────────────
def restante_max(d: dict) -> int | None:
    """Máximo de votos que ainda podem entrar = eleitorado apto das seções não totalizadas.
    None quando o arquivo não informa o eleitorado (aí nada pode ser garantido antes de 100%)."""
    if d["pst"] >= 100:
        return 0
    if d["eleitorado"] and d["eleitorado_tot"] and d["eleitorado"] >= d["eleitorado_tot"]:
        return d["eleitorado"] - d["eleitorado_tot"]
    return None


def pct_para_virar(diferenca: int, votos_restantes: float | None) -> float | None:
    """% dos votos válidos restantes que o 2º colocado precisa para empatar: s = (1 + D/R) / 2."""
    if votos_restantes is None:
        return None
    if votos_restantes <= 0:
        return float("inf") if diferenca > 0 else 50.0
    return 100 * (1 + diferenca / votos_restantes) / 2


def soma_nacional(ufs: dict) -> dict | None:
    """Se o arquivo do Brasil não trouxer o eleitorado, soma o das UFs."""
    E = sum((b["dados"] or {}).get("eleitorado", 0) for b in ufs.values())
    Et = sum((b["dados"] or {}).get("eleitorado_tot", 0) for b in ufs.values())
    return {"eleitorado": E, "eleitorado_tot": Et} if E and Et else None


def projetar(ufs: dict, nac: dict) -> dict:
    """Estimador de razão estratificado por UF: em cada UF, votos do candidato × (eleitorado total /
    eleitorado apurado). UFs sem voto ainda entram com eleitorado × taxa nacional de válidos,
    repartidos pelo % nacional atual."""
    proj, validos_proj = {}, 0.0
    linhas, faltando = [], []
    v_agora = e_agora = 0.0
    for uf, bloco in ufs.items():
        d = bloco["dados"]
        if not d or not d["cands"] or not sum(c["votos"] for c in d["cands"]):
            faltando.append((uf, (d or {}).get("eleitorado", 0)))
            continue
        if d["eleitorado_tot"] and d["eleitorado"] >= d["eleitorado_tot"]:
            fator = d["eleitorado"] / d["eleitorado_tot"]
        elif d["pst"] > 0:
            fator = 100 / d["pst"]
        else:
            faltando.append((uf, d["eleitorado"]))
            continue
        v_agora += d["validos"]
        e_agora += d["eleitorado_tot"]
        votos = {}
        for c in d["cands"]:
            if sub_judice(c):
                continue
            votos[c["numero"]] = c["votos"] * fator
            proj[c["numero"]] = proj.get(c["numero"], 0.0) + c["votos"] * fator
        validos_proj += sum(votos.values())
        linhas.append({"uf": uf, "pst": d["pst"], "agora": {c["numero"]: c["votos"] for c in d["cands"]},
                       "proj": votos})
    if faltando and v_agora and e_agora and proj:
        taxa = v_agora / e_agora
        tot = sum(proj.values())
        for uf, e in faltando:
            if not e:
                continue
            votos = {k: e * taxa * v / tot for k, v in proj.items()}
            for k, v in votos.items():
                proj[k] += v
            validos_proj += sum(votos.values())
            linhas.append({"uf": uf, "pst": 0.0, "agora": {}, "proj": votos, "estimada": True})
    if not proj and nac and nac["pst"] > 0:  # sem UFs: escala o Brasil inteiro
        f = (nac["eleitorado"] / nac["eleitorado_tot"]) if nac["eleitorado_tot"] else 100 / nac["pst"]
        proj = {c["numero"]: c["votos"] * f for c in nac["cands"] if not sub_judice(c)}
        validos_proj = sum(proj.values())
    pct = {k: 100 * v / validos_proj for k, v in proj.items()} if validos_proj else {}
    return {"votos": proj, "pct": pct, "validos": validos_proj, "linhas": linhas,
            "faltando": [u for u, _ in faltando]}


def analisar(nac: dict, ufs: dict) -> dict | None:
    d = nac["dados"]
    if not d or len(d["cands"]) < 2:
        return None
    if not (d["eleitorado"] and d["eleitorado_tot"]):
        extra = soma_nacional(ufs)
        if extra:
            d = {**d, **extra}
    a, b = d["cands"][0], d["cands"][1]
    D = a["votos"] - b["votos"]
    R = restante_max(d)
    sj = d["sub_judice"]
    taxa_validos = d["validos"] / d["eleitorado_tot"] if d["eleitorado_tot"] else None
    R_est = R * taxa_validos if (R is not None and taxa_validos) else None
    oficial = a["eleito"]
    # Certeza matemática (CF art. 77 §3º: maioria absoluta dos válidos no 2º turno). Pior caso:
    # todo eleitor que falta comparece, vota válido no 2º colocado e todo voto anulado sub judice
    # é revalidado para ele. Se mesmo assim não empata, acabou.
    certeza = R is not None and not sub_judice(a) and D > R + sj
    return {
        "d": d, "a": a, "b": b, "dif": D, "dif_pp": a["pct"] - b["pct"], "R": R, "R_est": R_est, "sj": sj,
        "virar_max": pct_para_virar(D, None if R is None else R + sj),
        "virar_est": pct_para_virar(D, None if R_est is None else R_est + sj),
        "oficial": oficial, "certeza": certeza, "proj": projetar(ufs, d),
    }


# ───────────────────────── MAPA MUNICIPAL ─────────────────────────
PASTA_MAPA = Path(__file__).parent / "mapa_br"
_componente_mapa = components.declare_component("mapa_br", path=str(PASTA_MAPA))
LAGOAS = {4300001, 4300002}      # Lagoa dos Patos e Lagoa Mirim (água, não município)
LIMITE_POR_CICLO = 1200          # municípios baixados por ciclo (o 1º carregamento leva ~1 min)
# Escala por faixa: [≥70%, ≥58%, ≥53%, >51,3%]; de 50%+1 a 51,3% fica no cinza neutro
ESCALAS = {"22": ["#187BD1", "#5C9BD3", "#6B91B3", "#84919C"],    # Flávio Bolsonaro: azul do painel, mesma perda de saturação do vermelho
           "13": ["#E91D24", "#D8585D", "#BC7B7E", "#A79294"]}    # Lula: vermelho
NEUTRO = "#f0f0f0"
SEM_DADO = "#1C3D66"
FAIXAS = ["70% ou mais", "58% a 70%", "53% a 58%", "51,3% a 53%"]
UF_IBGE = {"11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma",
           "22": "pi", "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba",
           "31": "mg", "32": "es", "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms",
           "51": "mt", "52": "go", "53": "df"}


@st.cache_resource
def geo_ids() -> list[int]:
    with open(PASTA_MAPA / "geo.json", encoding="utf-8") as f:
        return json.load(f)["ids"]


def faixa(pa: int) -> int | None:
    """pa = % do 1º candidato da tela ×10 entre os válidos; -1 = sem votos. Igual ao JS do mapa."""
    if pa < 0:
        return None
    lider = max(pa, 1000 - pa) / 10
    return 0 if lider >= 70 else 1 if lider >= 58 else 2 if lider >= 53 else 3 if lider > 51.3 else 4


class Coletor:
    """Roda em segundo plano (uma vez por servidor). A cada ciclo lê o andamento de cada UF
    ({uf}-e006258-ab.jws, com a hora da última totalização de cada município) e baixa só os
    municípios que mudaram ({uf}{mun}-c0001-e006258-u.jws)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.votos: dict[int, dict] = {}     # código IBGE → {"v": {número: votos}, "pst": %}
        self.carimbo: dict = {}              # (uf, cód. TSE) → (data, hora, seções) da última leitura
        self.cd_ibge: dict = {}              # (uf, cód. TSE) → código IBGE
        self.erro: str | None = None
        self.fila = 0
        self.ultimo = 0.0
        self.sessao = requests.Session()
        self.sessao.headers.update(HEADERS)

    def _get(self, url: str):
        r = self.sessao.get(url, params={"nocache": int(time.time() * 1000)}, timeout=6)
        r.raise_for_status()
        return decodificar(r.text)

    def _config(self):
        cfg = self._get(f"{BASE}/{ELE}/config/mun-e{ELE:06d}-cm.jws")
        m = {}
        for a in cfg.get("abr", []):
            uf = str(a.get("cd", "")).lower()
            if uf == "zz":                               # municípios do exterior não entram no mapa
                continue
            for mu in a.get("mu", []):
                try:
                    m[(uf, str(mu["cd"]))] = int(mu["cdi"])
                except (KeyError, ValueError, TypeError):
                    pass
        self.cd_ibge = m

    def _andamento(self, uf: str) -> list:
        try:
            j = self._get(f"{BASE}/{ELE}/dados/{uf}/{uf}-e{ELE:06d}-ab.jws")
        except Exception:  # noqa: BLE001
            return []
        out = []
        for a in j.get("abr", []):
            if str(a.get("tpabr", "")).lower() not in ("mun", "mu"):
                continue
            s_ = a.get("s") or {}
            if num(s_.get("st")) <= 0:                   # nenhuma seção totalizada ainda
                continue
            out.append(((uf, str(a.get("cdabr"))), (a.get("dt"), a.get("ht"), s_.get("st"))))
        return out

    def _municipio(self, item):
        (uf, cd), carimbo = item
        d = ler(self._get(f"{BASE}/{ELE}/dados/{uf}/{uf}{cd}-c{CARGO:04d}-e{ELE:06d}-u.jws"), uf)
        return (uf, cd), carimbo, {"v": {c["numero"]: c["votos"] for c in d["cands"] if not sub_judice(c)},
                                   "pst": d["pst"]}

    def ciclo(self):
        if not self.cd_ibge:
            self._config()
        with ThreadPoolExecutor(max_workers=14) as ex:
            listas = list(ex.map(self._andamento, [u for u, _ in UFS if u != "zz"]))
        mudou = [it for lista in listas for it in lista if self.carimbo.get(it[0]) != it[1]]
        lote = mudou[:LIMITE_POR_CICLO]
        self.fila = len(mudou)
        with ThreadPoolExecutor(max_workers=24) as ex:
            for fut in [ex.submit(self._municipio, it) for it in lote]:
                try:
                    chave, carimbo, dados = fut.result()
                except Exception:  # noqa: BLE001  (fica para o próximo ciclo)
                    continue
                cdi = self.cd_ibge.get(chave)
                if cdi is not None:
                    with self.lock:
                        self.votos[cdi] = dados
                self.carimbo[chave] = carimbo
                self.fila -= 1
        self.ultimo, self.erro = time.time(), None

    def rodar(self):
        while True:
            t0 = time.time()
            try:
                self.ciclo()
            except Exception as e:  # noqa: BLE001
                self.erro = f"{type(e).__name__}: {e}"[:160]
            time.sleep(max(1.0, REFRESH_S - (time.time() - t0)))

    def copia(self) -> dict:
        with self.lock:
            return dict(self.votos)


@st.cache_resource
def coletor() -> Coletor:
    c = Coletor()
    threading.Thread(target=c.rodar, daemon=True, name="coletor-municipios").start()
    return c


def votos_demo(ufs: dict) -> dict:
    """Municípios fictícios: % da UF ± ruído, apuração da UF ± defasagem."""
    out = {}
    for cdi in geo_ids():
        uf = UF_IBGE.get(str(cdi)[:2])
        d = (ufs.get(uf) or {}).get("dados") if uf else None
        if cdi in LAGOAS or not d:
            continue
        rnd = random.Random(cdi)
        p22 = next((c["pct"] for c in d["cands"] if c["numero"] == "22"), 50.0)
        pa = max(4.0, min(96.0, p22 + rnd.gauss(0, 11)))
        pst = max(0.0, min(100.0, d["pst"] + rnd.uniform(-60, 35)))
        if pst > 0:
            out[cdi] = {"v": {"22": int(pa * 100), "13": int((100 - pa) * 100)}, "pst": pst}
    return out


def dados_mapa(votos: dict, num_a: str, num_b: str) -> tuple[list[int], list[int]]:
    pa, ap = [], []
    for cdi in geo_ids():
        m = votos.get(cdi)
        va = m["v"].get(num_a, 0) if m else 0
        vb = m["v"].get(num_b, 0) if m else 0
        pa.append(round(1000 * va / (va + vb)) if va + vb > 0 else -1)
        ap.append(round(10 * m["pst"]) if m else 0)
    return pa, ap


def escala(numero: str, partido_: str) -> list[str]:
    if numero in ESCALAS:
        return ESCALAS[numero]
    c = cor_partido(partido_)
    return [c, c + "CC", c + "99", c + "66"]


def html_lateral_mapa(an: dict, esq: dict, dir_: dict, pa: list[int], ap: list[int], status: str) -> str:
    ce, cd = escala(esq["numero"], esq["partido"]), escala(dir_["numero"], dir_["partido"])
    cont = {"e": [0] * 4, "d": [0] * 4, "n": 0}
    com_voto = completos = 0
    for p, a in zip(pa, ap):
        k = faixa(p)
        if k is None:
            continue
        com_voto += 1
        completos += a >= 1000
        if k == 4:
            cont["n"] += 1
        else:
            cont["e" if p > 500 else "d"][k] += 1
    total = len(geo_ids()) - len(LAGOAS)
    ve, vd = sum(cont["e"]), sum(cont["d"])

    def bloco(c, cores, nome):
        linhas = "".join(
            f'<div class="fx"><i style="background:{cores[k]}"></i><span>{FAIXAS[k]}</span><b>{fi(c[k])}</b></div>'
            for k in range(4))
        return f'<div class="lado"><h4 style="color:{cores[0]}">{escape(nome)}</h4>{linhas}</div>'

    d = an["d"]
    barra = "".join(
        f'<i style="flex:{n};background:{cor}"></i>'
        for n, cor in [(cont["e"][k], ce[k]) for k in range(4)] + [(cont["n"], NEUTRO)]
        + [(cont["d"][k], cd[k]) for k in reversed(range(4))] if n)
    return (
        f'<div class="lat">'
        f'<div class="lat-res"><div><span style="color:{ce[0]}">{escape(esq["nome"])}</span><b style="color:{ce[0]}">{fp(esq["pct"])}%</b></div>'
        f'<div><span style="color:{cd[0]}">{escape(dir_["nome"])}</span><b style="color:{cd[0]}">{fp(dir_["pct"])}%</b></div>'
        f'<small>{fp(d["pst"])}% das seções · diferença de {fi(an["dif"])} votos</small></div>'
        f'<div class="lat-num"><b>{fi(com_voto)}</b> de {fi(total)} municípios com votos'
        f'<small>{fi(completos)} com 100% das seções totalizadas</small></div>'
        f'<div class="lat-ven"><span style="color:{ce[0]}"><b>{fi(ve)}</b> {escape(esq["nome"].split()[0].title())}</span>'
        f'<span style="color:{NEUTRO}"><b>{fi(cont["n"])}</b> no limite</span>'
        f'<span style="color:{cd[0]}"><b>{fi(vd)}</b> {escape(dir_["nome"].split()[0].title())}</span></div>'
        f'<div class="lat-barra">{barra}</div>'
        f'<div class="lados">{bloco(cont["e"], ce, esq["nome"])}{bloco(cont["d"], cd, dir_["nome"])}</div>'
        f'<div class="fx neutro"><i style="background:{NEUTRO}"></i><span>De 50% + 1 voto a 51,3% (qualquer lado)</span><b>{fi(cont["n"])}</b></div>'
        f'<div class="fx"><i style="background:{SEM_DADO};outline:1px solid var(--linha)"></i><span>Sem votos totalizados</span><b>{fi(total - com_voto)}</b></div>'
        f'<p class="lat-nota">Cor = % do vencedor no município entre os votos válidos. {status}</p>'
        f'</div>')


# ───────────────────────── CORES ─────────────────────────
CORES_PARTIDO = {"PT": "#C0122D", "PL": "#0F4C81", "PSD": "#0054A6", "MDB": "#009959", "PSB": "#E41B23",
                 "UNIAO": "#00A0DF", "NOVO": "#FF6600", "PSOL": "#F2A134", "PDT": "#1E4080",
                 "REPUBLICANOS": "#005CA9", "PP": "#003366", "PSDB": "#004A94", "AVANTE": "#2EABB1"}
FUNDO = "#132F52"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(h):
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def cor_partido(sigla: str) -> str:
    """Cor do partido, clareada (mesmo tom) até ficar legível no fundo azul."""
    import colorsys
    k = unicodedata.normalize("NFKD", sigla or "").encode("ascii", "ignore").decode().upper()
    base = CORES_PARTIDO.get("".join(ch for ch in k if ch.isalnum()), "#C9D6E5")
    if _contraste(base, FUNDO) >= 3:
        return base
    r, g, b = (v / 255 for v in _rgb(base))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    for i in range(41):
        rr, gg, bb = colorsys.hls_to_rgb(h, l + (0.92 - l) * i / 40, s)
        c = "#" + "".join(f"{round(v * 255):02X}" for v in (rr, gg, bb))
        if _contraste(c, FUNDO) >= 3:
            return c
    return "#FFFFFF"


# ───────────────────────── VISUAL ─────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Barlow:wght@400;500;600&display=swap');
:root{--tinta:#0C2340;--painel:#132F52;--linha:#24476F;--tecla:#EEF2F6;--apagado:#8FA6C1;--ouro:#F5C542;--ok:#2BB673;--alerta:#F08A24;}
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"]{display:none!important;}
html, body, .stApp, [data-testid="stAppViewContainer"]{background:var(--tinta)!important;}
.block-container, [data-testid="stMainBlockContainer"]{padding:1.6vh 1.8vw!important;max-width:100%!important;}
[data-stale="true"], .stale-element{opacity:1!important;filter:none!important;transition:none!important;}

.tela{font-family:'Barlow',system-ui,sans-serif;color:var(--tecla);height:calc(100vh - 3.2vh - 7.6vh);
  display:flex;flex-direction:column;gap:1.4vh;}
.topo{display:flex;align-items:baseline;justify-content:space-between;border-bottom:2px solid var(--linha);padding-bottom:.8vh;}
.stApp{font-family:'Barlow',system-ui,sans-serif;color:var(--tecla);}
.st-key-topo{height:6.2vh;border-bottom:2px solid var(--linha);padding-bottom:.8vh!important;margin-bottom:1.4vh;
  box-sizing:border-box;align-items:center!important;flex-wrap:nowrap!important;gap:1.2vw!important;}
.st-key-topo [data-testid="stElementContainer"]{width:auto!important;}
.st-key-topo .st-key-relogio, .st-key-topo [data-testid="stLayoutWrapper"]:has(> .st-key-relogio){margin-left:auto!important;
  width:auto!important;flex:0 0 auto!important;}
div[class*="st-key-aba-"] button{background:transparent!important;border:1px solid var(--linha)!important;border-radius:99px!important;
  padding:.35vh 1.1vw!important;min-height:0!important;box-shadow:none!important;}
div[class*="st-key-aba-"] button p{font-family:'Barlow',sans-serif!important;font-weight:600!important;
  font-size:clamp(13px,1.9vh,26px)!important;color:var(--apagado)!important;line-height:1.2!important;}
div[class*="st-key-aba-"] button:hover{border-color:var(--apagado)!important;}
div[class*="st-key-aba-on-"] button{background:var(--tecla)!important;border-color:var(--tecla)!important;}
div[class*="st-key-aba-on-"] button p{color:var(--tinta)!important;}
.st-key-mapa iframe{height:calc(100vh - 3.2vh - 7.8vh)!important;width:100%!important;border:0;}
.lat{font-family:'Barlow',system-ui,sans-serif;color:var(--tecla);display:flex;flex-direction:column;gap:1.4vh;
  height:calc(100vh - 3.2vh - 7.8vh);overflow:hidden;}
.lat-res{background:var(--painel);border:1px solid var(--linha);border-radius:12px;padding:1.2vh 1vw;}
.lat-res div{display:flex;justify-content:space-between;align-items:baseline;font-family:'Barlow Condensed',sans-serif;
  font-weight:700;font-size:clamp(18px,3.4vh,48px);line-height:1.15;}
.lat-res b{font-weight:800;font-size:1.2em;font-variant-numeric:tabular-nums;}
.lat-res small, .lat-num small{display:block;color:var(--apagado);font-size:clamp(11px,1.6vh,22px);margin-top:.4vh;}
.lat-num{font-size:clamp(13px,2.1vh,30px);color:var(--apagado);}
.lat-num b{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.6em;color:var(--tecla);}
.lat-ven{display:flex;justify-content:space-between;font-size:clamp(12px,1.9vh,26px);}
.lat-ven b{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.5em;font-variant-numeric:tabular-nums;}
.lat-barra{display:flex;height:2.2vh;min-height:10px;border-radius:99px;overflow:hidden;background:var(--linha);}
.lados{display:grid;grid-template-columns:1fr 1fr;gap:1vw;}
.lado h4{margin:0 0 .6vh;padding:0;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(14px,2.4vh,34px);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fx{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:.6vw;font-size:clamp(11px,1.75vh,24px);
  padding:.35vh 0;}
.fx i{width:1.8vh;height:1.8vh;min-width:10px;min-height:10px;border-radius:4px;display:block;}
.fx span{color:var(--apagado);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fx b{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-variant-numeric:tabular-nums;}
.lat-nota{margin:auto 0 0;color:var(--apagado);font-size:clamp(10px,1.5vh,20px);line-height:1.35;}
.marca{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(26px,4.4vh,62px);line-height:1;}
.marca small{font-weight:500;color:var(--apagado);font-size:.55em;margin-left:.6em;}
.relogio{font-family:'Barlow Condensed',sans-serif;font-weight:600;font-size:clamp(18px,3.2vh,44px);color:var(--apagado);
  display:flex;align-items:center;gap:.5em;}
.vivo{width:.55em;height:.55em;border-radius:50%;background:var(--ok);animation:pulso 2s infinite;}
.vivo.off{background:var(--alerta);animation:none;}
@keyframes pulso{0%{box-shadow:0 0 0 0 rgba(43,182,115,.55)}70%{box-shadow:0 0 0 .7em rgba(43,182,115,0)}100%{box-shadow:0 0 0 0 rgba(43,182,115,0)}}

.corpo{flex:1;display:grid;grid-template-columns:minmax(0,1.75fr) minmax(0,1fr);grid-template-rows:minmax(0,1fr);gap:1.4vw;min-height:0;}
.esq{display:flex;flex-direction:column;gap:1.3vh;min-height:0;overflow:hidden;}

.status{border-radius:12px;padding:1.1vh 1.2vw;font-family:'Barlow Condensed',sans-serif;font-weight:700;
  font-size:clamp(18px,3.2vh,44px);line-height:1.1;background:var(--painel);border:1px solid var(--linha);}
.status small{display:block;font-family:'Barlow',sans-serif;font-weight:500;font-size:.5em;color:var(--apagado);margin-top:.3vh;}
.status.ganhou{background:linear-gradient(90deg,rgba(245,197,66,.22),rgba(245,197,66,.06));border-color:var(--ouro);color:var(--ouro);}
.status.ganhou small{color:var(--tecla);}

.duelo{display:grid;grid-template-columns:1fr 1fr;gap:1.2vw;}
.cand{--c:var(--tecla);background:var(--painel);border:1px solid var(--linha);border-top:6px solid var(--c);border-radius:12px;
  padding:1.4vh 1.2vw;display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:1vw;align-items:center;}
.cand.direita{grid-template-columns:minmax(0,1fr) auto;text-align:right;}
.cand.direita .foto{order:2;}
.foto{position:relative;width:clamp(56px,13vh,180px);aspect-ratio:3/4;border-radius:10px;background:var(--linha);
  border:3px solid var(--c);overflow:hidden;display:grid;place-items:center;font-family:'Barlow Condensed',sans-serif;
  font-weight:700;font-size:clamp(20px,4.6vh,64px);color:var(--apagado);}
.foto::after{content:"";position:absolute;inset:0;background-image:var(--foto);background-size:cover;background-position:center top;}
.cand.venceu .foto{box-shadow:0 0 2.2vh rgba(245,197,66,.6);}
.nome{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(22px,4.2vh,60px);line-height:1;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.meta{color:var(--apagado);font-size:clamp(12px,1.9vh,26px);margin-top:.3vh;}
.pct{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(46px,11vh,150px);line-height:.95;color:var(--c);
  font-variant-numeric:tabular-nums;margin-top:.4vh;}
.pct small{font-size:.4em;}
.votos{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(18px,3.4vh,48px);font-variant-numeric:tabular-nums;}
.votos small{font-family:'Barlow',sans-serif;font-weight:500;font-size:.5em;color:var(--apagado);}
.selo{display:inline-block;margin-top:.6vh;padding:.1em .6em;border-radius:6px;background:var(--ouro);color:var(--tinta);
  font-weight:700;font-size:clamp(12px,1.8vh,24px);}

.cabo{position:relative;display:flex;height:2.4vh;min-height:12px;border-radius:99px;overflow:hidden;background:var(--linha);}
.cabo i{display:block;height:100%;transition:width .8s ease;}
.cabo b{position:absolute;left:50%;top:-.4vh;bottom:-.4vh;width:3px;background:var(--tecla);transform:translateX(-50%);}

.nums{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.9vw;}
.num{background:var(--painel);border:1px solid var(--linha);border-radius:10px;padding:1vh .9vw;min-width:0;}
.num span{display:block;color:var(--apagado);font-size:clamp(11px,1.6vh,22px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.num b{display:block;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(20px,4vh,56px);line-height:1.05;
  font-variant-numeric:tabular-nums;white-space:nowrap;}
.num small{display:block;color:var(--apagado);font-size:clamp(10px,1.5vh,20px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.trilho{height:.7vh;min-height:4px;background:var(--linha);border-radius:99px;overflow:hidden;margin-top:.6vh;}
.trilho i{display:block;height:100%;background:var(--tecla);}

.prev{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.9vw;flex:1;min-height:0;overflow:hidden;}
.caixa{background:var(--painel);border:1px solid var(--linha);border-radius:10px;padding:1.1vh 1vw;min-height:0;
  display:flex;flex-direction:column;gap:.6vh;}
.caixa h3{margin:0;padding:0;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(16px,2.6vh,36px);color:var(--tecla);}
.caixa p{margin:0;color:var(--apagado);font-size:clamp(11px,1.6vh,22px);line-height:1.3;}
.lin{display:flex;justify-content:space-between;align-items:baseline;gap:1vw;font-family:'Barlow Condensed',sans-serif;
  font-weight:700;font-size:clamp(16px,3vh,42px);}
.lin span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.lin b{font-weight:800;font-variant-numeric:tabular-nums;color:var(--c);}
.grande{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(28px,6vh,84px);line-height:1;color:var(--c,var(--tecla));
  font-variant-numeric:tabular-nums;}

.ufs{background:var(--painel);border:1px solid var(--linha);border-radius:12px;padding:1vh .9vw;display:flex;flex-direction:column;min-height:0;overflow:hidden;}
.ufs h3{margin:0 0 .5vh;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(16px,2.6vh,36px);}
.ufl{display:grid;grid-template-columns:2.6em 4.2em minmax(0,1fr) minmax(0,1fr);column-gap:.7vw;align-items:baseline;
  padding:.12vh 0;border-bottom:1px solid var(--linha);font-size:clamp(11px,1.75vh,25px);font-variant-numeric:tabular-nums;}
.ufl span:not(:first-child){text-align:right;}
.ufl .sg{font-family:'Barlow Condensed',sans-serif;font-weight:800;}
.ufl .sd{font-family:'Barlow Condensed',sans-serif;font-weight:700;}
.ufl.cab{color:var(--apagado);font-size:clamp(10px,1.4vh,19px);border-bottom-color:var(--apagado);}
.ufl .est{color:var(--apagado);font-style:italic;}
.rolo{overflow-y:auto;min-height:0;}
.aviso{color:var(--alerta);}
.vazio{flex:1;display:grid;place-items:center;color:var(--apagado);font-size:clamp(16px,3vh,40px);text-align:center;}

@media (max-width:900px){
  .tela{height:auto;}
  .corpo{grid-template-columns:1fr;}
  .duelo,.prev{grid-template-columns:1fr;}
  .nums{grid-template-columns:repeat(2,minmax(0,1fr));}
}
</style>
"""


def fi(n) -> str:
    return f"{round(n):,}".replace(",", ".")


def fp(p: float, casas: int = 2) -> str:
    return f"{p:.{casas}f}".replace(".", ",")


def iniciais(nome: str) -> str:
    return "".join(p[0] for p in nome.split()[:2] if p[:1].isalpha()).upper() or "?"


def html_cand(c: dict, cor: str, lado: str, venceu: bool, selo: str) -> str:
    foto = f"--foto:url('{escape(c['foto'])}')" if c["foto"] else ""
    cor = OURO if venceu else cor
    return (f'<div class="cand {lado}{" venceu" if venceu else ""}" style="--c:{cor}">'
            f'<div class="foto" style="{foto}">{escape(iniciais(c["nome"]))}</div><div>'
            f'<div class="nome">{escape(c["nome"])}</div>'
            f'<div class="meta">{escape(c["partido"])} – {escape(c["numero"])}</div>'
            f'<div class="pct">{fp(c["pct"])}<small>%</small></div>'
            f'<div class="votos">{fi(c["votos"])}<small> votos</small></div>'
            f'{f"<span class=selo>{selo}</span>" if venceu and selo else ""}</div></div>')


def html_painel(an: dict, erro_nac: str | None) -> str:
    d, a, b = an["d"], an["a"], an["b"]
    # ordem fixa na tela (por número), para os candidatos não trocarem de lado quando houver virada
    esq_c, dir_c = sorted((a, b), key=lambda c: int(c["numero"] or 0))
    cores = {c["numero"]: cor_partido(c["partido"]) for c in (a, b)}
    ganhou = an["oficial"] or an["certeza"]
    selo = "ELEITO" if an["oficial"] else "MATEMATICAMENTE ELEITO"

    # ── faixa de status
    if an["oficial"]:
        status = (f'<div class="status ganhou">{escape(a["nome"])} — ELEITO (proclamado pelo TSE)'
                  f'<small>Vantagem de {fi(an["dif"])} votos com {fp(d["pst"])}% das seções totalizadas.</small></div>')
    elif an["certeza"]:
        status = (f'<div class="status ganhou">{escape(a["nome"])} está MATEMATICAMENTE ELEITO'
                  f'<small>A vantagem de {fi(an["dif"])} votos já é maior que todos os {fi(an["R"] + an["sj"])} votos que ainda '
                  f'podem entrar (eleitorado das seções não totalizadas + anulados sub judice). '
                  f'Nem que todos fossem para {escape(b["nome"])} haveria virada. O TSE ainda não proclamou.</small></div>')
    else:
        if an["R"] is None:
            falta = "Eleitorado das seções não totalizadas ainda indisponível no arquivo do TSE."
        else:
            falta = f'Ainda podem entrar até {fi(an["R"] + an["sj"])} votos.'
        status = (f'<div class="status">Em apuração — {escape(a["nome"])} lidera por {fi(an["dif"])} votos'
                  f'<small>{falta}</small></div>')

    duelo = (f'<div class="duelo">'
             f'{html_cand(esq_c, cores[esq_c["numero"]], "", ganhou and esq_c is a, selo)}'
             f'{html_cand(dir_c, cores[dir_c["numero"]], "direita", ganhou and dir_c is a, selo)}</div>')
    pe = esq_c["pct"] / max(0.01, esq_c["pct"] + dir_c["pct"]) * 100
    cabo = (f'<div class="cabo"><i style="width:{pe:.2f}%;background:{cores[esq_c["numero"]]}"></i>'
            f'<i style="width:{100 - pe:.2f}%;background:{cores[dir_c["numero"]]}"></i><b></b></div>')

    # ── números
    tot, total = d["secoes"]
    ap_e = 100 * d["eleitorado_tot"] / d["eleitorado"] if d["eleitorado"] else None
    rest = "—" if an["R"] is None else fi(an["R"])
    nums = (
        f'<div class="nums">'
        f'<div class="num"><span>Seções totalizadas</span><b>{fp(d["pst"])}%</b>'
        f'<small>{fi(tot)} de {fi(total)}</small><div class="trilho"><i style="width:{min(100, d["pst"]):.2f}%"></i></div></div>'
        f'<div class="num"><span>Eleitorado apurado</span><b>{"—" if ap_e is None else fp(ap_e) + "%"}</b>'
        f'<small>{fi(d["eleitorado_tot"])} de {fi(d["eleitorado"])} aptos</small>'
        f'<div class="trilho"><i style="width:{min(100, ap_e or 0):.2f}%"></i></div></div>'
        f'<div class="num" style="--c:{cores[a["numero"]]}"><span>Diferença</span><b style="color:{OURO if ganhou else cores[a["numero"]]}">{fi(an["dif"])}</b>'
        f'<small>{fp(an["dif_pp"])} p.p. · {fi(d["validos"])} válidos</small></div>'
        f'<div class="num"><span>Ainda podem entrar (máx.)</span><b>{rest}</b>'
        f'<small>{"+ " + fi(an["sj"]) + " sub judice" if an["sj"] else "eleitores de seções não totalizadas"}</small></div>'
        f'</div>')

    # ── o que o 2º colocado precisa
    def txt_virar(p):
        if p is None:
            return "—", "sem dado de eleitorado"
        if p > 100:
            return "impossível", "precisaria de mais de 100%"
        return f"{fp(p, 1)}%", "dos votos restantes"
    v_est, s_est = txt_virar(an["virar_est"])
    v_max, s_max = txt_virar(an["virar_max"])
    cor_b = cores[b["numero"]]
    virar = (f'<div class="caixa"><h3>Para virar, {escape(b["nome"])} precisaria de</h3>'
             f'<div class="grande" style="--c:{cor_b}">{v_est}</div>'
             f'<p>{s_est} (estimativa: mantido o comparecimento válido de até agora). '
             f'Se todos os eleitores que faltam votassem: <b style="color:var(--tecla)">{v_max}</b>.</p>'
             f'<p>Quando esse número passa de 100% mesmo no pior caso, o resultado está decidido.</p></div>')

    # ── projeção
    pj = an["proj"]
    if pj["pct"]:
        ordem = sorted(pj["pct"].items(), key=lambda kv: -kv[1])
        nomes = {c["numero"]: c["nome"] for c in (a, b)}
        linhas = "".join(
            f'<div class="lin" style="--c:{cores.get(k, "#C9D6E5")}"><span>{escape(nomes.get(k, k))}</span>'
            f'<b>{fp(p)}%</b></div>' for k, p in ordem[:2])
        dif_proj = (pj["votos"].get(ordem[0][0], 0) - pj["votos"].get(ordem[1][0], 0)) if len(ordem) > 1 else 0
        extra = (f' UFs sem votos ainda (estimadas pela média): {", ".join(u.upper() for u in pj["faltando"])}.'
                 if pj["faltando"] else "")
        projecao = (f'<div class="caixa"><h3>Projeção para 100% das urnas</h3>{linhas}'
                    f'<p>Diferença projetada: <b style="color:var(--tecla)">{fi(dif_proj)}</b> votos · '
                    f'{fi(pj["validos"])} válidos. Mantém o % de cada um em cada UF e escala pelo eleitorado que falta.'
                    f'{extra}</p></div>')
    else:
        projecao = '<div class="caixa"><h3>Projeção para 100% das urnas</h3><p>Aguardando dados das UFs…</p></div>'

    aviso = f'<p class="aviso">Sem conexão com o TSE — mostrando a última leitura ({escape(erro_nac)})</p>' if erro_nac else ""
    return (f'<div class="esq">{status}{duelo}{cabo}{nums}<div class="prev">{virar}{projecao}</div>{aviso}</div>'
            f'{html_ufs(an)}')


def html_ufs(an: dict) -> str:
    a, b = an["a"], an["b"]
    ca, cb = cor_partido(a["partido"]), cor_partido(b["partido"])
    linhas = sorted(an["proj"]["linhas"],
                    key=lambda l: -(l["proj"].get(a["numero"], 0) - l["proj"].get(b["numero"], 0)))
    corpo = []
    for l in linhas:
        s_ag = l["agora"].get(a["numero"], 0) - l["agora"].get(b["numero"], 0)
        s_pj = l["proj"].get(a["numero"], 0) - l["proj"].get(b["numero"], 0)
        sg = "EXT" if l["uf"] == "zz" else l["uf"].upper()
        ap = '<span class="est">estimada</span>' if l.get("estimada") else f'{fp(l["pst"], 1)}%'
        ag = "—" if l.get("estimada") else f'{"+" if s_ag >= 0 else "−"}{fi(abs(s_ag))}'
        corpo.append(
            f'<div class="ufl"><span class="sg">{sg}</span><span>{ap}</span>'
            f'<span class="sd" style="color:{ca if s_ag >= 0 else cb}">{ag}</span>'
            f'<span class="sd" style="color:{ca if s_pj >= 0 else cb}">{"+" if s_pj >= 0 else "−"}{fi(abs(s_pj))}</span></div>')
    pa, pb = a["nome"].split()[0].title(), b["nome"].split()[0].title()
    return (f'<div class="ufs"><h3>Saldo por UF ({escape(pa)} × {escape(pb)})</h3>'
            f'<div class="ufl cab"><span>UF</span><span>Apurado</span><span>Saldo agora</span><span>Saldo projetado</span></div>'
            f'<div class="rolo">{"".join(corpo)}</div></div>')


def compactar(html: str) -> str:
    return re.sub(r"\n\s*", "", html)


# ───────────────────────── DIAGNÓSTICO ─────────────────────────
def tela_diagnostico():
    st.markdown("<style>.stApp *{color:#EEF2F6}</style>", unsafe_allow_html=True)
    st.title("Diagnóstico — 2º turno (eleição 6258)")
    for uf in ["br", "sp", "se"]:
        st.subheader(uf.upper())
        for u in urls(uf):
            try:
                r = requests.get(u, headers=HEADERS, timeout=6)
                st.write(f"`{u}` → HTTP {r.status_code}, {len(r.content)} bytes")
                if r.ok:
                    obj = decodificar(r.text)
                    st.write("Chaves do topo:", list(obj.keys())[:40] if isinstance(obj, dict) else type(obj).__name__)
                    d = ler(obj, uf)
                    st.json({k: v for k, v in d.items() if k != "cands"})
                    st.json(d["cands"][:2])
                    break
            except Exception as e:  # noqa: BLE001
                st.write(f"`{u}` → {type(e).__name__}: {e}")


# ───────────────────────── PÁGINA ─────────────────────────
st.set_page_config(page_title="Apuração 2026 — 2º turno", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
DEMO = st.query_params.get("demo") in ("1", "true", "sim")
DEBUG = st.query_params.get("debug") in ("1", "true", "sim")


def ir_para(aba: str):
    st.session_state.aba = aba


def cabecalho(erro: bool, rotulo: str):
    aba = st.session_state.get("aba", "painel")
    with st.container(key="topo", horizontal=True, vertical_alignment="center"):
        st.markdown(f'<div class="marca">Apuração 2026<small>2º turno · Presidente'
                    f'{" — demonstração" if DEMO else ""}</small></div>', unsafe_allow_html=True)
        for chave, texto in (("painel", "Painel"), ("mapa", "Mapa")):
            st.button(texto, key=f"aba-{'on' if aba == chave else 'off'}-{chave}", on_click=ir_para, args=(chave,))
        with st.container(key="relogio"):
            st.markdown(f'<div class="relogio"><span class="vivo {"off" if erro else ""}"></span>{rotulo}</div>',
                        unsafe_allow_html=True)


def visao_mapa(an: dict, ufs: dict):
    esq, dir_ = sorted((an["a"], an["b"]), key=lambda c: int(c["numero"] or 0))
    if DEMO:
        votos, status = votos_demo(ufs), "Modo demonstração: municípios fictícios."
    else:
        col = coletor()
        votos = col.copia()
        if col.erro:
            status = f'<span class="aviso">Falha na última leitura: {escape(col.erro)}</span>'
        elif col.fila > 0:
            status = f"Atualizando: {fi(col.fila)} municípios na fila."
        else:
            status = "Atualiza sozinho conforme o TSE totaliza cada município."
    pa, ap = dados_mapa(votos, esq["numero"], dir_["numero"])
    c1, c2 = st.columns([1.75, 1], gap="medium")
    with c1, st.container(key="mapa"):
        _componente_mapa(pa=pa, ap=ap, altura=900, key="mapa-br", default=None,
                         a={"nome": esq["nome"], "cores": escala(esq["numero"], esq["partido"])},
                         b={"nome": dir_["nome"], "cores": escala(dir_["numero"], dir_["partido"])})
    with c2:
        st.markdown(compactar(html_lateral_mapa(an, esq, dir_, pa, ap, status)), unsafe_allow_html=True)


@st.fragment(run_every=REFRESH_S)
def painel():
    if not DEMO:
        coletor()                     # deixa o mapa municipal carregando em segundo plano
    nac, ufs = carregar_demo() if DEMO else carregar()
    an = analisar(nac, ufs)
    erro = bool(nac["erro"]) or any(b["erro"] for b in ufs.values())
    hora = (nac["dados"] or {}).get("atualizado", "").split(" ")[-1]
    rotulo = f"TSE {hora}" if hora else datetime.now(TZ).strftime("%H:%M:%S")
    cabecalho(erro, rotulo)
    if not an:
        st.markdown(f'<div class="tela"><div class="vazio"><div>Aguardando dados do TSE…<br>'
                    f'<span class="aviso">{escape(nac["erro"] or "")}</span></div></div></div>', unsafe_allow_html=True)
        return
    if st.session_state.get("aba", "painel") == "mapa":
        visao_mapa(an, ufs)
    else:
        st.markdown(compactar(f'<div class="tela"><div class="corpo">{html_painel(an, nac["erro"])}</div></div>'),
                    unsafe_allow_html=True)


if DEBUG:
    tela_diagnostico()
else:
    painel()
