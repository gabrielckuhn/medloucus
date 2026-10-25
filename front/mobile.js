/* Escolha inicial (celular ou computador) e versão para celular em uma página só.
   Usa as funções e cores de app.js (carregado antes). A versão de computador não depende deste arquivo
   além da escolha: escolher "Computador" só fecha a tela de escolha. */
"use strict";

let modoTela = null;          // null até a pessoa escolher; "pc" ou "mobile"
let mMapaModo = "vencedor", mVideos = "", mRevelador = null;

// ───────── escolha ─────────
const ICONE_CEL = `<svg viewBox="0 0 60 100" fill="none" stroke="currentColor" stroke-width="3"><rect x="4" y="3" width="52" height="94" rx="9"/><line x1="22" y1="88" x2="38" y2="88"/></svg>`;
const ICONE_PC = `<svg viewBox="0 0 150 100" fill="none" stroke="currentColor" stroke-width="3"><rect x="4" y="3" width="142" height="78" rx="4"/><line x1="55" y1="97" x2="95" y2="97"/><line x1="75" y1="81" x2="75" y2="97"/></svg>`;

function paramDoEndereco(nome) {
  try { return new URLSearchParams(window.parent.location.search).get(nome); } catch (e) { return null; }
}

function montarEscolha() {
  const celPrimeiro = window.innerWidth < 900;
  const op = (m, icone, t, s) => `<button class="esc-op" data-modo="${m}">${icone}${(m === "mobile") === celPrimeiro ? "<em>Indicado para esta tela</em>" : ""}
    <b>${t}</b><span>${s}</span></button>`;
  const el = document.createElement("div");
  el.id = "escolha";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "Escolha a versão do painel");
  el.innerHTML = `<div class="esc-topo"><b>Apuração 2026</b><span>Presidente, 2º turno</span></div>
    <p class="esc-pergunta">Onde você vai acompanhar a apuração?</p>
    <div class="esc-opcoes">
      ${op("mobile", ICONE_CEL, "Celular", "Tudo numa página só, para rolar com o dedo.")}
      ${op("pc", ICONE_PC, "Computador ou TV", "Painel em cinco telas, com mapas grandes e os vídeos ao vivo.")}
    </div>`;
  document.body.appendChild(el);
  el.querySelectorAll(".esc-op").forEach(b => b.addEventListener("click", () => escolherModo(b.dataset.modo)));
  const sugerido = el.querySelector(`.esc-op[data-modo="${celPrimeiro ? "mobile" : "pc"}"]`);
  sugerido && sugerido.focus({ preventScroll: true });
}

function escolherModo(m) {
  modoTela = m === "mobile" ? "mobile" : "pc";
  const el = document.getElementById("escolha");
  if (el) { el.classList.add("saindo"); setTimeout(() => el.remove(), MOV ? 700 : 0); }
  if (modoTela === "mobile") {
    document.documentElement.classList.add("m");
    $("#g-videos").innerHTML = ""; videosMontados = "";        // um par de vídeos só
    montarFeed();
    if (D) renderFeed(D);
    window.scrollTo(0, 0);
  } else {
    document.documentElement.classList.remove("m");
    const f = document.getElementById("feed"); if (f) f.innerHTML = "";
    mVideos = "";
    if (D) render(D);                                          // monta os vídeos e o resto do PC
  }
}

// ───────── feed ─────────
const H2 = (t, desc) => `<h2 class="rt"><span>${t}</span></h2>${desc ? `<p class="m-desc r">${desc}</p>` : ""}<div class="m-fio rl"></div>`;

