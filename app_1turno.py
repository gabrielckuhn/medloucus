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
import re
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


def achar_num(d, chaves: tuple[str, ...]) -> float:
    """Primeiro valor numérico (> 0) de uma das chaves, em qualquer nível — ignorando os candidatos."""
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


def calcular_totais(corpo, cands: list, pst: float) -> dict:
    """Totais da abrangência (UF ou Brasil) e o máximo de votos que ainda pode entrar."""
    sub_judice_cands = sum(c["votos"] for c in cands if "sub judice" in c["situacao"].lower())
    validos_cands = sum(c["votos"] for c in cands if "sub judice" not in c["situacao"].lower())
    eleitorado = achar_num(corpo, ("te", "eleitorado"))            # eleitorado apto total
    eleitorado_tot = achar_num(corpo, ("est", "ea"))               # apto das seções já totalizadas
    validos = max(achar_num(corpo, ("vv",)), validos_cands)
    sub_judice = max(achar_num(corpo, ("vansj",)), sub_judice_cands)
    if pst >= 100:
        restante = 0.0                                             # todas as seções totalizadas
    elif eleitorado and eleitorado_tot and eleitorado >= eleitorado_tot:
        restante = eleitorado - eleitorado_tot                     # cada eleitor que falta votando válido
    else:
        restante = None                                            # sem dado → não dá para garantir nada
    return {"eleitorado": int(eleitorado), "eleitorado_totalizado": int(eleitorado_tot),
            "validos": int(validos), "sub_judice": int(sub_judice),
            "restante_max": None if restante is None else int(restante)}


def maioria_garantida(cands: list, tot: dict) -> bool:
    """Eleito no 1º turno com certeza matemática (CF art. 77 §2º: mais da metade dos votos válidos,
    sem brancos e nulos). Pior caso: todo eleitor das seções que faltam vota válido em outro
    candidato e todo voto 'anulado sub judice' é revalidado para outro candidato."""
    if not cands or tot["restante_max"] is None:
        return False
    lider = cands[0]
    if "sub judice" in lider["situacao"].lower():
        return False
    validos_max = tot["validos"] + tot["sub_judice"] + tot["restante_max"]
    return validos_max > 0 and 2 * lider["votos"] > validos_max


