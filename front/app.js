/* Apuração 2026 — 2º turno. Interface do painel (componente do Streamlit sem build).
   O Python manda um objeto com todos os dados a cada atualização; aqui só desenhamos. */
"use strict";

// ───────── protocolo mínimo de componente do Streamlit ─────────
function enviar(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), "*"); }

// ───────── utilidades ─────────
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const NF = new Intl.NumberFormat("pt-BR");
const fi = n => NF.format(Math.round(n || 0));
const fp = (p, c = 2) => (p ?? 0).toFixed(c).replace(".", ",");
const MOV = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const curto = n => {
  const a = Math.abs(n);
  if (a >= 1e6) return fp(n / 1e6, a >= 1e7 ? 1 : 2) + " mi";
  if (a >= 1e3) return fi(n / 1e3) + " mil";
  return fi(n);
};
const sinal = (n, f = curto) => (n > 0 ? "+" : n < 0 ? "−" : "") + f(Math.abs(n));
const MINUSC = new Set(["de", "da", "do", "das", "dos", "e"]);
const titulo = s => (s || "").toLowerCase().split(" ").map((p, i) => i && MINUSC.has(p) ? p : p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// número que desliza até o novo valor
function tween(el, para, fmt, dur = 1100) {
  if (!el) return;
  const de = el.__v ?? 0;
  el.__v = para;
  if (!MOV || de === para) { el.textContent = fmt(para); return; }
  const t0 = performance.now();
  cancelAnimationFrame(el.__raf);
  const passo = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
    el.textContent = fmt(de + (para - de) * e);
    if (k < 1) el.__raf = requestAnimationFrame(passo);
  };
  el.__raf = requestAnimationFrame(passo);
}

// ───────── cores ─────────
const COR = { F: "#187BD1", L: "#E91D24", Fc: "#5697DC", Lc: "#F26359", ouro: "#FACB0E" };
const FAIXA_F = ["#187BD1", "#5498DE", "#83B5EA", "#ACCFF5"];   // ≥70, 58–70, 53–58, 51,3–53
const FAIXA_L = ["#E91D24", "#F36359", "#F99287", "#FCB9B1"];
const NEUTRO = "#ECEBE4", SEM = "#1D201E";
const ROXO = ["#EEEEF2", "#DCD9EA", "#C9C5E2", "#B7B1DA", "#A69DD1", "#9589C8", "#8475BE", "#7561B5", "#654DAB", "#5737A1", "#4A1D96"];
const DIV_F = ["#DEE9F5", "#C8DCF2", "#B1CEEE", "#9BC1EA", "#84B3E5", "#6DA5E1", "#5697DC", "#3B89D6", "#187BD1"];
const DIV_L = ["#F5E3E1", "#F8CFCA", "#F9BBB3", "#F9A79D", "#F89186", "#F57B70", "#F26359", "#EE4741", "#E91D24"];
const FAIXAS = ["70% ou mais", "De 58% a 70%", "De 53% a 58%", "De 51,3% a 53%"];

function lerpHex(a, b, t) {
  const pa = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16)), pb = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return "#" + pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
function escala(stops, t) {
  t = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(t));
  return lerpHex(stops[i], stops[i + 1], t - i);
}
function faixa(pf) {               // pf = % de Flávio ×10 entre os válidos
  const lider = Math.max(pf, 1000 - pf) / 10;
  return lider >= 70 ? 0 : lider >= 58 ? 1 : lider >= 53 ? 2 : lider > 51.3 ? 3 : 4;
}
function corVencedor(pf) {
  if (pf < 0) return SEM;
  const k = faixa(pf);
  if (k === 4) return NEUTRO;
  return (pf > 500 ? FAIXA_F : FAIXA_L)[k];
}
const corApuracao = ap => escala(ROXO, ap / 1000);
function corVariacao(sw) {
  if (sw === -9999) return SEM;
  const t = Math.min(1, Math.abs(sw) / 120);       // 12 p.p. já é a cor cheia
  return escala(sw >= 0 ? DIV_F : DIV_L, t);
}

// ───────── estado ─────────
let D = null, geo = null, caminhos = [], modo = "vencedor", tela = "agora", primeira = true, rotTimer = null;

