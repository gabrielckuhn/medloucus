"""Modo demonstração: uma apuração fictícia, mas coerente em todos os níveis (município → UF → Brasil),
gerada a partir do 1º turno real com uma matriz de transferência escondida. A ordem de chegada imita
a de uma noite real (Sul/Sudeste/Centro-Oeste antes, Norte/Nordeste e capitais depois), para que dê
para ver a liderança mudar e o modelo antecipar o resultado."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from modelo import NUM_F, NUM_L, NOME_UF, REGIAO_UF, base_1turno, capitais_ibge, matriz_base

PASSOS = 90          # ~7,5 min até 100% com atualização a cada 5 s
# linhas: Flávio, Lula, outros, branco/nulo, abstenção do 1º turno → colunas: Flávio, Lula, branco/nulo
P_VERDADE = np.array([[0.935, 0.010, 0.010],
                      [0.012, 0.935, 0.010],
                      [0.470, 0.300, 0.090],
                      [0.110, 0.120, 0.540],
                      [0.035, 0.040, 0.010]])
INICIO = {"Sul": 0, "Sudeste": 6, "Centro-Oeste": 3, "Nordeste": 16, "Norte": 22, "Exterior": 30}


@lru_cache(maxsize=1)
def verdade():
    rnd = np.random.default_rng(2026)
    ids, x, te1, ufs = matriz_base()
    efeito_uf = {u: rnd.normal(0, 0.012, 2) for u in sorted(set(ufs))}
    rates = x @ P_VERDADE
    rates[:, :2] += np.array([efeito_uf[u] for u in ufs]) + rnd.normal(0, 0.022, (len(ids), 2))
    rates = np.clip(rates, 0.002, 0.98)
    final = rates * te1[:, None]
    caps = capitais_ibge()
    inicio = np.array([INICIO[REGIAO_UF[u]] for u in ufs], dtype=float) + rnd.uniform(0, 14, len(ids))
    inicio += np.array([12.0 if int(i) in caps else 0.0 for i in ids])      # capitais demoram mais
    dur = rnd.uniform(10, 28, len(ids)) + np.log10(np.maximum(te1, 10)) * 4
    zz = base_1turno()["zz"]
    zz_final = (zz[:5] / zz[5]) @ P_VERDADE * zz[5]
    return ids, te1, ufs, final, inicio, dur, zz_final


def _cands(f: float, l: float) -> list[dict]:
    v = max(f + l, 1)
    cs = [{"nome": "FLAVIO BOLSONARO", "numero": NUM_F, "partido": "PL", "votos": int(f), "pct": 100 * f / v,
           "situacao": "", "eleito": False, "foto": ""},
          {"nome": "LULA", "numero": NUM_L, "partido": "PT", "votos": int(l), "pct": 100 * l / v,
           "situacao": "", "eleito": False, "foto": ""}]
    return sorted(cs, key=lambda c: -c["votos"])


def _dados(f, l, bn, te, et, secoes_tot) -> dict:
    pst = 100 * et / te if te else 0.0
    return {"pst": pst, "secoes": (int(secoes_tot * pst / 100), int(secoes_tot)), "cands": _cands(f, l),
            "eleitorado": int(te), "eleitorado_tot": int(et), "validos": int(f + l), "sub_judice": 0,
            "comparecimento": int(f + l + bn), "brancos_nulos": int(bn), "atualizado": ""}


def carregar_demo(passo: float):
    """Mesma interface do modo real: (nac, ufs, votos municipais, andamento municipal)."""
    ids, te1, ufs, final, inicio, dur, zz_final = verdade()
    frac = np.clip((passo - inicio) / dur, 0, 1)
    obs = final * frac[:, None]
    et = te1 * frac
    votos, andamento = {}, {}
    for k, i in enumerate(ids):
        i = int(i)
        andamento[i] = {"te": int(te1[k]), "est": int(et[k]), "pst": 100 * frac[k]}
        if frac[k] > 0:
            votos[i] = {"v": {NUM_F: int(obs[k, 0]), NUM_L: int(obs[k, 1])}, "pst": 100 * frac[k],
                        "te": int(te1[k]), "est": int(et[k]), "c": int(obs[k].sum()), "bn": int(obs[k, 2])}
    ufs_out = {}
    tot = np.zeros(5)
    for u in NOME_UF:
        if u == "zz":
            continue
        mk = ufs == u
        f, l, bn = obs[mk].sum(0)
        te, e = te1[mk].sum(), et[mk].sum()
        ufs_out[u] = {"dados": _dados(f, l, bn, te, e, te / 400), "erro": None}
        tot += [f, l, bn, te, e]
    zf = float(np.clip((passo - INICIO["Exterior"]) / 30, 0, 1))
    zzb = base_1turno()["zz"]
    z = zz_final * zf
    ufs_out["zz"] = {"dados": _dados(z[0], z[1], z[2], zzb[5], zzb[5] * zf, zzb[5] / 400), "erro": None}
    tot += [z[0], z[1], z[2], zzb[5], zzb[5] * zf]
    nac = {"dados": _dados(*tot, tot[3] / 400), "erro": None}
    return nac, ufs_out, votos, andamento