def normalizar(raw, chave: str, ele: int, uf: str, maioria: bool = False) -> dict:
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
            "nome": str(c.get("nmu") or c.get("nmurna") or c.get("nu") or nome_tab or c.get("nm") or f"Candidato {numero}"),
            "numero": numero,
            "partido": partido(c) or part_tab,
            "votos": int(num(c.get("vap"))),
            "pct": num(c.get("pvap")),
            "situacao": str(c.get("st") or ""),
            "eleito": str(c.get("e") or "").lower() == "s",
            "foto": url_foto(ele, uf, str(c.get("sqcand"))) if c.get("sqcand") else "",
        })
    cands.sort(key=lambda x: (x["votos"], x["pct"]), reverse=True)

    totais = calcular_totais(corpo, cands, pst)
    if maioria and maioria_garantida(cands, totais) and not cands[0]["eleito"]:
        cands[0]["eleito_calc"] = True     # eleito pelo cálculo, antes da proclamação do TSE

    d_h = achar_dict_com(raw, "hg") or achar_dict_com(raw, "ht") or {}
    hora = d_h.get("hg") or d_h.get("ht") or ""
    data = d_h.get("dg") or d_h.get("dt") or ""
    return {
        "pst": pst,
        "secoes": (int(totalizadas), int(total)),
        "atualizado": f"{data} {hora}".strip(),
        "top": cands[:20],
        "totais": totais,
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
                dados = normalizar(raw, chave, ele, uf, maioria=chave in ("pres", "gov"))
                mem["dados"][chave] = dados
                return chave, dados, None
            except Exception as e:  # noqa: BLE001
                erros = [f"leitura: {type(e).__name__} {e}"]
        return chave, mem["dados"].get(chave), (erros[0] if erros else "erro")

    with ThreadPoolExecutor(max_workers=4) as ex:
        return {chave: {"dados": d, "erro": e} for chave, d, e in ex.map(um, CARGOS)}


# ───────────────────────── VISÃO POR ESTADO ─────────────────────────
UFS = [
    ("ac", "Acre"), ("al", "Alagoas"), ("ap", "Amapá"), ("am", "Amazonas"), ("ba", "Bahia"),
    ("ce", "Ceará"), ("df", "Distrito Federal"), ("es", "Espírito Santo"), ("go", "Goiás"),
    ("ma", "Maranhão"), ("mt", "Mato Grosso"), ("ms", "Mato Grosso do Sul"), ("mg", "Minas Gerais"),
    ("pa", "Pará"), ("pb", "Paraíba"), ("pr", "Paraná"), ("pe", "Pernambuco"), ("pi", "Piauí"),
    ("rj", "Rio de Janeiro"), ("rn", "Rio Grande do Norte"), ("rs", "Rio Grande do Sul"),
    ("ro", "Rondônia"), ("rr", "Roraima"), ("sc", "Santa Catarina"), ("sp", "São Paulo"),
    ("se", "Sergipe"), ("to", "Tocantins"),
]
# cargo da visão por estado → (rótulo, eleição, código do cargo, inclui exterior?)
CARGOS_UF = {
    "pres": ("Presidente", ELE_FEDERAL, 1, True),
    "gov": ("Governador", ELE_ESTADUAL, 3, False),
    "sen": ("Senador", ELE_ESTADUAL, 5, False),
}


def carregar_estados(cargo: str) -> dict:
    """Baixa o cargo escolhido em todas as UFs (em paralelo). Volta {uf: {"dados", "erro"}}."""
    _, ele, cod, exterior = CARGOS_UF[cargo]
    ufs = [u for u, _ in UFS] + (["zz"] if exterior else [])
    mem = ultimo_bom().setdefault("ufs", {})

    def um(uf):
        chave_mem = f"{cargo}-{uf}"
        _, raw, erros = baixar_cargo((chave_mem, "", "", ele, uf, cod))
        if raw is not None:
            try:
                tabela = "pres" if cargo == "pres" else (cargo if uf == UF else "-")
                dados = normalizar(raw, tabela, ele, uf, maioria=(cargo == "gov"))
                mem[chave_mem] = dados
                return uf, dados, None
            except Exception as e:  # noqa: BLE001
                erros = [f"{type(e).__name__}"]
        return uf, mem.get(chave_mem), (erros[0] if erros else "erro")

    with ThreadPoolExecutor(max_workers=14) as ex:
        return {uf: {"dados": d, "erro": e} for uf, d, e in ex.map(um, ufs)}


# eleitorado aproximado (só para o modo demo; os dados reais vêm do TSE)
ELEITORADO_DEMO = {
    "sp": 34_700_000, "mg": 16_300_000, "rj": 12_800_000, "ba": 11_300_000, "rs": 8_600_000, "pr": 8_500_000,
    "pe": 7_000_000, "ce": 6_800_000, "pa": 6_100_000, "sc": 5_500_000, "ma": 5_000_000, "go": 4_900_000,
    "pb": 3_000_000, "es": 2_900_000, "am": 2_600_000, "pi": 2_600_000, "mt": 2_500_000, "rn": 2_500_000,
    "al": 2_300_000, "df": 2_200_000, "ms": 2_000_000, "se": 1_740_000, "ro": 1_200_000, "to": 1_100_000,
    "zz": 700_000, "ac": 600_000, "ap": 550_000, "rr": 370_000,
}


def carregar_estados_demo(cargo: str) -> dict:
    rnd = random.Random(42 + len(cargo))
    _, _, _, exterior = CARGOS_UF[cargo]
    ufs = [u for u, _ in UFS] + (["zz"] if exterior else [])
    t = (time.time() / REFRESH_S) % 200
    falsos = [("CANDIDATA ALFA", "11", "PP"), ("CANDIDATO BETA", "13", "PT"), ("CANDIDATO GAMA", "55", "PSD"),
              ("CANDIDATA DELTA", "44", "UNIÃO"), ("CANDIDATO ÉPSILON", "15", "MDB"), ("CANDIDATO ZETA", "22", "PL")]
    out = {}
    for uf in ufs:
        if cargo == "pres":
            a, b = ("FLAVIO BOLSONARO", "22", "PL"), ("LULA", "13", "PT")
            if rnd.random() < 0.45:
                a, b = b, a
        else:
            a, b = rnd.sample(falsos, 2)
        pa = rnd.uniform(38, 58)
        pb = rnd.uniform(25, min(pa - 1, 96 - pa))
        pc_resto = 100 - pa - pb
        pst = min(100.0, rnd.uniform(10, 40) + t * 0.4)
        eleit = ELEITORADO_DEMO.get(uf, 1_000_000)
        eleit_tot = int(eleit * pst / 100)
        validos = int(eleit_tot * 0.76)
        trio = ((a, pa), (b, pb), (("OUTROS (DEMO)", "70", "AVANTE"), pc_resto))
        top = [{"nome": n, "numero": num_, "partido": p, "pct": pc,
                "votos": int(validos * pc / 100), "situacao": "", "eleito": False, "foto": ""}
               for (n, num_, p), pc in trio]
        totais = {"eleitorado": eleit, "eleitorado_totalizado": eleit_tot, "validos": validos,
                  "sub_judice": 0, "restante_max": eleit - eleit_tot}
        out[uf] = {"dados": {"pst": pst, "secoes": (0, 0), "atualizado": "", "top": top, "totais": totais},
                   "erro": None}
    return out


def projetar(blocos: dict) -> dict:
    """Projeção do 1º turno presidencial para 100% das urnas.

    Em cada UF, mantém o % de cada candidato e escala os votos válidos já apurados pelo
    eleitorado: fator = eleitorado apto total / eleitorado apto das seções totalizadas
    (se faltar esse dado, usa 100 / % de seções). UFs ainda sem votos entram com o
    eleitorado × taxa nacional de votos válidos, divididos pelo % nacional atual.
    """
    cands, ufs = {}, []
    soma_validos_agora = soma_validos_proj = 0.0
    soma_eleit = soma_eleit_tot = 0.0
    sem_dado = []

    def chave_c(c):
        return c["numero"] or c["nome"]

    for uf, bloco in blocos.items():
        d = bloco["dados"]
        tot = (d or {}).get("totais") or {}
        validos_c = [c for c in (d or {}).get("top", []) if "sub judice" not in c["situacao"].lower()]
        validos = float(sum(c["votos"] for c in validos_c))
        eleit, eleit_tot = float(tot.get("eleitorado") or 0), float(tot.get("eleitorado_totalizado") or 0)
        if eleit_tot > 0 and eleit >= eleit_tot:
            fator = eleit / eleit_tot
        elif d and d["pst"] > 0:
            fator = 100.0 / d["pst"]
        else:
            fator = None
        if not validos or fator is None:
            sem_dado.append((uf, eleit))
            continue
        soma_eleit += eleit
        soma_eleit_tot += eleit_tot
        soma_validos_agora += validos
        soma_validos_proj += validos * fator
        linha = {"uf": uf, "pst": d["pst"], "fator": fator, "validos_proj": validos * fator, "votos": {}}
        for c in validos_c:
            k = chave_c(c)
            reg = cands.setdefault(k, {"nome": c["nome"], "partido": c["partido"], "numero": c["numero"],
                                       "agora": 0.0, "proj": 0.0})
            reg["agora"] += c["votos"]
            reg["proj"] += c["votos"] * fator
            linha["votos"][k] = c["votos"] * fator
        ufs.append(linha)

    # UFs sem nenhum voto ainda: estimativa pela média nacional
    if sem_dado and soma_validos_agora:
        taxa_validos = soma_validos_agora / soma_eleit_tot if soma_eleit_tot else 0
        for uf, eleit in sem_dado:
            if not (eleit and taxa_validos):
                continue
            v = eleit * taxa_validos
            soma_validos_proj += v
            soma_eleit += eleit
            linha = {"uf": uf, "pst": 0.0, "fator": None, "validos_proj": v, "votos": {}, "estimada": True}
            for k, reg in cands.items():
                share = reg["agora"] / soma_validos_agora
                reg["proj"] += v * share
                linha["votos"][k] = v * share
            ufs.append(linha)

    ranking = sorted(cands.items(), key=lambda kv: -kv[1]["proj"])
    for _, reg in ranking:
        reg["pct_proj"] = 100 * reg["proj"] / soma_validos_proj if soma_validos_proj else 0
        reg["pct_agora"] = 100 * reg["agora"] / soma_validos_agora if soma_validos_agora else 0
    return {
        "ranking": ranking, "ufs": ufs, "validos_proj": soma_validos_proj, "validos_agora": soma_validos_agora,
        "eleitorado_apurado": 100 * soma_eleit_tot / soma_eleit if soma_eleit else 0,
        "ufs_sem_dado": [u for u, _ in sem_dado],
    }


def html_projecao(proj: dict) -> str:
    ranking = proj["ranking"]
    if not ranking:
        return '<div class="vazio" style="height:60vh">Ainda não há votos suficientes para projetar.</div>'
    lider_k, lider = ranking[0]
    if lider["pct_proj"] > 50:
        veredito = f'<b style="color:{opcoes_cor(lider["partido"])[0]}">{escape(lider["nome"])}</b> venceria no 1º turno'
    elif len(ranking) > 1:
        seg = ranking[1][1]
        veredito = (f'2º turno entre <b style="color:{opcoes_cor(lider["partido"])[0]}">{escape(lider["nome"])}</b> '
                    f'e <b style="color:{opcoes_cor(seg["partido"])[0]}">{escape(seg["nome"])}</b>')
    else:
        veredito = ""
    maior = max(r["pct_proj"] for _, r in ranking) or 1
    linhas = []
    for k, r in ranking[:8]:
        cor = opcoes_cor(r["partido"])[0]
        var = r["pct_proj"] - r["pct_agora"]
        linhas.append(
            f'<div class="pj-lin" style="--c:{cor}">'
            f'<div class="pj-nm">{escape(r["nome"])}<small>{escape(r["partido"])} – {escape(r["numero"])}</small></div>'
            f'<div class="pj-pc">{fmt_pct(r["pct_proj"])}<small>%</small></div>'
            f'<div class="pj-barra"><i style="width:{min(100, r["pct_proj"]):.2f}%"></i><b style="left:50%"></b></div>'
            f'<div class="pj-vt">{fmt_int(round(r["proj"]))} votos projetados'
            f'<span>agora {fmt_pct(r["pct_agora"])}% ({"+" if var >= 0 else "−"}{fmt_pct(abs(var))} p.p.)</span></div>'
            f'</div>')

    # saldo por UF entre os dois primeiros da projeção
    tabela = ""
    if len(ranking) > 1:
        k1, r1 = ranking[0]
        k2, r2 = ranking[1]
        c1, c2 = opcoes_cor(r1["partido"])[0], opcoes_cor(r2["partido"])[0]
        ufs = sorted(proj["ufs"], key=lambda u: -(u["votos"].get(k1, 0) - u["votos"].get(k2, 0)))
        cab = (f'<div class="pj-uf cabeca"><span>UF</span><span>Apurado</span><span>Válidos proj.</span>'
               f'<span>Saldo {escape(r1["nome"].split()[0].title())} × {escape(r2["nome"].split()[0].title())}</span></div>')
        corpo = []
        for u in ufs:
            saldo = u["votos"].get(k1, 0) - u["votos"].get(k2, 0)
            cor = c1 if saldo >= 0 else c2
            sg = "EXT" if u["uf"] == "zz" else u["uf"].upper()
            ap = "estimada" if u.get("estimada") else f'{fmt_pct(u["pst"])}%'
            corpo.append(f'<div class="pj-uf"><span class="sg">{sg}</span><span>{ap}</span>'
                         f'<span>{fmt_int(round(u["validos_proj"]))}</span>'
                         f'<span class="sd" style="color:{cor}">{"+" if saldo >= 0 else "−"}{fmt_int(round(abs(saldo)))}</span></div>')
        tabela = f'<div class="pj-tab">{cab}<div class="pj-rolo">{"".join(corpo)}</div></div>'

    nota = (f'Mantém o % de cada candidato em cada UF e escala os votos válidos pelo eleitorado que falta apurar. '
            f'Eleitorado já apurado: {fmt_pct(proj["eleitorado_apurado"])}%. '
            f'Válidos projetados no país: {fmt_int(round(proj["validos_proj"]))}.')
    if proj["ufs_sem_dado"]:
        nota += f' Sem votos ainda (estimadas pela média nacional): {", ".join(u.upper() for u in proj["ufs_sem_dado"])}.'
    nota += ' É uma estimativa: as seções que faltam em cada UF podem votar diferente das já apuradas.'
    return (f'<div class="pj"><div class="pj-esq"><div class="pj-ver">Projeção para 100% das urnas: {veredito}</div>'
            f'{"".join(linhas)}<div class="pj-nota">{escape(nota)}</div></div>{tabela}</div>')


def alternar_projecao():
    st.session_state.proj = not st.session_state.get("proj", False)


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
                    st.json(normalizar(obj, chave, ele, uf, maioria=chave in ("pres", "gov")))
                    break
            except Exception as e:  # noqa: BLE001
                st.write(f"`{u}` → {type(e).__name__}: {e}")


# ───────────────────────── MODO DEMO ─────────────────────────
DEMO_BASE = {
    "pres": [("FLAVIO BOLSONARO", "22", "PL", 51.07), ("LULA", "13", "PT", 40.82),
             ("ESCRITOR AUGUSTO CURY", "70", "AVANTE", 2.94)],
    "gov": [("FÁBIO", "55", "PSD", 58.77), ("VALMIR DE FRANCISQUINHO", "10", "REPUBLICANOS", 36.71),
            ("DR. HELTON", "50", "PSOL", 4.27)],
    "sen": [("ROGERIO CARVALHO", "131", "PT", 20.65), ("DELEGADO ALESSANDRO", "155", "MDB", 18.19),
            ("DELEGADO ANDRÉ DAVID", "101", "REPUBLICANOS", 17.87)],
    "depf": [("CLAUDIO MITIDIERI", "4040", "PSB", 7.89), ("JOAO DANIEL", "1311", "PT", 7.68),
             ("YANDRA MOURA", "4444", "UNIÃO", 6.93)],
}


def carregar_demo() -> dict:
    t = (time.time() / REFRESH_S) % 200
    pst_br, pst_se = min(100.0, 21.96 + t * 0.4), min(100.0, 18.59 + t * 0.45)
    agora = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
    out = {}
    for chave, *_ in CARGOS:
        pst = pst_br if chave == "pres" else pst_se
        base_votos = 120_000_000 if chave == "pres" else 1_100_000
        lista = list(DEMO_BASE[chave])
        ja = {n for _, n, _, _ in lista}
        ultimo = lista[-1][3]
        for n, (nome, p) in NOMES[chave].items():   # completa com os nomes conhecidos
            if n not in ja and len(lista) < 20:
                ultimo *= 0.82
                lista.append((nome, n, p, ultimo))
        top = []
        for nome, n, p, pct in lista:
            pct_j = max(0.0, pct + random.uniform(-0.25, 0.25) * min(1.0, pct / 5))
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

.stApp, .stApp p{font-family:'Barlow',system-ui,sans-serif;color:var(--tecla);}
:root{
  --topo:7.4vh;                                   /* altura do cabeçalho + respiro */
  --area:calc(100vh - 3.2vh - var(--topo));       /* altura útil para os quadros */
  --vgap:1.4vh;
}

.topo{display:flex;align-items:baseline;justify-content:space-between;height:6vh;box-sizing:border-box;
  border-bottom:2px solid var(--linha);padding-bottom:.8vh;margin-bottom:calc(var(--topo) - 6vh);}
.marca{font-family:'Barlow Condensed',sans-serif;font-weight:800;margin:0;padding:0;
  font-size:clamp(28px,4.6vh,64px);letter-spacing:.01em;color:var(--tecla);line-height:1;}
.marca small{font-weight:500;color:var(--apagado);font-size:.55em;margin-left:.6em;}
.relogio{font-family:'Barlow Condensed',sans-serif;font-size:clamp(20px,3.4vh,48px);
  font-weight:600;color:var(--apagado);display:flex;align-items:center;gap:.5em;}
.vivo{display:inline-block;width:.55em;height:.55em;border-radius:50%;background:var(--confirma);
  box-shadow:0 0 0 0 rgba(43,182,115,.6);animation:pulso 2s infinite;}
.vivo.off{background:var(--corrige);animation:none;}
@keyframes pulso{0%{box-shadow:0 0 0 0 rgba(43,182,115,.55)}70%{box-shadow:0 0 0 .7em rgba(43,182,115,0)}100%{box-shadow:0 0 0 0 rgba(43,182,115,0)}}

/* cabeçalho com abas */
.st-key-topo{height:6vh;border-bottom:2px solid var(--linha);padding-bottom:.8vh!important;box-sizing:border-box;
  align-items:center!important;flex-wrap:nowrap!important;gap:1.2vw!important;}
.st-key-topo [data-testid="stElementContainer"]{width:auto!important;}
.st-key-topo .st-key-relogio, .st-key-topo [data-testid="stLayoutWrapper"]:has(> .st-key-relogio){margin-left:auto!important;width:auto!important;flex:0 0 auto!important;}
div[class*="st-key-aba-"] button{background:transparent!important;border:1px solid var(--linha)!important;
  border-radius:99px!important;padding:.35vh 1.1vw!important;min-height:0!important;box-shadow:none!important;}
div[class*="st-key-aba-"] button p{font-family:'Barlow',sans-serif!important;font-weight:600!important;
  font-size:clamp(13px,1.9vh,26px)!important;color:var(--apagado)!important;line-height:1.2!important;}
div[class*="st-key-aba-"] button:hover{border-color:var(--apagado)!important;}
div[class*="st-key-aba-on-"] button{background:var(--tecla)!important;border-color:var(--tecla)!important;}
div[class*="st-key-aba-on-"] button p{color:var(--tinta)!important;}
div[class*="st-key-aba-"]{margin-bottom:.2vh;}

/* colunas do Streamlit = metades da tela */
[data-testid="stHorizontalBlock"]{gap:1.4vw!important;margin-top:1.2vh;}
.st-key-topo + div, .st-key-quadros{margin-top:0;}
.st-key-coluna-a, .st-key-coluna-b{gap:var(--vgap)!important;}

/* o quadro de cada cargo é um container do Streamlit */
div[class*="st-key-card-"]{background:var(--painel);border:1px solid var(--linha);border-radius:14px;
  padding:1.6vh 1.4vw!important;position:relative;overflow:hidden;box-sizing:border-box;
  gap:1.1vh!important;flex-wrap:nowrap!important;}
div[class*="st-key-card-normal-"]{height:calc((var(--area) - var(--vgap)) / 2);}
div[class*="st-key-card-foco-"]{height:var(--area);border-color:var(--apagado);}
div[class*="st-key-card-mini-"]{height:calc((var(--area) - 2 * var(--vgap)) / 3);gap:.7vh!important;}
div[class*="st-key-card-"] > div{width:100%;flex-shrink:0;}
div[class*="st-key-card-"]{flex:0 0 auto!important;}
[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card-"]){flex:0 0 auto!important;}
div[class*="st-key-card-"] [data-testid="stElementContainer"],
div[class*="st-key-card-"] [data-testid="stMarkdown"],
div[class*="st-key-card-"] [data-testid="stMarkdownContainer"]{position:static!important;}
div[class*="st-key-btn-"]{display:flex!important;justify-content:flex-start!important;}
div[class*="st-key-btn-"] .stButton, div[class*="st-key-btn-"] .stTooltipIcon{width:auto!important;}
div[class*="st-key-btn-"] button > div{justify-content:flex-start!important;}
div[class*="st-key-card-"] [data-testid="stMarkdownContainer"]{width:100%;}

/* título do quadro = botão (clique abre/fecha) */
div[class*="st-key-btn-"] button{background:none!important;border:none!important;box-shadow:none!important;
  padding:0!important;min-height:0!important;margin:0!important;line-height:1!important;cursor:pointer;
  justify-content:flex-start!important;}
div[class*="st-key-btn-"] button p{font-family:'Barlow',sans-serif!important;color:var(--apagado)!important;
  font-size:clamp(14px,2.6vh,38px)!important;line-height:1!important;margin:0!important;text-align:left;}
div[class*="st-key-btn-"] button p strong{font-family:'Barlow Condensed',sans-serif!important;font-weight:800!important;
  color:var(--tecla)!important;font-size:clamp(26px,4.4vh,62px)!important;margin-right:.15em;}
div[class*="st-key-btn-"] button:hover p strong{text-decoration:underline;text-decoration-thickness:2px;
  text-underline-offset:.15em;text-decoration-color:var(--apagado);}
div[class*="st-key-btn-"] button:focus-visible{outline:2px solid var(--tecla)!important;outline-offset:4px;border-radius:6px;}
div[class*="st-key-card-mini-"] div[class*="st-key-btn-"] button p{font-size:clamp(12px,2vh,28px)!important;}
div[class*="st-key-card-mini-"] div[class*="st-key-btn-"] button p strong{font-size:clamp(20px,3.2vh,44px)!important;}

/* % de urnas no canto superior direito do quadro */
.urnas-abs{position:absolute;top:1.2vh;right:1.4vw;}
div[class*="st-key-card-"] .trilho{margin-top:1vh;}
div[class*="st-key-card-mini-"] .trilho{margin-top:.6vh;}
div[class*="st-key-card-mini-"] .urnas small{display:none;}
div[class*="st-key-card-mini-"] .urnas b{font-size:clamp(20px,3.2vh,44px);}
div[class*="st-key-card-mini-"] .urnas small{font-size:clamp(11px,1.3vh,18px);}
.urnas{text-align:right;line-height:1;}
.urnas b{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(26px,4.4vh,62px);color:var(--tecla);}
.urnas small{display:block;color:var(--apagado);font-size:clamp(12px,1.6vh,22px);margin-top:.3vh;}
.trilho{height:1vh;min-height:6px;background:var(--linha);border-radius:99px;overflow:hidden;}
.trilho i{display:block;height:100%;background:var(--tecla);border-radius:99px;transition:width .8s ease;}

.cands{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;gap:.6vh;min-height:0;}
.cand{display:grid;grid-template-columns:auto 1fr auto;align-items:center;column-gap:1.1vw;row-gap:0;}
.foto{position:relative;width:clamp(44px,8.2vh,120px);aspect-ratio:3/4;border-radius:10px;
  background:var(--linha);border:3px solid var(--c);overflow:hidden;display:grid;place-items:center;
  font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(18px,3.4vh,48px);color:var(--apagado);}
.foto::after{content:"";position:absolute;inset:0;background-image:var(--foto);background-size:cover;background-position:center top;}
.info{min-width:0;}
.nome{font-family:'Barlow Condensed',sans-serif;font-weight:700;line-height:1.02;
  font-size:clamp(22px,4vh,58px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.meta{color:var(--apagado);font-size:clamp(13px,1.9vh,26px);margin-top:.4vh;
  display:flex;align-items:baseline;flex-wrap:wrap;column-gap:.8em;}
.votos{font-family:'Barlow Condensed',sans-serif;font-weight:700;color:var(--tecla);
  font-size:clamp(20px,3.4vh,48px);line-height:1;font-variant-numeric:tabular-nums;}
.votos small{font-family:'Barlow',sans-serif;font-weight:500;font-size:.5em;color:var(--tecla);opacity:.85;}
.meta .tag{display:inline-block;margin-left:.6em;padding:.05em .5em;border-radius:6px;
  background:var(--confirma);color:var(--tinta);font-weight:600;}
.meta .tag.alerta{background:var(--corrige);}
.barra{height:.9vh;min-height:5px;background:var(--linha);border-radius:99px;margin-top:.8vh;overflow:hidden;}
.barra i{display:block;height:100%;background:var(--c);transition:width .8s ease;}
.pct{font-family:'Barlow Condensed',sans-serif;font-weight:800;line-height:1;text-align:right;
  font-size:clamp(34px,7.4vh,110px);font-variant-numeric:tabular-nums;color:var(--c);}
.cand{--c:var(--tecla);}
.cand .delta{grid-column:2/4;margin-top:.5vh;}
.delta{color:var(--apagado);font-size:clamp(13px,2vh,28px);line-height:1.15;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.delta b{font-family:'Barlow Condensed',sans-serif;font-weight:700;color:var(--tecla);font-size:1.3em;}
.delta em{font-style:normal;color:var(--tecla);}
.pct small{font-size:.45em;font-weight:600;}

.vazio{flex:1;display:grid;place-items:center;text-align:center;color:var(--apagado);
  font-size:clamp(16px,2.4vh,32px);}
.aviso{color:var(--corrige);font-size:clamp(12px,1.5vh,20px);}

/* quadro aberto: lista dos 20 primeiros */
.lista{overflow-y:auto;max-height:calc(var(--area) - 3.2vh - 4.4vh - 2.6vh - 1.5vh);padding-right:.4vw;margin-top:.6vh;}
.lista::-webkit-scrollbar{width:8px}.lista::-webkit-scrollbar-thumb{background:var(--linha);border-radius:8px}
.lin{--c:var(--tecla);display:grid;grid-template-columns:2em minmax(0,1fr) 5.2em 4.8em 4em;align-items:center;
  column-gap:.8vw;padding:.35vh .6vw;border-left:5px solid var(--c);margin-bottom:.3vh;border-radius:4px;
  font-size:clamp(14px,2.45vh,34px);line-height:1.1;
  background:linear-gradient(90deg,color-mix(in srgb,var(--c) 20%,transparent) var(--w),transparent var(--w));}
.lin.cabeca{border-left-color:transparent;background:none;color:var(--apagado);font-size:clamp(11px,1.5vh,20px);
  padding-top:0;padding-bottom:.2vh;}
.lin .pos{color:var(--apagado);font-variant-numeric:tabular-nums;}
.lin .nm{font-family:'Barlow Condensed',sans-serif;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.lin .nm small{font-family:'Barlow',sans-serif;font-weight:500;color:var(--apagado);font-size:.7em;margin-left:.6em;}
.lin .vt{font-family:'Barlow Condensed',sans-serif;font-weight:700;text-align:right;font-variant-numeric:tabular-nums;}
.lin .df{color:var(--apagado);text-align:right;font-variant-numeric:tabular-nums;font-size:.8em;}
.lin.cabeca .df{white-space:nowrap;}
.lin .pc{font-family:'Barlow Condensed',sans-serif;font-weight:800;text-align:right;color:var(--c);font-variant-numeric:tabular-nums;}
.lin.cabeca span{font-family:'Barlow',sans-serif!important;font-weight:500!important;color:var(--apagado)!important;font-size:1em!important;}

/* quadros reduzidos: sem foto, uma linha por candidato */
.mini{display:flex;flex-direction:column;gap:.5vh;}
.mlin{--c:var(--tecla);display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:baseline;column-gap:1vw;
  border-left:4px solid var(--c);padding-left:.6vw;}
.mlin .nm{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(16px,3.3vh,46px);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.1;}
.mlin .nm small{font-family:'Barlow',sans-serif;font-weight:500;color:var(--apagado);font-size:.55em;margin-left:.5em;}
.mlin .vt{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(15px,3vh,42px);font-variant-numeric:tabular-nums;}
.mlin .vt small{font-family:'Barlow',sans-serif;font-weight:500;font-size:.55em;opacity:.85;}
.mlin .pc{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(18px,4vh,56px);
  color:var(--c);text-align:right;font-variant-numeric:tabular-nums;line-height:1;white-space:nowrap;min-width:3.4em;}
.mlin .vt{white-space:nowrap;}
.mini{gap:.8vh;margin-top:.4vh;}
.mini .delta{margin:0 0 .3vh calc(4px + .6vw);font-size:clamp(11px,1.9vh,26px);}

/* eleito: tudo dourado */
.eleito .votos, .eleito .votos small, .eleito .vt, .eleito .vt small, .eleito .nome, .eleito .nm, .eleito .ld{color:#F5C542!important;}
.eleito .foto{box-shadow:0 0 1.2vh rgba(245,197,66,.55);}
.meta .tag{background:#F5C542!important;color:var(--tinta)!important;}
.meta .tag.alerta{background:var(--corrige)!important;}

/* projeção */
div[class*="st-key-aba-"][class*="-proj"]{margin-left:.8vw;}
.pj{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:1.6vw;height:calc(var(--area) - 6.4vh);}
.pj-esq{display:flex;flex-direction:column;gap:1.3vh;min-height:0;overflow:hidden;}
.pj-ver{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(20px,3.6vh,50px);line-height:1.1;}
.pj-ver b{font-weight:800;}
.pj-lin{--c:var(--tecla);display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:1vw;row-gap:.4vh;
  border-left:5px solid var(--c);padding-left:.9vw;}
.pj-nm{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(18px,3.2vh,44px);line-height:1;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;align-self:end;}
.pj-nm small{font-family:'Barlow',sans-serif;font-weight:500;color:var(--apagado);font-size:.5em;margin-left:.6em;}
.pj-pc{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(28px,5.4vh,76px);line-height:.9;
  color:var(--c);grid-row:1/3;grid-column:2;align-self:center;font-variant-numeric:tabular-nums;}
.pj-pc small{font-size:.45em;}
.pj-barra{position:relative;height:1vh;min-height:6px;background:var(--linha);border-radius:99px;}
.pj-barra i{display:block;height:100%;background:var(--c);border-radius:99px;}
.pj-barra b{position:absolute;top:-.5vh;bottom:-.5vh;width:2px;background:var(--tecla);opacity:.7;}
.pj-vt{grid-column:1/3;color:var(--tecla);font-size:clamp(12px,1.9vh,26px);font-variant-numeric:tabular-nums;}
.pj-vt span{color:var(--apagado);margin-left:1em;}
.pj-nota{margin-top:auto;color:var(--apagado);font-size:clamp(11px,1.5vh,20px);line-height:1.35;max-width:75ch;}
.pj-tab{background:var(--painel);border:1px solid var(--linha);border-radius:12px;padding:1.2vh 1vw;
  display:flex;flex-direction:column;min-height:0;}
.pj-rolo{overflow-y:auto;min-height:0;}
.pj-uf{display:grid;grid-template-columns:3.2em 1fr 1.4fr 1.6fr;column-gap:.8vw;align-items:baseline;
  padding:.28vh 0;border-bottom:1px solid var(--linha);font-size:clamp(12px,1.8vh,25px);font-variant-numeric:tabular-nums;}
.pj-uf span:not(:first-child){text-align:right;}
.pj-uf .sg{font-family:'Barlow Condensed',sans-serif;font-weight:800;}
.pj-uf .sd{font-family:'Barlow Condensed',sans-serif;font-weight:700;}
.pj-uf.cabeca{color:var(--apagado);font-size:clamp(11px,1.5vh,20px);border-bottom-color:var(--apagado);}

/* visão por estado */
.st-key-filtro{gap:.6vw!important;margin:1.2vh 0 1vh!important;align-items:center!important;flex-wrap:nowrap!important;}
.st-key-filtro [data-testid="stElementContainer"]{width:auto!important;}
.st-key-filtro [data-testid="stElementContainer"]:last-child{min-width:0;flex:1 1 auto;}
.resumo{display:flex;gap:1.6vw;flex-wrap:nowrap;overflow:hidden;max-width:100%;line-height:1.5;padding:.1em 0;align-items:baseline;font-size:clamp(13px,2vh,28px);color:var(--apagado);
  margin-left:1.2vw;}
.resumo span{white-space:nowrap;}
.resumo b{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1.3em;color:var(--c);}
.ufs{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));grid-auto-rows:1fr;gap:1vh .8vw;
  height:calc(var(--area) - 6.4vh);}
.uf{--c:var(--linha);background:var(--painel);border:1px solid var(--linha);border-top:6px solid var(--c);
  border-radius:10px;padding:1vh .8vw;display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;}
.uf .cab{display:flex;justify-content:space-between;align-items:baseline;gap:.4vw;}
.uf .sg{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(20px,3.6vh,50px);line-height:1;}
.uf .ap{font-family:'Barlow Condensed',sans-serif;font-weight:600;font-size:clamp(13px,2vh,28px);color:var(--tecla);
  font-variant-numeric:tabular-nums;}
.uf .ap small{color:var(--apagado);font-weight:500;font-size:.7em;margin-left:.2em;}
.uf .es{color:var(--apagado);font-size:clamp(10px,1.4vh,19px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.uf .tr{height:.6vh;min-height:4px;background:var(--linha);border-radius:99px;overflow:hidden;margin:.6vh 0 .8vh;}
.uf .tr i{display:block;height:100%;background:var(--tecla);}
.uf .ld{margin-top:auto;font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:clamp(13px,2.2vh,30px);
  line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.uf .ld small{font-family:'Barlow',sans-serif;font-weight:500;color:var(--apagado);font-size:.7em;margin-left:.3em;}
.uf .pc{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:clamp(24px,4.8vh,66px);line-height:1;
  color:var(--c);font-variant-numeric:tabular-nums;}
.uf .pc small{font-size:.45em;}
.uf .mg{color:var(--apagado);font-size:clamp(10px,1.4vh,19px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.uf.sem{--c:var(--linha);}
.uf.sem .ld{color:var(--apagado);font-weight:500;}

@media (max-width:900px){
  .pj{grid-template-columns:1fr;height:auto;}
  .ufs{grid-template-columns:repeat(3,minmax(0,1fr));height:auto;grid-auto-rows:auto;}
  .st-key-topo{height:auto;flex-wrap:wrap!important;}
  div[class*="st-key-card-"]{height:auto!important;min-height:30vh;}
  .urnas-abs{position:static;text-align:left;}
  .lista{max-height:70vh;}
}
@media (prefers-reduced-motion:reduce){.vivo{animation:none}.trilho i,.barra i{transition:none}}
</style>
"""


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ───────────────────────── CORES DOS PARTIDOS ─────────────────────────
# Cor principal primeiro; as seguintes são alternativas (usadas se a principal sumir no fundo azul
# ou se os dois candidatos do quadro ficarem com cores parecidas).
CORES_PARTIDO = {
    "PT": ["#C0122D"],
    "PSOL": ["#F2A134", "#E84C3D"],
    "PDT": ["#1E4080", "#D32F2F"],
    "PSB": ["#E41B23"],
    "PCDOB": ["#009E3D"],
    "PV": ["#00A859"],
    "MDB": ["#009959"],
    "PSD": ["#0054A6"],
    "PSDB": ["#004A94", "#FFD400"],
    "CIDADANIA": ["#2BB673"],
    "SOLIDARIEDADE": ["#162A5B", "#F37021"],
    "AVANTE": ["#2EABB1"],
    "PL": ["#0F4C81", "#FFD400"],
    "UNIAO": ["#00A0DF"],
    "PP": ["#003366"],
    "REPUBLICANOS": ["#005CA9", "#009E3D", "#FDC300"],
    "PODE": ["#1D2A44", "#00A896"],
    "NOVO": ["#FF6600"],
    "UP": ["#000000"],
}
APELIDOS = {"PODEMOS": "PODE", "UNIAOBRASIL": "UNIAO", "PCB DO B": "PCDOB", "PROGRESSISTAS": "PP"}
COR_NEUTRA = "#C9D6E5"   # partidos sem cor definida
FUNDO_CARD = "#132F52"   # mesmo valor de --painel
CONTRASTE_MIN = 3.0      # legível para números grandes


def _chave_partido(sigla: str) -> str:
    import unicodedata
    k = unicodedata.normalize("NFKD", sigla).encode("ascii", "ignore").decode().upper()
    k = "".join(ch for ch in k if ch.isalnum())
    return APELIDOS.get(k, k)


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _lum(h: str) -> float:
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _clarear(h: str) -> str:
    """Sobe a luminosidade mantendo o tom e a saturação, até ficar legível no fundo do quadro."""
    import colorsys
    r, g, b = (v / 255 for v in _rgb(h))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.08:  # preto/cinza (ex.: UP) → cinza claro
        sat = 0.0
    for i in range(41):
        l2 = light + (0.92 - light) * i / 40
        c = _hex(tuple(v * 255 for v in colorsys.hls_to_rgb(hue, l2, sat)))
        if _contraste(c, FUNDO_CARD) >= CONTRASTE_MIN:
            return c
    return "#FFFFFF"


def opcoes_cor(sigla: str) -> list[str]:
    """Cores possíveis do partido, já legíveis, em ordem de preferência."""
    brutas = CORES_PARTIDO.get(_chave_partido(sigla or ""), [])
    if not brutas:
        return [COR_NEUTRA]
    ordem = [c if _contraste(c, FUNDO_CARD) >= CONTRASTE_MIN else _clarear(c) for c in brutas]
    return list(dict.fromkeys(ordem))


OURO = "#F5C542"


def eleito(c: dict) -> bool:
    """TSE marca o eleito com e='s' e/ou st='Eleito' ('Eleito por QP', 'Eleito por média'...)."""
    return (bool(c.get("eleito")) or bool(c.get("eleito_calc"))
            or str(c.get("situacao", "")).strip().lower().startswith("eleit"))


def cor_final(c: dict, cor: str | None = None) -> str:
    return OURO if eleito(c) else (cor or opcoes_cor(c["partido"])[0])


def _distancia(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def cores_do_quadro(cands: list[dict]) -> list[str]:
    """Uma cor por candidato; se o 2º ficar parecido com o 1º, tenta a alternativa do partido."""
    cores = []
    for c in cands:
        ops = opcoes_cor(c["partido"])
        escolha = ops[0]
        if cores and _distancia(escolha, cores[0]) < 90:
            escolha = next((o for o in ops if _distancia(o, cores[0]) >= 90), escolha)
        cores.append(escolha)
    return [cor_final(c, cor) for c, cor in zip(cands, cores)]


def fmt_pct(p: float) -> str:
    return f"{p:.2f}".replace(".", ",")


def iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p[0].isalpha()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def html_cand(c: dict, cor: str, delta: str = "") -> str:
    foto_css = f"--foto:url('{escape(c['foto'])}')" if c["foto"] else ""
    situ = c["situacao"].lower()
    tag = ""
    if c["eleito"] or situ.startswith("eleito"):
        tag = '<span class="tag">Eleito</span>'
    elif c.get("eleito_calc"):
        tag = '<span class="tag">Eleito no 1º turno</span>'
    elif "2º turno" in situ or "2o turno" in situ:
        tag = '<span class="tag">2º turno</span>'
    elif "sub judice" in situ:
        tag = '<span class="tag alerta">Sub judice</span>'
    largura = max(0.0, min(100.0, c["pct"]))
    partido_num = " – ".join(x for x in (escape(c["partido"]), escape(c["numero"])) if x)
    return f"""
    <div class="cand{' eleito' if eleito(c) else ''}" style="--c:{cor}">
      <div class="foto" style="{foto_css}">{escape(iniciais(c['nome']))}</div>
      <div class="info">
        <div class="nome">{escape(c['nome'])}</div>
        <div class="meta"><span class="votos">{fmt_int(c['votos'])}<small> votos</small></span>{partido_num}{tag}</div>
        <div class="barra"><i style="width:{largura:.2f}%"></i></div>
      </div>
      <div class="pct">{fmt_pct(c['pct'])}<small>%</small></div>
      {delta}
    </div>"""


def html_delta(frente: dict, atras: dict) -> str:
    d = frente["votos"] - atras["votos"]
    nome = escape(atras["nome"])
    if d == 0:
        return f'<div class="delta">Empatado com <em>{nome}</em></div>'
    return f'<div class="delta"><b>{fmt_int(d)}</b> votos a mais que <em>{nome}</em></div>'


def html_urnas(dados, erro) -> str:
    pst = dados["pst"]
    tot, total = dados["secoes"]
    sub = f"{fmt_int(tot)} de {fmt_int(total)} seções" if total else "urnas apuradas"
    if erro:
        sub = '<span class="aviso">sem conexão — último dado</span>'
    return (f'<div class="urnas urnas-abs"><b>{fmt_pct(pst)}%</b><small>{sub}</small></div>'
            f'<div class="trilho"><i style="width:{min(pst, 100):.2f}%"></i></div>')


def deltas_do_quadro(chave: str, top: list) -> list[str]:
    deltas = ["", ""]
    if len(top) >= 2:
        deltas[0] = html_delta(top[0], top[1])
    if chave == "sen" and len(top) >= 3:
        # Senado 2026 tem 2 vagas: a disputa que importa é 2º × 3º
        deltas[1] = html_delta(top[1], top[2])
    return deltas


def corpo_normal(chave, dados, erro) -> str:
    top = dados["top"]
    mostrados = top[:2]
    cores = cores_do_quadro(mostrados)
    deltas = deltas_do_quadro(chave, top)
    cands = "".join(html_cand(c, cores[i], deltas[i]) for i, c in enumerate(mostrados)) or \
        '<div class="vazio">Ainda sem votos totalizados</div>'
    return f'{html_urnas(dados, erro)}<div class="cands" style="height:calc((var(--area) - var(--vgap)) / 2 - 3.2vh - 7.6vh)">{cands}</div>'


def corpo_mini(chave, dados, erro) -> str:
    top = dados["top"]
    mostrados = top[:2]
    cores = cores_do_quadro(mostrados)
    deltas = deltas_do_quadro(chave, top)
    linhas = []
    for i, c in enumerate(mostrados):
        part = " – ".join(x for x in (escape(c["partido"]), escape(c["numero"])) if x)
        linhas.append(
            f'<div class="mlin{" eleito" if eleito(c) else ""}" style="--c:{cores[i]}"><span class="nm">{escape(c["nome"])}<small>{part}</small></span>'
            f'<span class="vt">{fmt_int(c["votos"])}<small> votos</small></span>'
            f'<span class="pc">{fmt_pct(c["pct"])}%</span></div>{deltas[i]}')
    corpo = "".join(linhas) or '<div class="vazio">Ainda sem votos totalizados</div>'
    return f'{html_urnas(dados, erro)}<div class="mini">{corpo}</div>'


def corpo_foco(chave, dados, erro) -> str:
    top = dados["top"]
    if not top:
        return f'{html_urnas(dados, erro)}<div class="vazio">Ainda sem votos totalizados</div>'
    lider = max(top[0]["pct"], 0.01)
    linhas = ['<div class="lin cabeca"><span>#</span><span>Candidato</span><span class="vt">Votos</span>'
              '<span class="df">Vantagem</span><span class="pc">%</span></div>']
    for i, c in enumerate(top):
        cor = cor_final(c)
        part = " – ".join(x for x in (escape(c["partido"]), escape(c["numero"])) if x)
        dif = f'+{fmt_int(c["votos"] - top[i + 1]["votos"])}' if i + 1 < len(top) else ""
        largura = 100 * c["pct"] / lider
        linhas.append(
            f'<div class="lin{" eleito" if eleito(c) else ""}" style="--c:{cor};--w:{largura:.1f}%"><span class="pos">{i + 1}º</span>'
            f'<span class="nm">{escape(c["nome"])}<small>{part}</small></span>'
            f'<span class="vt">{fmt_int(c["votos"])}</span><span class="df">{dif}</span>'
            f'<span class="pc">{fmt_pct(c["pct"])}%</span></div>')
    return f'{html_urnas(dados, erro)}<div class="lista">{"".join(linhas)}</div>'


def compactar(html: str) -> str:
    """Tira quebras de linha/indentação: no Markdown, linha indentada após linha em branco vira bloco de código."""
    return re.sub(r"\n\s*", "", html)


def nome_uf(uf: str) -> str:
    return dict(UFS).get(uf, "Exterior" if uf == "zz" else uf.upper())


def html_estados(cargo: str, blocos: dict) -> str:
    tiles, lideres = [], {}
    for uf, bloco in blocos.items():
        d = bloco["dados"]
        sg, nome = ("EXT" if uf == "zz" else uf.upper()), nome_uf(uf)
        if not d or not d["top"]:
            pst = d["pst"] if d else 0
            msg = "Aguardando dados" if not d else "Sem votos ainda"
            tiles.append(f'<div class="uf sem"><div class="cab"><span class="sg">{sg}</span>'
                         f'<span class="ap">{fmt_pct(pst)}%</span></div><div class="es">{escape(nome)}</div>'
                         f'<div class="tr"><i style="width:{min(pst, 100):.1f}%"></i></div>'
                         f'<div class="ld">{msg}</div></div>')
            continue
        l1 = d["top"][0]
        cor = cor_final(l1)
        margem = ""
        if len(d["top"]) > 1:
            pp = l1["pct"] - d["top"][1]["pct"]
            margem = f'+{fmt_pct(pp)} p.p. sobre {escape(d["top"][1]["nome"])}'
        situ = l1["situacao"].lower()
        if l1["eleito"] or situ.startswith("eleito"):
            margem = "Eleito"
        elif l1.get("eleito_calc"):
            margem = "Eleito no 1º turno"
        elif "2º turno" in situ:
            margem = "Vai ao 2º turno"
        # Presidente: conta por candidato; Governador/Senador: por partido (candidatos mudam de UF para UF)
        chave_l = (l1["nome"], l1["partido"]) if cargo == "pres" else (l1["partido"] or "Sem partido", "")
        lideres.setdefault(chave_l, [0, cor])[0] += 1
        tiles.append(
            f'<div class="uf{" eleito" if eleito(l1) else ""}" style="--c:{cor}"><div class="cab"><span class="sg">{sg}</span>'
            f'<span class="ap">{fmt_pct(d["pst"])}%<small>urnas</small></span></div>'
            f'<div class="es">{escape(nome)}</div>'
            f'<div class="tr"><i style="width:{min(d["pst"], 100):.1f}%"></i></div>'
            f'<div class="ld">{escape(l1["nome"])}<small>{escape(l1["partido"])}</small></div>'
            f'<div class="pc">{fmt_pct(l1["pct"])}<small>%</small></div>'
            f'<div class="mg">{margem}</div></div>')
    ranking = sorted(lideres.items(), key=lambda kv: -kv[1][0])
    resumo = "".join(
        f'<span style="--c:{cor}"><b>{escape(nome)}</b> lidera em {n} {"UF" if n == 1 else "UFs"}</span>'
        for (nome, _), (n, cor) in ranking)
    return f'<div class="resumo">{resumo}</div>', f'<div class="ufs">{"".join(tiles)}</div>'


def ir_para_aba(aba: str):
    st.session_state.aba = aba


def escolher_cargo_uf(cargo: str):
    st.session_state.cargo_uf = cargo


def alternar_foco(chave: str):
    st.session_state.foco = None if st.session_state.get("foco") == chave else chave


def quadro(cargo, bloco, modo: str):
    """modo: 'normal' (2×2), 'foco' (aberto, lista de 20) ou 'mini' (reduzido, sem foto)."""
    chave, titulo, abrang, *_ = cargo
    dados, erro = bloco["dados"], bloco["erro"]
    with st.container(key=f"card-{modo}-{chave}"):
        rotulo = f"**{titulo}** {abrang}" + ("  ✕" if modo == "foco" else "")
        st.button(rotulo, key=f"btn-{chave}", on_click=alternar_foco, args=(chave,))
        if not dados:
            html = (f'<div class="vazio" style="height:20vh"><div>Aguardando dados do TSE…<br>'
                    f'<span class="aviso">{escape(erro or "")}</span></div></div>')
        elif modo == "foco":
            html = corpo_foco(chave, dados, erro)
        elif modo == "mini":
            html = corpo_mini(chave, dados, erro)
        else:
            html = corpo_normal(chave, dados, erro)
        st.markdown(compactar(html), unsafe_allow_html=True)


# ───────────────────────── PÁGINA ─────────────────────────
st.set_page_config(page_title="Apuração 2026", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

DEMO = st.query_params.get("demo") in ("1", "true", "sim")
DEBUG = st.query_params.get("debug") in ("1", "true", "sim")


def cabecalho(algum_erro: bool, rotulo: str):
    aba = st.session_state.get("aba", "painel")
    with st.container(key="topo", horizontal=True, vertical_alignment="bottom"):
        st.markdown(f'<div class="marca">Apuração 2026<small>1º turno{" — demonstração" if DEMO else ""}</small></div>',
                    unsafe_allow_html=True)
        for chave, texto in (("painel", "Painel"), ("estados", "Por estado")):
            estado = "on" if aba == chave else "off"
            st.button(texto, key=f"aba-{estado}-{chave}", on_click=ir_para_aba, args=(chave,))
        with st.container(key="relogio"):
            st.markdown(f'<div class="relogio"><span class="vivo {"off" if algum_erro else ""}"></span>{rotulo}</div>',
                        unsafe_allow_html=True)


def rotulo_hora(blocos: dict) -> str:
    tse_hora = next((b["dados"]["atualizado"].split(" ")[-1] for b in blocos.values()
                     if b["dados"] and b["dados"]["atualizado"]), "")
    return f"TSE {tse_hora}" if tse_hora else datetime.now(TZ).strftime("%H:%M:%S")


def visao_estados():
    cargo = st.session_state.get("cargo_uf", "pres")
    blocos = carregar_estados_demo(cargo) if DEMO else carregar_estados(cargo)
    erros = sum(1 for b in blocos.values() if b["erro"])
    cabecalho(erros > 0, rotulo_hora(blocos))
    resumo, grade = html_estados(cargo, blocos)
    with st.container(key="filtro", horizontal=True):
        for chave, (texto, *_) in CARGOS_UF.items():
            estado = "on" if cargo == chave else "off"
            st.button(texto, key=f"aba-{estado}-uf-{chave}", on_click=escolher_cargo_uf, args=(chave,))
        projecao = cargo == "pres" and st.session_state.get("proj", False)
        if cargo == "pres":
            st.button("Projeção", key=f"aba-{'on' if projecao else 'off'}-proj", on_click=alternar_projecao)
        st.markdown(compactar(resumo), unsafe_allow_html=True)
    if projecao:
        st.markdown(compactar(html_projecao(projetar(blocos))), unsafe_allow_html=True)
    else:
        st.markdown(compactar(grade), unsafe_allow_html=True)


@st.fragment(run_every=REFRESH_S)
def painel():
    if st.session_state.get("aba", "painel") == "estados":
        visao_estados()
        return

    blocos = carregar_demo() if DEMO else carregar_tudo()
    algum_erro = any(b["erro"] for b in blocos.values())
    cabecalho(algum_erro, rotulo_hora(blocos))

    por_chave = {c[0]: c for c in CARGOS}
    foco = st.session_state.get("foco")
    esq, dir_ = st.columns(2)
    if foco in por_chave:
        with esq, st.container(key="coluna-a"):
            quadro(por_chave[foco], blocos[foco], "foco")
        with dir_, st.container(key="coluna-b"):
            for c in CARGOS:
                if c[0] != foco:
                    quadro(c, blocos[c[0]], "mini")
    else:
        # mesma posição de antes: Presidente | Governador / Senador | Deputado federal
        with esq, st.container(key="coluna-a"):
            quadro(por_chave["pres"], blocos["pres"], "normal")
            quadro(por_chave["sen"], blocos["sen"], "normal")
        with dir_, st.container(key="coluna-b"):
            quadro(por_chave["gov"], blocos["gov"], "normal")
            quadro(por_chave["depf"], blocos["depf"], "normal")


if DEBUG:
    tela_diagnostico()
else:
    painel()
