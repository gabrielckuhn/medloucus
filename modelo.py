"""Cálculos do 2º turno: certeza matemática, projeção municipal por transferência de votos,
probabilidade de vitória, recortes (regiões, UFs, capitais) e previsão de horário.

Modelo (resumo):
  Para cada município, o 1º turno dá a composição do eleitorado apto:
      x = [Flávio, Lula, outros candidatos, branco/nulo, abstenção] / aptos
  Nos municípios já apurados no 2º turno observamos, sobre o eleitorado das seções totalizadas,
      y = [Flávio, Lula, branco/nulo] / eleitorado apurado
  Ajustamos y ≈ x · P (mínimos quadrados ponderados, 0 ≤ P ≤ 1). P é a matriz de transferência:
  que fração de cada grupo do 1º turno foi para cada opção no 2º. Ela é aplicada ao eleitorado
  que falta apurar em cada município, com correção pelo desvio médio da UF (encolhido em direção
  a zero quando a UF tem poucos dados) e, em municípios já parcialmente apurados, puxando para o
  que as seções desse município já mostraram.
  A incerteza soma três partes: erro municipal (resíduos), erro comum por UF (variação entre
  UFs) e um erro comum nacional, aplicadas só ao eleitorado que falta.
"""
from __future__ import annotations

import csv
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

NUM_F, NUM_L = "22", "13"          # Flávio Bolsonaro, Lula
GRUPOS = ["Flávio", "Lula", "Outros candidatos", "Branco ou nulo", "Não votou"]
DESTINOS = ["Flávio", "Lula", "Branco ou nulo", "Não votou"]
PASTA = Path(__file__).parent
LAGOAS = {4300001, 4300002}

UF_IBGE = {"11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma",
           "22": "pi", "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba",
           "31": "mg", "32": "es", "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms",
           "51": "mt", "52": "go", "53": "df"}
NOME_UF = {"ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas", "ba": "Bahia", "ce": "Ceará",
           "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás", "ma": "Maranhão", "mt": "Mato Grosso",
           "ms": "Mato Grosso do Sul", "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
           "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
           "rs": "Rio Grande do Sul", "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina", "sp": "São Paulo",
           "se": "Sergipe", "to": "Tocantins", "zz": "Exterior"}
REGIAO_UF = {**{u: "Norte" for u in ("ac", "am", "ap", "pa", "ro", "rr", "to")},
             **{u: "Nordeste" for u in ("al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se")},
             **{u: "Sudeste" for u in ("es", "mg", "rj", "sp")},
             **{u: "Sul" for u in ("pr", "rs", "sc")},
             **{u: "Centro-Oeste" for u in ("df", "go", "ms", "mt")}, "zz": "Exterior"}
REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"]
CAPITAIS = {"ac": "rio branco", "al": "maceio", "ap": "macapa", "am": "manaus", "ba": "salvador",
            "ce": "fortaleza", "df": "brasilia", "es": "vitoria", "go": "goiania", "ma": "sao luis",
            "mt": "cuiaba", "ms": "campo grande", "mg": "belo horizonte", "pa": "belem", "pb": "joao pessoa",
            "pr": "curitiba", "pe": "recife", "pi": "teresina", "rj": "rio de janeiro", "rn": "natal",
            "rs": "porto alegre", "ro": "porto velho", "rr": "boa vista", "sc": "florianopolis",
            "sp": "sao paulo", "se": "aracaju", "to": "palmas"}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().strip()


# ───────────────────────── BASE DO 1º TURNO ─────────────────────────
@lru_cache(maxsize=1)
def base_1turno() -> dict:
    """Resultado do 1º turno por município (TSE, 100% apurado), código IBGE como chave.
    O exterior entra agregado na chave "zz"."""
    mun, zz = {}, np.zeros(7)
    with open(PASTA / "base_1turno.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            te, c, fl, lu, vv = (int(r[k]) for k in ("aptos", "comparecimento", "flavio", "lula", "validos"))
            bn = int(r["brancos"]) + int(r["nulos"])
            vec = np.array([fl, lu, vv - fl - lu, bn, te - c, te, c], dtype=float)
            if r["uf"] == "zz" or not r["cd_ibge"]:
                zz += vec
            else:
                mun[int(r["cd_ibge"])] = {"uf": r["uf"], "vec": vec}
    return {"mun": mun, "zz": zz}


MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "d'"}