// ───────── navegação ─────────
function irPara(nova, anima = true) {
  if (nova === tela && $("#" + nova).classList.contains("ativa")) return;
  tela = nova;
  $$("nav button").forEach(b => b.dataset.tela === nova ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  $$(".tela").forEach(s => {
    const on = s.id === nova;
    s.classList.toggle("ativa", on);
    s.classList.remove("entrando");
    if (on && anima && MOV) { void s.offsetWidth; s.classList.add("entrando"); }
  });
  if (nova === "agora" && D) desenharCurva(D);
  if (nova === "modelo" && D) desenharNoite(D);
  if (nova === "mapa") montarMapa();
}
$$("nav button").forEach(b => b.addEventListener("click", () => { pararRotacao(); irPara(b.dataset.tela); }));
document.addEventListener("keydown", e => {
  const ordem = ["agora", "mapa", "estados", "modelo"];
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const i = ordem.indexOf(tela) + (e.key === "ArrowRight" ? 1 : -1);
    pararRotacao();
    irPara(ordem[(i + ordem.length) % ordem.length]);
  }
});
$$(".modos button").forEach(b => b.addEventListener("click", () => {
  modo = b.dataset.modo;
  $$(".modos button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
  pintarMapa(); legendaMapa();
}));
function iniciarRotacao(seg) {
  if (rotTimer || !seg) return;
  const ordem = ["agora", "mapa", "estados", "modelo"];
  rotTimer = setInterval(() => irPara(ordem[(ordem.indexOf(tela) + 1) % ordem.length]), seg * 1000);
}
function pararRotacao() { clearInterval(rotTimer); rotTimer = null; }

// ───────── tela AGORA ─────────
function nomeCurto(k) { return k === "F" ? "Flávio" : "Lula"; }

function renderAgora(d) {
  const c = d.cand, s = d.sit, n = d.nac, p = d.proj;
  // manchete
  const h1 = $("#manchete"), sub = $("#manchete-sub");
  h1.classList.remove("eleito");
  if (!s) { h1.textContent = "Aguardando os primeiros votos"; sub.textContent = ""; }
  else {
    const lid = c[s.lider], seg = c[s.lider === "F" ? "L" : "F"];
    if (s.oficial) {
      h1.textContent = `${titulo(lid.nome)} está eleito presidente`; h1.classList.add("eleito");
      sub.textContent = "Resultado proclamado pelo TSE.";
    } else if (s.certeza) {
      h1.textContent = `${titulo(lid.nome)} está matematicamente eleito`; h1.classList.add("eleito");
      sub.textContent = `A vantagem de ${fi(s.dif)} votos já supera os ${fi(n.R + n.sj)} que ainda podem entrar. O TSE ainda não proclamou.`;
    } else {
      h1.textContent = `${titulo(lid.nome)} lidera por ${fi(s.dif)} votos`;
      if (p && p.ok) {
        const vp = p.s_f >= 50 ? "F" : "L";
        sub.textContent = vp === s.lider
          ? `O modelo projeta ${titulo(c[vp].nome)} com ${fp(vp === "F" ? p.s_f : 100 - p.s_f, 1)}% ao final.`
          : `O modelo projeta virada: ${titulo(c[vp].nome)} com ${fp(vp === "F" ? p.s_f : 100 - p.s_f, 1)}% ao final.`;
      } else sub.textContent = p ? p.motivo : "";
    }
  }
  // placar
  for (const k of ["F", "L"]) {
    const ganhou = s && (s.oficial || s.certeza) && s.lider === k;
    $("#lado-" + k).classList.toggle("venceu", !!ganhou);
    $(`[data-selo="${k}"]`).textContent = s && s.oficial ? "Eleito" : "Matematicamente eleito";
    $(`[data-nome="${k}"]`).textContent = titulo(c[k].nome);
    tween($(`[data-pct="${k}"]`), c[k].pct, v => fp(v));
    tween($(`[data-votos="${k}"]`), c[k].votos, fi);
  }
  const tot = c.F.pct + c.L.pct || 100;
  $("#cabo-L").style.flexBasis = (100 * c.L.pct / tot) + "%";
  $("#cabo-F").style.flexBasis = (100 * c.F.pct / tot) + "%";
  const ap = n.te ? 100 * n.et / n.te : n.pst;
  $("#barra-apuracao").style.width = ap + "%";
  // números
  tween($("#n-secoes"), n.pst, v => fp(v) + "%");
  $("#n-secoes-sub").textContent = `${fi(n.secoes[0])} de ${fi(n.secoes[1])} seções`;
  tween($("#n-eleitorado"), ap, v => fp(v) + "%");
  $("#n-eleitorado-sub").textContent = `${fi(n.et)} de ${fi(n.te)} aptos`;
  tween($("#n-dif"), s ? s.dif : 0, fi);
  $("#n-dif-sub").textContent = s ? `votos de diferença, ${fp(s.dif_pp)} p.p.` : "votos de diferença";
  $("#n-dif").style.color = s ? (s.oficial || s.certeza ? COR.ouro : COR[s.lider + "c"]) : "";
  if (n.R == null) $("#n-resta").textContent = "—"; else tween($("#n-resta"), n.R + n.sj, fi);
  const vz = $("#n-virar"), vs = $("#n-virar-sub");
  if (!s || s.virar_est == null) { vz.textContent = "—"; vs.textContent = "para virar"; }
  else {
    const seg = s.lider === "F" ? "L" : "F";
    vs.textContent = `dos votos restantes para ${nomeCurto(seg)} virar`;
    if (s.virar_max == null || s.virar_max > 100) { vz.textContent = "Impossível"; vz.style.color = COR.ouro; }
    else { tween(vz, s.virar_est, v => fp(v, 1) + "%"); vz.style.color = COR[seg + "c"]; }
  }
  renderProjecao(d);
  desenharCurva(d);
  renderRegioes(d);
}

function renderProjecao(d) {
  const p = d.proj;
  $("#proj-rotulo").textContent = p && p.ok ? "Projeção para 100% das urnas" : "Projeção proporcional (modelo calibrando)";
  if (!p || p.s_f == null) { $$("[data-proj]").forEach(e => e.textContent = "—"); return; }
  tween($('[data-proj="F"]'), p.s_f, v => fp(v, 1) + "%");
  tween($('[data-proj="L"]'), 100 - p.s_f, v => fp(v, 1) + "%");
  // intervalo: eixo de Lula 54% a Flávio 54%
  const pos = s => Math.max(0, Math.min(100, (s - 46) / 8 * 100));
  const fx = $("#ic-faixa");
  if (p.ic) { fx.style.left = pos(p.ic[0]) + "%"; fx.style.width = (pos(p.ic[1]) - pos(p.ic[0])) + "%"; fx.classList.remove("oculto");
    $("#ic-txt").textContent = `95%: Flávio de ${fp(p.ic[0], 1)}% a ${fp(p.ic[1], 1)}%`; }
  else { fx.classList.add("oculto"); $("#ic-txt").textContent = "sem intervalo ainda"; }
  $("#ic-ponto").style.left = `calc(${pos(p.s_f)}% - 1px)`;
  const pf = p.prob_f;
  if (pf == null) { $("#ch-F").style.flexBasis = "50%"; $("#ch-L").style.flexBasis = "50%"; $("#ch-F-txt").textContent = "—"; $("#ch-L-txt").textContent = "—"; }
  else {
    $("#ch-F").style.flexBasis = (100 * pf) + "%"; $("#ch-L").style.flexBasis = (100 * (1 - pf)) + "%";
    const txt = v => v > .995 ? "mais de 99%" : v < .005 ? "menos de 1%" : fp(100 * v, 0) + "%";
    $("#ch-F-txt").textContent = "Flávio " + txt(pf); $("#ch-L-txt").textContent = "Lula " + txt(1 - pf);
  }
  const partes = [];
  if (d.eta) partes.push(d.eta.hora
    ? `Decisão matemática prevista para por volta de <b>${d.eta.hora}</b>, com ${fp(d.eta.frac, 0)}% do eleitorado apurado.`
    : `Decisão matemática prevista com cerca de <b>${fp(d.eta.frac, 0)}%</b> do eleitorado apurado.`);
  if (p.ok) partes.push(`Ajustado em ${fi(p.n)} municípios de ${p.n_ufs} estados; erro médio de ${fp(p.mae, 1)} p.p. por município.`);
  else partes.push(esc(p.motivo));
  $("#proj-nota").innerHTML = partes.join(" ");
}

function desenharCurva(d) {
  const svg = $("#curva");
  const W = svg.clientWidth, H = svg.clientHeight;
  if (!W || !H) return;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const h = d.hist || [];
  const m = { l: 44, r: 8, t: 10, b: 22 };
  const lim = Math.max(4, ...h.flatMap(p => [Math.abs(p[1] ?? 0), Math.abs(p[2] ?? 0)])) * 1.12;
  const X = x => m.l + (W - m.l - m.r) * x / 100;
  const Y = y => m.t + (H - m.t - m.b) * (1 - (y + lim) / (2 * lim));
  let o = "";
  for (const t of [0, 25, 50, 75, 100]) o += `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}" stroke="#2A2C28"/>
    <text x="${X(t)}" y="${H - 6}" text-anchor="${t === 0 ? "start" : t === 100 ? "end" : "middle"}">${t}%</text>`;
  o += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="#A6A48F"/>`;
  const rl = Math.round(lim);
  o += `<text x="${m.l - 6}" y="${Y(lim) + 10}" text-anchor="end" fill="${COR.Fc}">F +${rl}</text>
        <text x="${m.l - 6}" y="${Y(-lim) - 2}" text-anchor="end" fill="${COR.Lc}">L +${rl}</text>`;
  // contagem: segmentos coloridos pelo lado que lidera
  const pts = h.filter(p => p[1] != null);
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if ((a[1] >= 0) === (b[1] >= 0)) {
      o += `<line x1="${X(a[0])}" y1="${Y(a[1])}" x2="${X(b[0])}" y2="${Y(b[1])}" stroke="${a[1] >= 0 ? COR.F : COR.L}" stroke-width="2.5" stroke-linecap="round"/>`;
    } else {
      const t = a[1] / (a[1] - b[1]), xm = a[0] + (b[0] - a[0]) * t;
      o += `<line x1="${X(a[0])}" y1="${Y(a[1])}" x2="${X(xm)}" y2="${Y(0)}" stroke="${a[1] >= 0 ? COR.F : COR.L}" stroke-width="2.5"/>
            <line x1="${X(xm)}" y1="${Y(0)}" x2="${X(b[0])}" y2="${Y(b[1])}" stroke="${b[1] >= 0 ? COR.F : COR.L}" stroke-width="2.5"/>`;
    }
  }
  const pj = h.filter(p => p[2] != null);
  if (pj.length > 1) o += `<polyline fill="none" stroke="#FFFCE1" stroke-width="1.5" stroke-dasharray="5 5" points="${pj.map(p => `${X(p[0])},${Y(p[2])}`).join(" ")}"/>`;
  const ult = pts[pts.length - 1];
  if (ult) o += `<circle cx="${X(ult[0])}" cy="${Y(ult[1])}" r="4.5" fill="${ult[1] >= 0 ? COR.F : COR.L}" stroke="#0E100F" stroke-width="2"/>`;
  if (!pts.length) o += `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">A curva aparece com os primeiros votos</text>`;
  svg.innerHTML = o;
}

function renderRegioes(d) {
  const rs = (d.rec && d.rec.regioes) || [];
  const box = $("#regioes");
  const lim = Math.max(1, ...rs.flatMap(r => [Math.abs(r.f - r.l), Math.abs(r.fp - r.lp)])) * 1.08;
  if (box.children.length !== rs.length) box.innerHTML = rs.map(r => `<div class="reg"><span class="nm">${esc(r.nome)}</span>
      <div class="divergente"><i></i><u></u></div><span class="vl"></span><span class="ap"></span></div>`).join("");
  rs.forEach((r, k) => {
    const el = box.children[k], sd = r.f - r.l, sp = r.fp - r.lp;
    const w = 50 * Math.abs(sd) / lim, bar = $("i", el);
    bar.style.background = sd >= 0 ? COR.F : COR.L;
    bar.style.left = sd >= 0 ? "50%" : (50 - w) + "%"; bar.style.width = w + "%";
    const u = $("u", el); u.style.left = `calc(${50 + 50 * sp / lim}% - 1px)`; u.style.display = r.fp + r.lp > 0 ? "" : "none";
    const t = $(".vl", el);
    t.textContent = sinal(sd); t.style.color = sd > 0 ? COR.Fc : sd < 0 ? COR.Lc : "#A6A48F";
    $(".ap", el).textContent = fp(r.ap, 0) + "%";
  });
}

// ───────── MAPA ─────────
const MODOS = {
  vencedor: ["Quem vence em cada município", "Cor pela porcentagem do vencedor entre os votos válidos já apurados."],
  apuracao: ["Quanto já foi apurado", "Do branco, sem nenhuma seção totalizada, ao roxo escuro, com 100% das seções."],
  variacao: ["O que mudou desde o 1º turno", "Quanto a fatia de Flávio entre os dois finalistas subiu ou caiu em relação ao 1º turno."],
};

function montarMapa() {
  if (!geo || caminhos.length) return;
  const svg = $("#svgmapa");
  svg.setAttribute("viewBox", `0 0 ${geo.w} ${geo.h}`);
  const NS = "http://www.w3.org/2000/svg", fr = document.createDocumentFragment();
  geo.p.forEach((dd, i) => { const p = document.createElementNS(NS, "path"); p.setAttribute("d", dd); p.setAttribute("fill", SEM); p.dataset.i = i; fr.appendChild(p); caminhos.push(p); });
  $("#mun").appendChild(fr);
  geo.uf.forEach(dd => { const p = document.createElementNS(NS, "path"); p.setAttribute("d", dd); $("#uf").appendChild(p); });
  $("#mapa-carregando").remove();
  const dica = $("#dica");
  $("#mun").addEventListener("mousemove", ev => {
    const i = ev.target.dataset && ev.target.dataset.i;
    if (i === undefined || !D) { dica.style.display = "none"; return; }
    const m = D.mapa, pf = m.pf[i] ?? -1, ap = (m.ap[i] ?? 0) / 10, sw = m.sw[i];
    let html = `<b>${esc(titulo(geo.nm[i]))}</b>`;
    if (pf < 0) html += "Sem votos totalizados";
    else {
      html += `<span style="color:${COR.Fc}">Flávio ${fp(pf / 10, 1)}%</span>&nbsp;&nbsp;<span style="color:${COR.Lc}">Lula ${fp(100 - pf / 10, 1)}%</span>`;
      if (sw !== -9999) html += `<br>${sw >= 0 ? "Flávio" : "Lula"} ${sw === 0 ? "igual" : "+" + fp(Math.abs(sw) / 10, 1) + " p.p."} desde o 1º turno`;
    }
    html += `<br>${fp(ap, 1)}% das seções apuradas`;
    dica.innerHTML = html; dica.style.display = "block";
    dica.style.left = Math.min(ev.clientX + 16, innerWidth - dica.offsetWidth - 8) + "px";
    dica.style.top = Math.min(ev.clientY + 16, innerHeight - dica.offsetHeight - 8) + "px";
  });
  $("#mun").addEventListener("mouseleave", () => dica.style.display = "none");
  pintarMapa(); legendaMapa();
}

function pintarMapa() {
  if (!D || !caminhos.length) return;
  const m = D.mapa;
  const f = modo === "vencedor" ? i => corVencedor(m.pf[i] ?? -1) : modo === "apuracao" ? i => corApuracao(m.ap[i] ?? 0) : i => corVariacao(m.sw[i] ?? -9999);
  for (let i = 0; i < caminhos.length; i++) caminhos[i].setAttribute("fill", f(i));
}

function legendaMapa() {
  if (!D) return;
  const m = D.mapa, n = m.pf.length;
  $("#modo-tit").textContent = MODOS[modo][0];
  $("#modo-desc").textContent = MODOS[modo][1];
  let leg = "", cont = "";
  if (modo === "vencedor") {
    const c = { F: [0, 0, 0, 0], L: [0, 0, 0, 0], n: 0, s: 0 };
    m.pf.forEach(pf => { if (pf < 0) { c.s++; return; } const k = faixa(pf); if (k === 4) c.n++; else c[pf > 500 ? "F" : "L"][k]++; });
    const col = (k, nome, cores) => `<div><h3 style="color:${COR[k + "c"]}">${nome}</h3><div class="legenda">${cores.map((cor, j) =>
      `<div class="leg-lin"><i style="background:${cor}"></i><span>${FAIXAS[j]}</span><b>${fi(c[k][j])}</b></div>`).join("")}</div></div>`;
    leg = `<div class="leg-cols">${col("F", "Flávio", FAIXA_F)}${col("L", "Lula", FAIXA_L)}</div>
      <div class="legenda" style="margin-top:1.4vh"><div class="leg-lin"><i style="background:${NEUTRO}"></i><span>De 50% + 1 voto a 51,3%, para qualquer lado</span><b>${fi(c.n)}</b></div>
      <div class="leg-lin"><i style="background:${SEM};outline:1px solid #2A2C28"></i><span>Sem votos totalizados</span><b>${fi(c.s)}</b></div></div>`;
    const vf = c.F.reduce((a, b) => a + b, 0), vl = c.L.reduce((a, b) => a + b, 0);
    cont = `<div><b style="color:${COR.Fc}">${fi(vf)}</b><span>municípios com Flávio à frente</span></div>
            <div><b style="color:${COR.Lc}">${fi(vl)}</b><span>municípios com Lula à frente</span></div>`;
  } else if (modo === "apuracao") {
    const tot = m.ap.filter(a => a >= 1000).length, zero = m.ap.filter(a => a <= 0).length;
    leg = `<div class="gradiente" style="background:linear-gradient(90deg,${ROXO.join(",")})"></div><div class="grad-txt"><span>0%</span><span>50%</span><span>100% das seções</span></div>`;
    cont = `<div><b>${fi(tot)}</b><span>municípios completos</span></div><div><b>${fi(n - tot - zero)}</b><span>em apuração</span></div><div><b>${fi(zero)}</b><span>sem nenhuma seção</span></div>`;
  } else {
    const sf = m.sw.filter(s => s !== -9999 && s > 0).length, sl = m.sw.filter(s => s !== -9999 && s < 0).length;
    leg = `<div class="gradiente" style="background:linear-gradient(90deg,${[...DIV_L].reverse().join(",")},${DIV_F.join(",")})"></div>
      <div class="grad-txt"><span style="color:${COR.Lc}">Lula +12 p.p.</span><span>igual</span><span style="color:${COR.Fc}">Flávio +12 p.p.</span></div>`;
    cont = `<div><b style="color:${COR.Fc}">${fi(sf)}</b><span>municípios onde Flávio cresceu</span></div><div><b style="color:${COR.Lc}">${fi(sl)}</b><span>onde Lula cresceu</span></div>`;
  }
  $("#legenda").innerHTML = leg;
  $("#contagem").innerHTML = cont;
  const li = (x, k) => `<li><span>${esc(x.nome)} (${x.uf.toUpperCase()})</span><b style="color:${COR[k + "c"]}">${sinal(x.saldo, fi)}</b></li>`;
  $("#top-F").innerHTML = (D.rec.top_f || []).slice(0, 6).map(x => li(x, "F")).join("") || "<li><span>Sem dados ainda</span></li>";
  $("#top-L").innerHTML = (D.rec.top_l || []).slice(0, 6).map(x => li(x, "L")).join("") || "<li><span>Sem dados ainda</span></li>";
}

// ───────── ESTADOS ─────────
function renderEstados(d) {
  const ufs = [...(d.rec.ufs || [])].sort((a, b) => ((b.fp - b.lp) || (b.f - b.l)) - ((a.fp - a.lp) || (a.f - a.l)));
  const lim = Math.max(1, ...ufs.map(u => Math.abs(u.fp - u.lp)));
  const cor = sd => sd >= 0 ? COR.Fc : COR.Lc;
  let o = `<div class="cab"></div><div class="cab">Estado</div><div class="cab">Apurado</div><div class="cab r">Flávio</div>
    <div class="cab r">Lula</div><div class="cab r">Saldo agora</div><div class="cab" style="justify-content:center">Saldo projetado</div>`;
  for (const u of ufs) {
    const v = u.f + u.l, pf = v ? 100 * u.f / v : null, sa = u.f - u.l, sp = u.fp - u.lp;
    const w = 30 * Math.abs(sp) / lim;
    const rot = sp >= 0 ? `left:calc(${50 + w}% + 6px)` : `right:calc(${50 + w}% + 6px)`;
    o += `<div class="sg">${u.uf === "zz" ? "EXT" : u.uf.toUpperCase()}</div><div>${esc(u.nome)}</div>
      <div class="apc"><div class="ap-bar"><i style="width:${u.ap}%"></i></div><span>${fp(u.ap, 0)}%</span></div>
      <div class="r" style="color:${COR.Fc}">${pf == null ? "—" : fp(pf, 1) + "%"}</div>
      <div class="r" style="color:${COR.Lc}">${pf == null ? "—" : fp(100 - pf, 1) + "%"}</div>
      <div class="r" style="color:${v ? cor(sa) : "#A6A48F"}">${v ? sinal(sa) : "—"}</div>
      <div class="dv">${sp ? `<i style="background:${sp >= 0 ? COR.F : COR.L};${sp >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%"></i>
        <span style="${rot};color:${cor(sp)}">${sinal(sp)}</span>` : ""}</div>`;
  }
  $("#tabela-uf").innerHTML = o;
  let c = `<div class="cab">Capital</div><div class="cab r">Flávio</div><div class="cab r">Lula</div><div class="cab r">Apurado</div>`;
  for (const x of d.rec.capitais || []) {
    const v = x.f + x.l, pf = v ? 100 * x.f / v : null;
    const lid = pf == null ? "" : pf >= 50 ? `style="color:${COR.Fc}"` : `style="color:${COR.Lc}"`;
    c += `<div ${lid}>${esc(x.nome)} <span style="color:#A6A48F">${x.uf.toUpperCase()}</span></div>
      <div class="r">${pf == null ? "—" : fp(pf, 1) + "%"}</div><div class="r">${pf == null ? "—" : fp(100 - pf, 1) + "%"}</div><div class="r">${fp(x.pst, 0)}%</div>`;
  }
  $("#tabela-cap").innerHTML = c;
}

// ───────── MODELO ─────────
const GRUPOS = [["Eleitores de Flávio", "F"], ["Eleitores de Lula", "L"], ["Outros candidatos", "O"], ["Branco ou nulo", "BN"], ["Não votou", "A"]];
const CORES_DEST = [COR.F, COR.L, "#8E8C79", "#3A3C37"];
function renderModelo(d) {
  const p = d.proj, g = d.grupos || {};
  if (!p || !p.trans) {
    $("#fluxos").innerHTML = `<p class="texto">${esc(p ? p.motivo : "Aguardando dados.")}</p>`;
    $("#fluxo-nota").textContent = "";
  } else {
    const box = $("#fluxos");
    if (box.children.length !== 5) box.innerHTML = GRUPOS.map(([nome, k]) => `<div class="fluxo"><div class="nm">${nome}<small>${curto(g[k] || 0)} no 1º turno</small></div>
      <div class="pilha">${CORES_DEST.map((cor, j) => `<i style="background:${cor};color:${j === 2 ? "#0E100F" : "#FFFCE1"};flex:0 0 25%"></i>`).join("")}</div></div>`).join("");
    p.trans.forEach((row, r) => $$("i", box.children[r]).forEach((el, j) => {
      el.style.flexBasis = row[j] + "%"; el.textContent = row[j] >= 7 ? fp(row[j], 0) + "%" : "";
    }));
    $("#fluxo-nota").textContent = "Inferência ecológica: compara municípios, não pessoas. As linhas dos grupos grandes são as mais firmes; a dos outros candidatos é a mais incerta.";
  }
  const fat = [];
  if (p && p.s_f != null) {
    const dp = p.F - p.L;
    fat.push([sinal(dp, curto), `diferença projetada para ${dp >= 0 ? "Flávio" : "Lula"}`]);
    fat.push([curto(p.F + p.L), "votos válidos projetados"]);
  }
  if (p && p.comparecimento) fat.push([fp(p.comparecimento, 1) + "%", "comparecimento projetado (1º turno: 78,9%)"]);
  if (p) fat.push([fi(p.n), `municípios usados no ajuste, ${fp(p.cobertura, 1)}% do eleitorado`]);
  if (p && p.mae != null) fat.push([fp(p.mae, 1) + " p.p.", "erro médio do modelo por município"]);
  if (d.coleta) fat.push([fi(d.coleta.municipios), d.coleta.fila ? `municípios lidos, ${fi(d.coleta.fila)} na fila` : "municípios lidos do TSE"]);
  $("#fatos").innerHTML = fat.map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join("");
}

function desenharNoite(d) {
  const svg = $("#noite");
  const W = svg.clientWidth, H = svg.clientHeight;
  if (!W || !H) return;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const h = (d.hist || []).filter(p => p[3] != null || p[2] != null);
  const m = { l: 40, r: 40, t: 10, b: 22 };
  const X = x => m.l + (W - m.l - m.r) * x / 100;
  const Y = y => m.t + (H - m.t - m.b) * (1 - y / 100);           // eixo 0–100% (chance)
  const Yp = s => m.t + (H - m.t - m.b) * (1 - (s - 44) / 12);    // eixo 44–56% (projeção)
  let o = "";
  for (const t of [0, 25, 50, 75, 100]) o += `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}" stroke="#2A2C28"/>
    <text x="${X(t)}" y="${H - 6}" text-anchor="${t === 0 ? "start" : t === 100 ? "end" : "middle"}">${t}%</text>`;
  o += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(50)}" y2="${Y(50)}" stroke="#A6A48F"/>
    <text x="${m.l - 6}" y="${Y(100) + 10}" text-anchor="end">100%</text><text x="${m.l - 6}" y="${Y(0)}" text-anchor="end">0%</text>
    <text x="${W - m.r + 6}" y="${Yp(56) + 10}">56%</text><text x="${W - m.r + 6}" y="${Yp(44)}">44%</text>`;
  const pc = h.filter(p => p[3] != null);
  if (pc.length > 1) o += `<polyline fill="none" stroke="${COR.F}" stroke-width="2.5" points="${pc.map(p => `${X(p[0])},${Y(100 * p[3])}`).join(" ")}"/>`;
  const pp = h.filter(p => p[2] != null).map(p => [p[0], 50 + p[2] / 2]);
  if (pp.length > 1) o += `<polyline fill="none" stroke="#FFFCE1" stroke-width="1.5" stroke-dasharray="5 5" points="${pp.map(p => `${X(p[0])},${Yp(Math.max(44, Math.min(56, p[1])))}`).join(" ")}"/>`;
  if (pc.length < 2 && pp.length < 2) o += `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">O gráfico se forma ao longo da noite</text>`;
  svg.innerHTML = o;
}

// ───────── ciclo de dados ─────────
function render(d) {
  D = d;
  $("#hora").innerHTML = d.demo ? `Demonstração <b>${esc(d.hora)}</b>` : `TSE <b>${esc(d.hora)}</b>`;
  const pulso = $("#pulso");
  pulso.classList.toggle("falha", !!d.falha);
  if (d.hora !== pulso.__hora) {           // o TSE publicou uma atualização: o ponto pisca uma vez
    pulso.__hora = d.hora;
    pulso.classList.remove("novo"); void pulso.offsetWidth; pulso.classList.add("novo");
  }
  if (!d.cand) {
    $("#manchete").textContent = d.falha ? "Sem resposta do TSE" : "Aguardando os primeiros votos";
    $("#manchete-sub").textContent = d.falha
      ? "O painel tenta de novo a cada 5 segundos e mostra os números assim que o TSE responder."
      : "Os números aparecem quando a primeira seção for totalizada.";
    $("#proj-nota").textContent = "";
    return;
  }
  renderAgora(d);
  renderEstados(d);
  renderModelo(d);
  if (tela === "modelo") desenharNoite(d);
  pintarMapa(); legendaMapa();
  if (primeira) {
    primeira = false;
    if (d.aba && d.aba !== "agora") irPara(d.aba, false);
    iniciarRotacao(d.rotacao);
  }
}

let ultimaAltura = 0;
window.addEventListener("message", ev => {
  const m = ev.data;
  if (!m || m.type !== "streamlit:render") return;
  const a = m.args || {};
  if (a.altura && a.altura !== ultimaAltura) { ultimaAltura = a.altura; enviar("streamlit:setFrameHeight", { height: a.altura }); }
  if (a.dados) render(a.dados);
});
window.addEventListener("resize", () => { if (D && tela === "agora") desenharCurva(D); if (D && tela === "modelo") desenharNoite(D); });

fetch("geo.json").then(r => r.json()).then(g => { geo = g; if (tela === "mapa") montarMapa(); else setTimeout(montarMapa, 400); });
enviar("streamlit:componentReady", { apiVersion: 1 });
