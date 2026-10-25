/* Sinal de presença, anônimo: um código aleatório por navegador (sem nome, IP ou dados pessoais),
   se a aba está visível e o modo escolhido. Só é enviado quando algo muda; o "ping" de quem continua
   no site é a própria atualização do painel a cada 5 s, no servidor. */
"use strict";
(function () {
  let id;
  try {
    id = localStorage.getItem("apuracao26-id");
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36));
      localStorage.setItem("apuracao26-id", id);
    }
  } catch (e) { id = "s-" + Math.random().toString(36).slice(2); }   // navegação privada: conta por sessão
  let ultimo = "";
  function avisar() {
    const v = { id, visivel: document.visibilityState === "visible", modo: (typeof modoTela !== "undefined" && modoTela) || "" };
    const k = JSON.stringify(v);
    if (k === ultimo) return;
    ultimo = k;
    enviar("streamlit:setComponentValue", { value: v, dataType: "json" });
  }
  document.addEventListener("visibilitychange", avisar);
  setInterval(avisar, 10000);
  setTimeout(avisar, 1500);
})();