def _titulo(nome: str) -> str:
    """'Rio De Janeiro' → 'Rio de Janeiro'."""
    ps = nome.split()
    return " ".join(p.lower() if k and p.lower() in MINUSCULAS else p for k, p in enumerate(ps))


@lru_cache(maxsize=1)
def nomes_municipios() -> dict[int, str]:
    import json
    with open(PASTA / "front" / "geo.json", encoding="utf-8") as f:
        g = json.load(f)
    return {i: _titulo(n) for i, n in zip(g["ids"], g["nm"])}


@lru_cache(maxsize=1)
def capitais_ibge() -> dict[int, str]:
    nomes = nomes_municipios()
    out = {}
    for cdi, nm in nomes.items():
        uf = UF_IBGE.get(str(cdi)[:2])
        if uf and _norm(nm) == CAPITAIS.get(uf):
            out[cdi] = uf
    return out


@lru_cache(maxsize=1)
def matriz_base():
    """Arrays fixos na ordem dos municípios da base."""
    b = base_1turno()["mun"]
    ids = np.array(sorted(b), dtype=np.int64)
    vec = np.array([b[i]["vec"] for i in ids])
    te1 = vec[:, 5]
    x = vec[:, :5] / np.maximum(te1, 1)[:, None]          # composição do eleitorado no 1º turno
    ufs = np.array([b[i]["uf"] for i in ids])
    return ids, x, te1, ufs


# ───────────────────────── CERTEZA MATEMÁTICA ─────────────────────────
def restante_max(d: dict) -> int | None:
    """Máximo de votos que ainda podem entrar = eleitorado apto das seções não totalizadas."""
    if d["pst"] >= 100:
        return 0
    if d["eleitorado"] and d["eleitorado_tot"] and d["eleitorado"] >= d["eleitorado_tot"]:
        return d["eleitorado"] - d["eleitorado_tot"]
    return None


def pct_para_virar(diferenca: float, votos_restantes: float | None) -> float | None:
    """% dos votos válidos restantes que o 2º colocado precisa para empatar: (1 + D/R) / 2."""
    if votos_restantes is None:
        return None
    if votos_restantes <= 0:
        return math.inf if diferenca > 0 else 50.0
    return 100 * (1 + diferenca / votos_restantes) / 2


def situacao_nacional(nac: dict, ufs: dict) -> dict | None:
    d = nac.get("dados")
    if not d or len(d["cands"]) < 2:
        return None
    if not (d["eleitorado"] and d["eleitorado_tot"]):
        E = sum((b["dados"] or {}).get("eleitorado", 0) for b in ufs.values())
        Et = sum((b["dados"] or {}).get("eleitorado_tot", 0) for b in ufs.values())
        if E and Et:
            d = {**d, "eleitorado": E, "eleitorado_tot": Et}
    a, b = d["cands"][0], d["cands"][1]
    D = a["votos"] - b["votos"]
    R = restante_max(d)
    sj = d["sub_judice"]
    taxa = d["validos"] / d["eleitorado_tot"] if d["eleitorado_tot"] else None
    R_est = R * taxa if (R is not None and taxa) else None
    # CF art. 77 §3º: maioria absoluta dos válidos. Pior caso: todo eleitor que falta vota válido no
    # 2º colocado e todo voto anulado sub judice é revalidado para ele. Se ainda assim não empata, acabou.
    certeza = R is not None and "sub judice" not in a["situacao"].lower() and D > R + sj
    return {"d": d, "a": a, "b": b, "dif": D, "dif_pp": a["pct"] - b["pct"], "R": R, "R_est": R_est, "sj": sj,
            "virar_max": pct_para_virar(D, None if R is None else R + sj),
            "virar_est": pct_para_virar(D, None if R_est is None else R_est + sj),
            "oficial": bool(a["eleito"]), "certeza": certeza}