function montarFeed() {
  const f = document.getElementById("feed");
  f.innerHTML = `
  <header class="m-barra" id="m-barra">
    <div class="m-barra-lin"><b>Apuração 2026</b>
      <div class="m-mini" aria-hidden="true"><span class="F" id="m-mini-F">—</span><span class="L" id="m-mini-L">—</span></div>
      <div class="m-relogio"><i id="m-pulso"></i><span id="m-hora">Conectando</span></div></div>
    <div class="m-progresso"><i id="m-prog" style="width:0"></i></div>
  </header>

  <section class="m-heroi" id="m-heroi">
    <p class="m-status r" id="m-status">Aguardando os primeiros votos</p>
    <div class="m-lado F r" id="m-lado-F"><div class="nm">Flávio Bolsonaro</div>
      <div class="pc"><span id="m-pct-F">0,00</span><small>%</small></div>
      <div class="vt"><b id="m-vt-F">0</b> votos</div><span class="selo" id="m-selo-F">Eleito</span></div>
    <div class="r"><div class="m-cabo"><i class="F" id="m-cabo-F"></i><i class="L" id="m-cabo-L"></i><u></u></div></div>
    <div class="m-lado L r" id="m-lado-L"><div class="nm">Lula</div>
      <div class="pc"><span id="m-pct-L">0,00</span><small>%</small></div>
      <div class="vt"><b id="m-vt-L">0</b> votos</div><span class="selo" id="m-selo-L">Eleito</span></div>
  </section>

  <section class="m-sec">
    ${H2("A apuração em números")}
    <div class="m-nums">
      <div class="r"><b id="m-secoes">0%</b><small id="m-secoes-sub">das seções totalizadas</small><div class="m-trilho"><i id="m-tr-secoes" style="width:0"></i></div></div>
      <div class="r"><b id="m-eleit">0%</b><small id="m-eleit-sub">do eleitorado apurado</small><div class="m-trilho"><i id="m-tr-eleit" style="width:0"></i></div></div>
      <div class="r largo"><b id="m-dif">0</b><small id="m-dif-sub">votos de diferença</small></div>
      <div class="r"><b id="m-resta">—</b><small>votos que ainda podem entrar</small></div>
      <div class="r"><b id="m-virar">—</b><small id="m-virar-sub">para virar</small></div>
    </div>
  </section>

  <section class="m-sec">
    ${H2("Projeção para 100% das urnas", "O modelo compara cada município com o 1º turno e estima o resultado final.")}
    <div class="m-proj r"><div class="F"><b id="m-proj-F">—</b><span>Flávio</span></div><div class="L"><b id="m-proj-L">—</b><span>Lula</span></div></div>
    <div class="r"><div class="m-ic"><span class="meio"></span><span class="faixa" id="m-ic-faixa"></span><span class="ponto" id="m-ic-ponto"></span></div>
      <div class="m-leg"><span>Lula 54%</span><span id="m-ic-txt">intervalo de 95%</span><span>Flávio 54%</span></div></div>
    <div class="r"><div class="m-chance"><i id="m-ch-F" style="background:var(--flavio);flex:0 0 50%"></i><i id="m-ch-L" style="background:var(--lula);flex:0 0 50%"></i></div>
      <div class="m-chance-txt"><span id="m-ch-F-txt" style="color:var(--flavio-claro)">—</span><span id="m-ch-L-txt" style="color:var(--lula-claro)">—</span></div></div>
    <p class="m-nota r" id="m-proj-nota"></p>
  </section>

  <section class="m-sec">
    ${H2("Ao vivo")}
    <div class="m-videos" id="m-videos"></div>
  </section>

  <section class="m-sec">
    ${H2("O mapa dos municípios")}
    <div class="m-modos r" role="group" aria-label="O que o mapa mostra">
      <button data-mm="vencedor" aria-pressed="true">Vencedor</button><button data-mm="apuracao" aria-pressed="false">Apuração</button><button data-mm="variacao" aria-pressed="false">Desde o 1º turno</button>
    </div>
    <canvas class="m-mapa r" id="m-mapa" aria-label="Mapa dos municípios"></canvas>
    <div class="m-mapa-leg r" id="m-mapa-leg"></div>
    <div class="m-cont r" id="m-mapa-cont"></div>
    <div class="m-listas">
      <div class="m-lista r"><h3 style="color:var(--flavio-claro)">Maiores saldos de Flávio</h3><ol id="m-top-F"></ol></div>
      <div class="m-lista r"><h3 style="color:var(--lula-claro)">Maiores saldos de Lula</h3><ol id="m-top-L"></ol></div>
    </div>
  </section>

  <section class="m-sec">
    ${H2("A vantagem ao longo da apuração", "Linha cheia: a contagem. Tracejada: o que o modelo projetava em cada momento.")}
    <div class="m-curva r"><svg id="m-curva" preserveAspectRatio="none"></svg></div>
  </section>

  <section class="m-sec">
    ${H2("Por região", "A barra é o saldo de agora; o traço, o projetado.")}
    <div id="m-regioes"></div>
  </section>

  <section class="m-sec">
    ${H2("Por estado", "Do maior saldo projetado de Flávio ao maior de Lula.")}
    <div class="m-ufs" id="m-ufs"></div>
  </section>

  <section class="m-sec">
    ${H2("Capitais")}
    <div class="m-lista m-caps r"><ol id="m-caps"></ol></div>
  </section>

  <section class="m-sec">
    ${H2("Para onde foram os votos do 1º turno", "Estimativa a partir dos municípios já apurados.")}
    <div id="m-fluxos"></div>
    <div class="m-dest r"><span><i style="background:var(--flavio)"></i>Flávio</span><span><i style="background:var(--lula)"></i>Lula</span>
      <span><i style="background:#8E8C79"></i>Branco ou nulo</span><span><i style="background:#3A3C37"></i>Não votou</span></div>
  </section>

  <footer class="m-rodape">
    <p class="r">Dados oficiais do TSE, atualizados a cada 5 segundos. "Matematicamente eleito" aparece quando a diferença já supera todos os votos que ainda podem entrar, mesmo antes da proclamação.</p>
    <p class="r">A projeção e a chance de vitória são estimativas: as seções que faltam podem votar diferente das já apuradas.</p>
    <button class="r" id="m-ir-pc">Ver a versão para computador</button>
  </footer>`;

  f.querySelectorAll(".m-modos button").forEach(b => b.addEventListener("click", () => {
    mMapaModo = b.dataset.mm;
    f.querySelectorAll(".m-modos button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    if (D) { pintarMapaFeed(D); legendaMapaFeed(D); }
  }));
  $("#m-ir-pc").addEventListener("click", () => escolherModo("pc"));
  prepararMovimento(f);
}

// cada elemento entra no seu tempo: atraso pela posição dentro da seção
function prepararMovimento(raiz) {
  const itens = [...raiz.querySelectorAll(".r, .rt, .rl")].filter(el => !el.classList.contains("on"));
  const ordem = new Map();
  itens.forEach(el => {
    const sec = el.closest("section, footer") || raiz;
    const i = ordem.get(sec) || 0;
    ordem.set(sec, i + 1);
    el.style.setProperty("--d", Math.min(i, 7) * 85 + "ms");
  });
  if (!MOV || !("IntersectionObserver" in window)) { itens.forEach(el => el.classList.add("on")); return; }
  if (!mRevelador) mRevelador = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("on"); mRevelador.unobserve(e.target); }
  }), { rootMargin: "0px 0px -8% 0px", threshold: .08 });
  itens.forEach(el => mRevelador.observe(el));
}

