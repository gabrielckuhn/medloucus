"""Leitura dos arquivos públicos de resultado do TSE (eleição 2026, 2º turno presidencial)
e coletor municipal em segundo plano."""
from __future__ import annotations

import base64
import gzip
import json
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests
import streamlit as st


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
    e_ = corpo.get("e") if isinstance(corpo, dict) and isinstance(corpo.get("e"), dict) else {}
    v_ = corpo.get("v") if isinstance(corpo, dict) and isinstance(corpo.get("v"), dict) else {}
    return {
        "comparecimento": int(num(e_.get("c"))),
        "brancos_nulos": int(num(v_.get("vb")) + num(v_.get("tvn") or v_.get("vn"))),
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


LIMITE_POR_CICLO = 1200          # municípios baixados por ciclo (o 1º carregamento leva ~1 min)


class Coletor:
    """Roda em segundo plano (uma vez por servidor). A cada ciclo lê o andamento de cada UF
    ({uf}-e006258-ab.jws, com a hora da última totalização de cada município) e baixa só os
    municípios que mudaram ({uf}{mun}-c0001-e006258-u.jws)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.votos: dict[int, dict] = {}     # código IBGE → {"v": {número: votos}, "pst": %}
        self.carimbo: dict = {}              # (uf, cód. TSE) → (data, hora, seções) da última leitura
        self.cd_ibge: dict = {}              # (uf, cód. TSE) → código IBGE
        self.andamento: dict[int, dict] = {} # código IBGE → {"te", "est", "pst"} de todos os municípios
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
            s_, e_ = a.get("s") or {}, a.get("e") or {}
            cdi = self.cd_ibge.get((uf, str(a.get("cdabr"))))
            if cdi is not None:
                self.andamento[cdi] = {"te": int(num(e_.get("te"))), "est": int(num(e_.get("est"))),
                                       "pst": num(s_.get("pst"))}
            if num(s_.get("st")) <= 0:                   # nenhuma seção totalizada ainda
                continue
            out.append(((uf, str(a.get("cdabr"))), (a.get("dt"), a.get("ht"), s_.get("st"))))
        return out

    def _municipio(self, item):
        (uf, cd), carimbo = item
        d = ler(self._get(f"{BASE}/{ELE}/dados/{uf}/{uf}{cd}-c{CARGO:04d}-e{ELE:06d}-u.jws"), uf)
        return (uf, cd), carimbo, {"v": {c["numero"]: c["votos"] for c in d["cands"] if not sub_judice(c)},
                                   "pst": d["pst"], "te": d["eleitorado"], "est": d["eleitorado_tot"],
                                   "c": d["comparecimento"], "bn": d["brancos_nulos"]}

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

    def copia(self) -> tuple[dict, dict]:
        with self.lock:
            return dict(self.votos), dict(self.andamento)


@st.cache_resource
def coletor() -> Coletor:
    c = Coletor()
    threading.Thread(target=c.rodar, daemon=True, name="coletor-municipios").start()
    return c