# ───────────────────────── MODELO MUNICIPAL ─────────────────────────
def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _votos_cand(m: dict, num: str) -> float:
    return float(m["v"].get(num, 0)) if m else 0.0


def projetar(votos: dict, andamento: dict, ufs: dict) -> dict:
    """Projeta o resultado final. `votos`: municípios já com dados do 2º turno (código IBGE →
    {"v", "te", "est", "bn", "pst"}); `andamento`: eleitorado de todos os municípios;
    `ufs`: arquivos por UF (para o exterior)."""
    ids, x, te1, ufs_arr = matriz_base()
    n = len(ids)
    te2 = np.array([(andamento.get(i) or votos.get(i) or {}).get("te") or t for i, t in zip(ids, te1)], dtype=float)
    est = np.zeros(n)
    obs = np.zeros((n, 3))                 # Flávio, Lula, branco/nulo já apurados
    for k, i in enumerate(ids):
        m = votos.get(int(i))
        if m and m.get("est"):
            est[k] = min(m["est"], te2[k])
            obs[k] = [_votos_cand(m, NUM_F), _votos_cand(m, NUM_L), m.get("bn", 0)]
    cont = (est > 0) & (obs[:, 0] + obs[:, 1] > 0)
    frac = np.where(te2 > 0, est / np.maximum(te2, 1), 0)
    R = np.maximum(te2 - est, 0)

    # exterior: escala o que já foi apurado; sem dados, usa o 1º turno com a transferência estimada
    zz = (ufs.get("zz") or {}).get("dados") or {}
    zz_obs = np.array([_votos_cand({"v": {c["numero"]: c["votos"] for c in zz.get("cands", [])}}, NUM_F),
                       _votos_cand({"v": {c["numero"]: c["votos"] for c in zz.get("cands", [])}}, NUM_L),
                       zz.get("brancos_nulos", 0)], dtype=float)
    zz_te = float(zz.get("eleitorado") or base_1turno()["zz"][5])
    zz_est = float(zz.get("eleitorado_tot") or 0)

    n_cont = int(cont.sum())
    ufs_cont = len(set(ufs_arr[cont]))
    cobertura = est[cont].sum() / max(te2.sum(), 1)
    pronto = n_cont >= 40 and ufs_cont >= 6 and cobertura >= 0.005

    if not pronto:
        return _projecao_proporcional(ids, ufs_arr, te2, est, obs, cont, zz_obs, zz_te, zz_est,
                                      motivo=f"Calibrando: {n_cont} municípios apurados em {ufs_cont} UFs. "
                                             f"O modelo liga com 40 municípios em 6 UFs.")

    # ── ajuste da matriz de transferência
    w = est[cont] ** 0.75
    sw = np.sqrt(w)[:, None]
    Xc = x[cont]
    Y = obs[cont] / est[cont][:, None]
    P = np.zeros((5, 3))
    for j in range(3):
        P[:, j] = lsq_linear(Xc * sw, Y[:, j] * sw[:, 0], bounds=(0, 1), method="bvls").x
    resid = Y - Xc @ P

    # ── efeito por UF (encolhido)
    kappa = 20 * float(np.median(w))
    uf_lista = sorted(set(ufs_arr))
    delta, peso_uf = {}, {}
    for u in uf_lista:
        mk = ufs_arr[cont] == u
        sw_u = w[mk].sum()
        delta[u] = (w[mk, None] * resid[mk]).sum(0) / (sw_u + kappa) if mk.any() else np.zeros(3)
        peso_uf[u] = sw_u
    # variância entre UFs da diferença Flávio − Lula (momentos), com piso de 1 p.p.
    dd = np.array([delta[u][0] - delta[u][1] for u in uf_lista if peso_uf[u] > 0])
    tau2 = max(float(np.var(dd)) * 1.5 if len(dd) > 2 else 0.0, 0.01 ** 2)
    r_adj = resid - np.array([delta[u] for u in ufs_arr[cont]])
    d_res = r_adj[:, 0] - r_adj[:, 1]
    sig_m2 = float((w * d_res ** 2).sum() / w.sum())

    # ── previsão do que falta
    base_rate = np.clip(x @ P + np.array([delta[u] for u in ufs_arr]), 0, 1)
    lam = np.where(cont, frac / (frac + 0.2), 0.0)
    obs_rate = np.where(cont[:, None], obs / np.maximum(est, 1)[:, None], 0)
    rate = lam[:, None] * obs_rate + (1 - lam[:, None]) * base_rate
    proj = obs + R[:, None] * rate

    if zz_est > 0 and zz_obs[:2].sum() > 0:
        zz_proj = zz_obs * (zz_te / zz_est)
        zz_R_mod = 0.0
    else:
        xz = base_1turno()["zz"][:5] / max(base_1turno()["zz"][5], 1)
        zz_proj = zz_te * np.clip(xz @ P, 0, 1)
        zz_R_mod = zz_te

    F = proj[:, 0].sum() + zz_proj[0]
    L = proj[:, 1].sum() + zz_proj[1]
    BN = proj[:, 2].sum() + zz_proj[2]

    # ── incerteza da diferença Flávio − Lula
    R_eff = R * (1 - lam)
    var_ind = sig_m2 * float((R_eff ** 2).sum())
    var_uf = 0.0
    for u in uf_lista:
        mk = ufs_arr == u
        v_u = tau2 * kappa / (peso_uf[u] + kappa)
        var_uf += float(R_eff[mk].sum()) ** 2 * v_u
    sig_nac = 0.012        # erro comum nacional (p.p. do eleitorado que falta): ordem de apuração, não linearidade
    var_nac = (sig_nac * (float(R_eff.sum()) + zz_R_mod)) ** 2
    sd = math.sqrt(var_ind + var_uf + var_nac)
    D = F - L
    V = F + L
    prob_f = _phi(D / sd) if sd > 0 else (1.0 if D > 0 else 0.0)
    s_f = 100 * F / V
    meia = 100 * 1.96 * sd / (2 * V)

    # ── matriz de transferência legível (cada linha soma 100%)
    trans = []
    for g in range(5):
        row = np.clip(P[g], 0, 1)
        tot = row.sum()
        if tot > 1:
            row = row / tot
        trans.append([round(100 * float(v), 1) for v in row] + [round(100 * max(0.0, 1 - float(row.sum())), 1)])

    # qualidade: erro médio do % de Flávio nos municípios apurados
    s_obs = obs[cont, 0] / np.maximum(obs[cont, 0] + obs[cont, 1], 1)
    pred_c = Xc @ P + np.array([delta[u] for u in ufs_arr[cont]])
    s_pred = pred_c[:, 0] / np.maximum(pred_c[:, 0] + pred_c[:, 1], 1e-9)
    mae = float(np.average(np.abs(s_obs - s_pred), weights=w)) * 100

    return {
        "ok": True, "motivo": "",
        "F": F, "L": L, "BN": BN, "D": D, "sd": sd, "prob_f": prob_f,
        "s_f": s_f, "ic": [s_f - meia, s_f + meia],
        "comparecimento": 100 * (F + L + BN) / (te2.sum() + zz_te),
        "trans": trans, "n": n_cont, "n_ufs": ufs_cont, "cobertura": 100 * cobertura, "mae": mae,
        "por_mun": {int(i): (float(p[0]), float(p[1])) for i, p in zip(ids, proj)},
        "zz": (float(zz_proj[0]), float(zz_proj[1])),
    }