// parallax leve no herói e placar compacto na barra quando o herói sai da tela
let mRaf = 0;
window.addEventListener("scroll", () => {
  if (modoTela !== "mobile" || mRaf) return;
  mRaf = requestAnimationFrame(() => {
    mRaf = 0;
    const y = window.scrollY, h = $("#m-heroi");
    if (!h) return;
    const alt = h.offsetHeight;
    if (MOV && y < alt * 1.2) {
      $("#m-lado-F").style.transform = `translate3d(0, ${y * -0.06}px, 0)`;
      $("#m-lado-L").style.transform = `translate3d(0, ${y * -0.12}px, 0)`;
    }
    $("#m-barra").classList.toggle("compacta", y > alt * 0.72);
  });
}, { passive: true });

function montarVideosFeed(lista) {
  const chave = JSON.stringify(lista || []);
  if (chave === mVideos) return;                 // nunca recria o player
  mVideos = chave;
  $("#m-videos").innerHTML = (lista || []).slice(0, 2).map(v => {
    const id = String(v.id || "").replace(/[^A-Za-z0-9_-]/g, "");
    const src = `https://www.youtube.com/embed/${id}?autoplay=1&mute=1&playsinline=1&rel=0&modestbranding=1`;
    return `<figure class="m-video r on"><figcaption><i></i>${esc(v.titulo || "Ao vivo")}</figcaption><div class="quadro">
      ${id ? `<iframe src="${src}" title="${esc(v.titulo || "Transmissão ao vivo")}" loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
        referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>` : ""}</div></figure>`;
  }).join("");
}

