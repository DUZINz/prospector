/*
 * Configuração de contato — edite só aqui, os links no HTML se atualizam sozinhos.
 */
const CONTATO = {
  // Número com DDI + DDD, só dígitos. Ex.: "5541999998888"
  whatsapp: "55SEUNUMEROAQUI",
  whatsappMensagem: "Olá! Vi seu portfólio e quero um site para o meu negócio.",
  email: "seuemail@dominio.com",
};

function montarLinkWhatsapp() {
  const texto = encodeURIComponent(CONTATO.whatsappMensagem);
  return `https://wa.me/${CONTATO.whatsapp}?text=${texto}`;
}

function aplicarLinksDeContato() {
  const linkWhatsapp = montarLinkWhatsapp();
  document.querySelectorAll("[data-whatsapp-link]").forEach((el) => {
    el.setAttribute("href", linkWhatsapp);
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "noopener");
  });

  document.querySelectorAll("[data-email-link]").forEach((el) => {
    el.setAttribute("href", `mailto:${CONTATO.email}`);
    el.textContent = CONTATO.email;
  });
}

/*
 * Monta os cards de #portfolio a partir de PROJETOS (data/projetos.js).
 */
function renderizarPortfolio() {
  const grid = document.getElementById("portfolio-grid");
  if (!grid || typeof PROJETOS === "undefined") return;

  grid.innerHTML = PROJETOS.map(
    (p) => `
    <a class="card" href="${p.link}" target="_blank" rel="noopener" data-reveal>
      <div class="card__capa-wrap">
        <img class="card__capa" src="${p.imagem_capa}" alt="Capa do site de ${p.nome_cliente}" loading="lazy" />
        <span class="card__segmento">${p.segmento}</span>
      </div>
      <div class="card__corpo">
        <h3 class="card__nome">${p.nome_cliente}</h3>
        <p class="card__descricao">${p.descricao_curta}</p>
      </div>
    </a>
  `
  ).join("");
}

/*
 * Revela elementos marcados com [data-reveal] conforme entram na tela.
 */
function ativarRevealOnScroll() {
  const alvos = document.querySelectorAll("[data-reveal]");
  if (!alvos.length || !("IntersectionObserver" in window)) {
    alvos.forEach((el) => el.classList.add("is-visivel"));
    return;
  }

  const observer = new IntersectionObserver(
    (entradas) => {
      entradas.forEach((entrada) => {
        if (entrada.isIntersecting) {
          entrada.target.classList.add("is-visivel");
          observer.unobserve(entrada.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  alvos.forEach((el) => observer.observe(el));
}

function preencherAno() {
  const el = document.querySelector(".footer__ano");
  if (el) el.textContent = `© ${new Date().getFullYear()}`;
}

document.addEventListener("DOMContentLoaded", () => {
  aplicarLinksDeContato();
  renderizarPortfolio();
  ativarRevealOnScroll();
  preencherAno();
});