def _projecao_proporcional(ids, ufs_arr, te2, est, obs, cont, zz_obs, zz_te, zz_est, motivo: str) -> dict:
    """Antes de o modelo ligar: mantém o % de cada município já apurado; os demais recebem o % da UF
    (ou do país). Sem probabilidade."""
    tot = obs[cont].sum(0)
    taxa_br = tot / max(est[cont].sum(), 1)
    proj = obs.copy()
    for u in set(ufs_arr):
        mk = ufs_arr == u
        mc = mk & cont
        taxa = obs[mc].sum(0) / est[mc].sum() if mc.any() and est[mc].sum() > 0 else taxa_br
        rate = np.where(cont[mk, None], obs[mk] / np.maximum(est[mk], 1)[:, None], taxa)
        proj[mk] = obs[mk] + (te2[mk] - est[mk])[:, None] * rate
    zz_proj = zz_obs * (zz_te / zz_est) if zz_est > 0 else zz_te * taxa_br
    F = proj[:, 0].sum() + zz_proj[0]
    L = proj[:, 1].sum() + zz_proj[1]
    V = F + L
    return {"ok": False, "motivo": motivo, "F": F, "L": L, "BN": proj[:, 2].sum() + zz_proj[2], "D": F - L,
            "sd": None, "prob_f": None, "s_f": 100 * F / V if V else None, "ic": None, "comparecimento": None,
            "trans": None, "n": int(cont.sum()), "n_ufs": len(set(ufs_arr[cont])),
            "cobertura": 100 * est[cont].sum() / max(te2.sum(), 1), "mae": None,
            "por_mun": {int(i): (float(p[0]), float(p[1])) for i, p in zip(ids, proj)} if V else {},
            "zz": (float(zz_proj[0]), float(zz_proj[1]))}