function renderFeed(d) {
  if (!$("#m-barra")) return;
  $("#m-hora").innerHTML = `<span class="lbl">${d.demo ? "Demonstração" : "TSE"} </span><b>${esc(d.hora)}</b>`;
  const pulso = $("#m-pulso");
  pulso.classList.toggle("falha", !!d.falha);
  if (d.hora !== pulso.__hora) { pulso.__hora = d.hora; pulso.classList.remove("novo"); void pulso.offsetWidth; pulso.classList.add("novo"); }
  montarVideosFeed(d.videos);
  const st = $("#m-status");
  if (!d.cand) {
    st.innerHTML = d.falha ? `Sem resposta do TSE<small>O painel tenta de novo a cada 5 segundos.</small>` : "Aguardando os primeiros votos";
    return;
  }
  const c = d.cand, s = d.sit, n = d.nac, p = d.proj;
  // herói
  st.classList.toggle("eleito", !!(s && (s.oficial || s.certeza)));
  if (!s) st.textContent = "Aguardando os primeiros votos";
  else {
    const nome = titulo(c[s.lider].nome);
    st.innerHTML = s.oficial ? `${nome} está eleito presidente<small>Resultado proclamado pelo TSE.</small>`
      : s.certeza ? `${nome} está matematicamente eleito<small>A vantagem já supera os ${fi(n.R + n.sj)} votos que ainda podem entrar.</small>`
      : `${nome} lidera por ${fi(s.dif)} votos<small>${p && p.ok ? `O modelo projeta ${titulo(c[p.s_f >= 50 ? "F" : "L"].nome)} com ${fp(Math.max(p.s_f, 100 - p.s_f), 1)}% ao final.` : "Com " + fp(n.pst, 1) + "% das seções totalizadas."}</small>`;
  }
  for (const k of ["F", "L"]) {
    const ganhou = s && (s.oficial || s.certeza) && s.lider === k;
    $("#m-lado-" + k).classList.toggle("venceu", !!ganhou);
    $("#m-selo-" + k).textContent = s && s.oficial ? "Eleito" : "Matematicamente eleito";
    tween($("#m-pct-" + k), c[k].pct, v => fp(v));
    tween($("#m-vt-" + k), c[k].votos, fi);
    $("#m-mini-" + k).textContent = (k === "F" ? "Flávio " : "Lula ") + fp(c[k].pct) + "%";
  }
  const tot = c.F.pct + c.L.pct || 100;
  $("#m-cabo-F").style.flexBasis = (100 * c.F.pct / tot) + "%";
  $("#m-cabo-L").style.flexBasis = (100 * c.L.pct / tot) + "%";
  const ap = n.te ? 100 * n.et / n.te : n.pst;
  $("#m-prog").style.width = ap + "%";
  // números
  tween($("#m-secoes"), n.pst, v => fp(v) + "%");
  $("#m-secoes-sub").textContent = `${fi(n.secoes[0])} de ${fi(n.secoes[1])} seções`;
  $("#m-tr-secoes").style.width = n.pst + "%";
  tween($("#m-eleit"), ap, v => fp(v) + "%");
  $("#m-eleit-sub").textContent = `do eleitorado (${curto(n.et)} de ${curto(n.te)})`;
  $("#m-tr-eleit").style.width = ap + "%";
  tween($("#m-dif"), s ? s.dif : 0, fi);
  $("#m-dif").style.color = s ? (s.oficial || s.certeza ? COR.ouro : COR[s.lider + "c"]) : "";
  $("#m-dif-sub").textContent = s ? `votos de diferença para ${nomeCurto(s.lider)}, ${fp(s.dif_pp)} p.p.` : "votos de diferença";
  if (n.R == null) $("#m-resta").textContent = "—"; else tween($("#m-resta"), n.R + n.sj, curto);
  const vz = $("#m-virar"), vs = $("#m-virar-sub");
  if (!s || s.virar_est == null) { vz.textContent = "—"; vs.textContent = "para virar"; }
  else {
    const o = s.lider === "F" ? "L" : "F";
    vs.textContent = `do restante para ${nomeCurto(o)} virar`;
    if (s.virar_max == null || s.virar_max > 100) { vz.textContent = "Impossível"; vz.style.color = COR.ouro; }
    else { tween(vz, s.virar_est, v => fp(v, 1) + "%"); vz.style.color = COR[o + "c"]; }
  }
  // projeção
  if (p && p.s_f != null) {
    tween($("#m-proj-F"), p.s_f, v => fp(v, 1) + "%"); tween($("#m-proj-L"), 100 - p.s_f, v => fp(v, 1) + "%");
    const pos = x => Math.max(0, Math.min(100, (x - 46) / 8 * 100));
    const fx = $("#m-ic-faixa");
    if (p.ic) { fx.style.left = pos(p.ic[0]) + "%"; fx.style.width = (pos(p.ic[1]) - pos(p.ic[0])) + "%"; fx.style.visibility = "";
      $("#m-ic-txt").textContent = `95%: Flávio de ${fp(p.ic[0], 1)}% a ${fp(p.ic[1], 1)}%`; }
    else { fx.style.visibility = "hidden"; $("#m-ic-txt").textContent = "sem intervalo ainda"; }
    $("#m-ic-ponto").style.left = `calc(${pos(p.s_f)}% - 1px)`;
  }
  const pf = p ? p.prob_f : null;
  const txt = v => v > .995 ? "mais de 99%" : v < .005 ? "menos de 1%" : fp(100 * v, 0) + "%";
  $("#m-ch-F").style.flexBasis = (pf == null ? 50 : 100 * pf) + "%"; $("#m-ch-L").style.flexBasis = (pf == null ? 50 : 100 * (1 - pf)) + "%";
  $("#m-ch-F-txt").textContent = pf == null ? "Chance de vitória: aguardando" : "Flávio " + txt(pf);
  $("#m-ch-L-txt").textContent = pf == null ? "" : "Lula " + txt(1 - pf);
  const notas = [];
  if (d.eta) notas.push(d.eta.hora ? `Decisão matemática prevista para por volta de <b>${d.eta.hora}</b>.` : `Decisão matemática prevista com cerca de <b>${fp(d.eta.frac, 0)}%</b> do eleitorado apurado.`);
  if (p && p.ok) notas.push(`Ajustado em ${fi(p.n)} municípios; erro médio de ${fp(p.mae, 1)} p.p.`);
  else if (p) notas.push(esc(p.motivo));
  $("#m-proj-nota").innerHTML = notas.join(" ");
  // mapa, curva e listas
  pintarMapaFeed(d); legendaMapaFeed(d);
  desenharCurva(d, $("#m-curva"));
  regioesFeed(d); estadosFeed(d); capitaisFeed(d); fluxosFeed(d);
}