# ───────────────────────── RECORTES ─────────────────────────
def _cand(d: dict, num: str) -> int:
    return next((c["votos"] for c in (d or {}).get("cands", []) if c["numero"] == num), 0)


def recortes(ufs: dict, votos: dict, proj: dict) -> dict:
    """Regiões e UFs (agora pelos arquivos oficiais por UF; projeção pelo modelo), capitais e
    maiores saldos municipais."""
    pm = proj.get("por_mun") or {}
    uf_proj: dict[str, list[float]] = {}
    for cdi, (f, l) in pm.items():
        u = UF_IBGE.get(str(cdi)[:2])
        acc = uf_proj.setdefault(u, [0.0, 0.0])
        acc[0] += f
        acc[1] += l
    uf_proj["zz"] = list(proj.get("zz") or (0.0, 0.0))

    linhas_uf = []
    for u, nome in NOME_UF.items():
        d = (ufs.get(u) or {}).get("dados") or {}
        f, l = _cand(d, NUM_F), _cand(d, NUM_L)
        fp_, lp_ = uf_proj.get(u, (0, 0))
        te, et = d.get("eleitorado", 0), d.get("eleitorado_tot", 0)
        linhas_uf.append({"uf": u, "nome": nome, "regiao": REGIAO_UF[u],
                          "pst": d.get("pst", 0.0), "ap": 100 * et / te if te else d.get("pst", 0.0),
                          "f": f, "l": l, "fp": fp_, "lp": lp_, "te": te, "et": et})

    regioes = []
    for r in REGIOES:
        ls = [x for x in linhas_uf if x["regiao"] == r]
        te = sum(x["te"] for x in ls)
        et = sum(x["et"] for x in ls)
        regioes.append({"nome": r, "ap": 100 * et / te if te else 0.0,
                        "f": sum(x["f"] for x in ls), "l": sum(x["l"] for x in ls),
                        "fp": sum(x["fp"] for x in ls), "lp": sum(x["lp"] for x in ls), "te": te})

    nomes = nomes_municipios()
    caps = []
    for cdi, u in capitais_ibge().items():
        m = votos.get(cdi)
        fp_, lp_ = pm.get(cdi, (0.0, 0.0))
        caps.append({"nome": nomes.get(cdi, ""), "uf": u, "f": _votos_cand(m, NUM_F), "l": _votos_cand(m, NUM_L),
                     "fp": fp_, "lp": lp_, "pst": (m or {}).get("pst", 0.0)})
    caps.sort(key=lambda c: -(c["fp"] + c["lp"]))

    saldos = []
    for cdi, m in votos.items():
        f, l = _votos_cand(m, NUM_F), _votos_cand(m, NUM_L)
        if f + l > 0:
            saldos.append((f - l, cdi, f, l, m.get("pst", 0.0)))
    saldos.sort()
    def item(t):
        return {"nome": nomes.get(t[1], ""), "uf": UF_IBGE.get(str(t[1])[:2], ""), "saldo": t[0],
                "f": t[2], "l": t[3], "pst": t[4]}
    top_f = [item(t) for t in reversed(saldos[-8:]) if t[0] > 0]
    top_l = [item(t) for t in saldos[:8] if t[0] < 0]
    return {"ufs": linhas_uf, "regioes": regioes, "capitais": caps, "top_f": top_f, "top_l": top_l}