function pintarMapaFeed(d) {
  const cv = $("#m-mapa");
  if (!geo || !cv) return;
  if (!formas) formas = { m: geo.p.map(x => new Path2D(x)), u: geo.uf.map(x => new Path2D(x)) };
  const m = d.mapa;
  const cor = mMapaModo === "vencedor" ? i => corVencedor(m.pf[i] ?? -1)
    : mMapaModo === "apuracao" ? i => corApuracao(m.ap[i] ?? 0) : i => corVariacao(m.sw[i] ?? -9999);
  desenharMapaCanvas(cv, cor);
}

function legendaMapaFeed(d) {
  const m = d.mapa;
  let leg = "", cont = "";
  if (mMapaModo === "vencedor") {
    const c = { F: [0, 0, 0, 0], L: [0, 0, 0, 0], n: 0 };
    m.pf.forEach(pf => { if (pf < 0) return; const k = faixa(pf); if (k === 4) c.n++; else c[pf > 500 ? "F" : "L"][k]++; });
    const seg = [...[0, 1, 2, 3].map(j => [c.F[j], FAIXA_F[j]]), [c.n, NEUTRO], ...[3, 2, 1, 0].map(j => [c.L[j], FAIXA_L[j]])];
    const t = seg.reduce((a, x) => a + x[0], 0) || 1;
    leg = `<div class="m-faixas">${seg.map(x => `<i style="background:${x[1]};flex:0 0 ${100 * x[0] / t}%"></i>`).join("")}</div>
      <div class="m-grad-txt"><span style="color:var(--flavio-claro)">Flávio 70%+</span><span>até 51,3%</span><span style="color:var(--lula-claro)">Lula 70%+</span></div>`;
    cont = `<div><b style="color:${COR.Fc}">${fi(c.F.reduce((a, b) => a + b, 0))}</b><span>com Flávio à frente</span></div>
      <div><b style="color:${COR.Lc}">${fi(c.L.reduce((a, b) => a + b, 0))}</b><span>com Lula à frente</span></div>`;
  } else if (mMapaModo === "apuracao") {
    const tot = m.ap.filter(a => a >= 1000).length, zero = m.ap.filter(a => a <= 0).length;
    leg = `<div class="m-grad" style="background:linear-gradient(90deg,${ROXO.join(",")})"></div><div class="m-grad-txt"><span>0%</span><span>50%</span><span>100% das seções</span></div>`;
    cont = `<div><b>${fi(tot)}</b><span>completos</span></div><div><b>${fi(m.ap.length - tot - zero)}</b><span>em apuração</span></div><div><b>${fi(zero)}</b><span>sem seção</span></div>`;
  } else {
    const sf = m.sw.filter(x => x !== -9999 && x > 0).length, sl = m.sw.filter(x => x !== -9999 && x < 0).length;
    leg = `<div class="m-grad" style="background:linear-gradient(90deg,${[...DIV_L].reverse().join(",")},${DIV_F.join(",")})"></div>
      <div class="m-grad-txt"><span style="color:var(--lula-claro)">Lula +12 p.p.</span><span>igual</span><span style="color:var(--flavio-claro)">Flávio +12 p.p.</span></div>`;
    cont = `<div><b style="color:${COR.Fc}">${fi(sf)}</b><span>onde Flávio cresceu</span></div><div><b style="color:${COR.Lc}">${fi(sl)}</b><span>onde Lula cresceu</span></div>`;
  }
  $("#m-mapa-leg").innerHTML = leg;
  $("#m-mapa-cont").innerHTML = cont;
  const li = (x, k) => `<li><span>${esc(x.nome)} (${x.uf.toUpperCase()})</span><b style="color:${COR[k + "c"]}">${sinal(x.saldo, fi)}</b></li>`;
  $("#m-top-F").innerHTML = (d.rec.top_f || []).slice(0, 5).map(x => li(x, "F")).join("") || "<li><span>Sem dados ainda</span></li>";
  $("#m-top-L").innerHTML = (d.rec.top_l || []).slice(0, 5).map(x => li(x, "L")).join("") || "<li><span>Sem dados ainda</span></li>";
}