# ───────────────────────── MAPAS ─────────────────────────
def dados_mapa(ids_geo: list[int], votos: dict, andamento: dict) -> dict:
    """Arrays na ordem da geometria: % de Flávio entre válidos (×10, −1 sem votos), % das seções
    apuradas (×10) e variação do % de Flávio (entre Flávio e Lula) em relação ao 1º turno (×10)."""
    b = base_1turno()["mun"]
    pf, ap, sw = [], [], []
    for cdi in ids_geo:
        m = votos.get(cdi)
        f, l = _votos_cand(m, NUM_F), _votos_cand(m, NUM_L)
        pst = (m or {}).get("pst")
        if pst is None:
            pst = (andamento.get(cdi) or {}).get("pst", 0.0)
        ap.append(round(10 * pst))
        if f + l > 0:
            s2 = f / (f + l)
            pf.append(round(1000 * s2))
            v1 = b.get(cdi, {}).get("vec")
            s1 = v1[0] / (v1[0] + v1[1]) if v1 is not None and v1[0] + v1[1] > 0 else s2
            sw.append(round(1000 * (s2 - s1)))
        else:
            pf.append(-1)
            sw.append(-9999)
    return {"pf": pf, "ap": ap, "sw": sw}


# ───────────────────────── HORÁRIO DA DECISÃO ─────────────────────────
def previsao_decisao(hist: list, sit: dict, proj: dict) -> dict | None:
    """Quando a vantagem deve passar o máximo que ainda pode entrar, supondo que a diferença
    caminha em linha reta até a projeção final e o ritmo de apuração (eleitores/min) se mantém."""
    if not sit or sit["R"] is None or sit["certeza"] or sit["oficial"] or not proj.get("D"):
        return None
    d = sit["d"]
    te, et = d["eleitorado"], d["eleitorado_tot"]
    if not te or et >= te:
        return None
    sinal = 1 if sit["a"]["numero"] == NUM_F else -1
    D_now, D_fim = sit["dif"], sinal * proj["D"]           # diferença a favor do líder atual
    if D_fim <= 0:
        return None
    f0 = et / te
    # D(f) = D_now + (D_fim − D_now)(f − f0)/(1 − f0) > te(1 − f) + sj
    a1 = (D_fim - D_now) / (1 - f0)
    f = (te + sit["sj"] - D_now + a1 * f0) / (a1 + te)
    if not (f0 <= f <= 1):
        return None
    ritmo = None
    pts = [h for h in hist if h.get("t") and h.get("et")]
    if len(pts) >= 2:
        recentes = [h for h in pts if h["t"] >= pts[-1]["t"] - 600] or pts[-2:]
        if len(recentes) >= 2 and recentes[-1]["t"] > recentes[0]["t"]:
            ritmo = (recentes[-1]["et"] - recentes[0]["et"]) / (recentes[-1]["t"] - recentes[0]["t"])
    seg = (f - f0) * te / ritmo if ritmo and ritmo > 0 else None
    return {"frac": 100 * f, "seg": seg}