// listas que só mudam de conteúdo: cria as linhas uma vez (para o movimento de entrada) e depois atualiza
function linhas(box, n, molde) {
  if (box.children.length !== n) {
    box.innerHTML = Array.from({ length: n }, molde).join("");
    prepararMovimento(box);
  }
  return [...box.children];
}

function regioesFeed(d) {
  const rs = d.rec.regioes || [];
  const lim = Math.max(1, ...rs.flatMap(r => [Math.abs(r.f - r.l), Math.abs(r.fp - r.lp)])) * 1.08;
  linhas($("#m-regioes"), rs.length, () => `<div class="m-reg r"><span class="nm"></span><div class="m-div"><i></i><u></u></div><span class="vl"></span></div>`)
    .forEach((el, k) => {
      const r = rs[k], sd = r.f - r.l, sp = r.fp - r.lp, w = 50 * Math.abs(sd) / lim;
      $(".nm", el).innerHTML = `${esc(r.nome)}<small>${fp(r.ap, 0)}% apurado</small>`;
      const i = $("i", el); i.style.background = sd >= 0 ? COR.F : COR.L; i.style.left = sd >= 0 ? "50%" : (50 - w) + "%"; i.style.width = w + "%";
      const u = $("u", el); u.style.left = `calc(${50 + 50 * sp / lim}% - 1px)`; u.style.display = r.fp + r.lp > 0 ? "" : "none";
      const v = $(".vl", el); v.textContent = sinal(sd); v.style.color = sd > 0 ? COR.Fc : sd < 0 ? COR.Lc : "#A6A48F";
    });
}

function estadosFeed(d) {
  const ufs = [...(d.rec.ufs || [])].sort((a, b) => ((b.fp - b.lp) || (b.f - b.l)) - ((a.fp - a.lp) || (a.f - a.l)));
  linhas($("#m-ufs"), ufs.length, () => `<div class="m-uf r"><span class="sg"></span><span class="nm"></span><span class="sd"></span>
      <div class="ln2"><div class="ap"><i></i></div><span class="pcs"></span></div></div>`)
    .forEach((el, k) => {
      const u = ufs[k], v = u.f + u.l, pf = v ? 100 * u.f / v : null, sp = u.fp - u.lp;
      $(".sg", el).textContent = u.uf === "zz" ? "EXT" : u.uf.toUpperCase();
      $(".nm", el).textContent = u.nome;
      const sd = $(".sd", el); sd.textContent = sp ? sinal(sp) : "—"; sd.style.color = sp >= 0 ? COR.Fc : COR.Lc;
      $(".ap i", el).style.width = u.ap + "%";
      $(".pcs", el).innerHTML = pf == null ? `${fp(u.ap, 0)}% apurado`
        : `<span style="color:${COR.Fc}">${fp(pf, 1)}%</span> · <span style="color:${COR.Lc}">${fp(100 - pf, 1)}%</span> · ${fp(u.ap, 0)}%`;
    });
}

function capitaisFeed(d) {
  $("#m-caps").innerHTML = (d.rec.capitais || []).map(x => {
    const v = x.f + x.l, pf = v ? 100 * x.f / v : null;
    const val = pf == null ? `<b style="color:#A6A48F">—</b>` : pf >= 50 ? `<b style="color:${COR.Fc}">Flávio ${fp(pf, 1)}%</b>` : `<b style="color:${COR.Lc}">Lula ${fp(100 - pf, 1)}%</b>`;
    return `<li><span>${esc(x.nome)} <small>${x.uf.toUpperCase()} · ${fp(x.pst, 0)}%</small></span>${val}</li>`;
  }).join("");
}

function fluxosFeed(d) {
  const p = d.proj, g = d.grupos || {}, box = $("#m-fluxos");
  if (!p || !p.trans) { box.innerHTML = `<p class="m-nota">${esc(p ? p.motivo : "Aguardando dados.")}</p>`; return; }
  linhas(box, 5, (_, r) => `<div class="m-fluxo r"><div class="nm"><span>${GRUPOS[r][0]}</span><small>${curto(g[GRUPOS[r][1]] || 0)} no 1º turno</small></div>
      <div class="m-pilha">${CORES_DEST.map((cor, j) => `<i style="background:${cor};color:${j === 2 ? "#0E100F" : "#FFFCE1"};flex:0 0 25%"></i>`).join("")}</div></div>`)
    .forEach((el, r) => $$("i", el).forEach((x, j) => {
      x.style.flexBasis = p.trans[r][j] + "%"; x.textContent = p.trans[r][j] >= 9 ? fp(p.trans[r][j], 0) + "%" : "";
    }));
}

window.addEventListener("resize", () => { if (modoTela === "mobile" && D) { pintarMapaFeed(D); desenharCurva(D, $("#m-curva")); } });

// ao abrir: ?modo=pc / ?modo=celular (ou ?rotacao=, para TV) pula a escolha
(function iniciar() {
  const m = (paramDoEndereco("modo") || "").toLowerCase();
  if (["pc", "computador", "tv"].includes(m) || paramDoEndereco("rotacao")) { modoTela = "pc"; return; }
  if (["mobile", "celular", "m"].includes(m)) { escolherModo("mobile"); return; }
  montarEscolha();
})();
