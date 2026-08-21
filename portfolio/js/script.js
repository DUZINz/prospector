/*
 * Configuração de contato — edite só aqui, os links no HTML se atualizam sozinhos.
 */
const CONTATO = {
  // Número com DDI + DDD, só dígitos. Ex.: "5541999998888"
  whatsapp: "5541987886113",
  whatsappMensagem: "Olá! Vi seu portfólio e quero um site para o meu negócio.",
  email: "eduardogrunitzky@gmail.com",
};

function montarLinkWhatsapp(mensagem) {
  const texto = encodeURIComponent(mensagem || CONTATO.whatsappMensagem);
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

/* ------------------------------ portfólio ------------------------------ */

const FILTRO_TODOS = "todos";

/*
 * Projeto sem `link` não tem demo pública: o botão vira um convite de
 * orçamento no WhatsApp já com o nome do modelo na mensagem.
 */
function montarAcaoDoProjeto(p) {
  if (p.link) {
    return {
      href: p.link,
      rotulo: p.cta || "Ver projeto ao vivo",
      externo: true,
    };
  }
  return {
    href: montarLinkWhatsapp(
      `Olá! Vi o modelo "${p.nome_cliente}" no seu portfólio e quero um projeto parecido para o meu negócio.`
    ),
    rotulo: p.cta || "Solicitar projeto similar",
    externo: true,
  };
}

function montarCard(p) {
  const acao = montarAcaoDoProjeto(p);
  const tags = (p.tags || [])
    .map((t) => `<li class="card__tag">${t}</li>`)
    .join("");

  return `
    <article class="card" data-categoria="${p.categoria}" data-reveal>
      <div class="card__capa-wrap">
        <img class="card__capa" src="${p.imagem_capa}" alt="Prévia de ${p.nome_cliente}" loading="lazy" />
        <span class="card__segmento">${p.segmento}</span>
      </div>
      <div class="card__corpo">
        ${p.tipo ? `<p class="card__tipo">${p.tipo}</p>` : ""}
        <h3 class="card__nome">${p.nome_cliente}</h3>
        <p class="card__descricao">${p.descricao_curta}</p>
        ${tags ? `<ul class="card__tags">${tags}</ul>` : ""}
        <a class="btn btn--fantasma btn--small card__acao"
           href="${acao.href}"
           ${acao.externo ? 'target="_blank" rel="noopener"' : ""}>
          ${acao.rotulo} <span aria-hidden="true">→</span>
        </a>
      </div>
    </article>
  `;
}

/*
 * Monta as abas de filtro a partir de CATEGORIAS, escondendo as que não têm
 * nenhum projeto — assim a barra nunca mostra uma aba que abre vazia.
 */
function montarFiltros() {
  const barra = document.getElementById("portfolio-filtros");
  if (!barra || typeof CATEGORIAS === "undefined") return;

  const comProjetos = CATEGORIAS.filter((c) =>
    PROJETOS.some((p) => p.categoria === c.chave)
  );
  if (comProjetos.length < 2) return; // uma categoria só: filtro não ajuda em nada

  const abas = [{ chave: FILTRO_TODOS, rotulo: "Todos" }, ...comProjetos];

  barra.innerHTML = abas
    .map((c) => {
      const total =
        c.chave === FILTRO_TODOS
          ? PROJETOS.length
          : PROJETOS.filter((p) => p.categoria === c.chave).length;
      const ativo = c.chave === FILTRO_TODOS;
      return `
      <button type="button" class="filtro${ativo ? " is-ativo" : ""}"
              data-filtro="${c.chave}" role="tab" aria-selected="${ativo}">
        ${c.rotulo} <span class="filtro__contagem">${total}</span>
      </button>`;
    })
    .join("");

  barra.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-filtro]");
    if (botao) aplicarFiltro(botao.dataset.filtro);
  });
}

function aplicarFiltro(chave) {
  document.querySelectorAll("#portfolio-filtros .filtro").forEach((b) => {
    const ativo = b.dataset.filtro === chave;
    b.classList.toggle("is-ativo", ativo);
    b.setAttribute("aria-selected", String(ativo));
  });

  document.querySelectorAll("#portfolio-grid .card").forEach((card) => {
    const mostrar = chave === FILTRO_TODOS || card.dataset.categoria === chave;
    card.hidden = !mostrar;
    // Card que entra depois de já ter passado a dobra precisa aparecer na hora.
    if (mostrar) card.classList.add("is-visivel");
  });
}

function renderizarPortfolio() {
  const grid = document.getElementById("portfolio-grid");
  if (!grid || typeof PROJETOS === "undefined") return;

  grid.innerHTML = PROJETOS.map(montarCard).join("");
  montarFiltros();
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


/* ------------------------------ calculadora ------------------------------ */

const MOEDA = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

/*
 * Preço e prazo somam direto: base + cada módulo escolhido. Prazo em dias
 * úteis, sem paralelismo — é estimativa de proposta, não cronograma.
 */
function calcularOrcamento(base, extras) {
  return {
    total: extras.reduce((s, m) => s + m.preco, base.preco),
    dias: extras.reduce((s, m) => s + m.dias, base.dias),
  };
}

function montarBriefing(base, extras) {
  const { total, dias } = calcularOrcamento(base, extras);
  const linhas = [
    "Olá, Eduardo! Montei uma estimativa no seu site:",
    "",
    `Projeto: ${base.nome} — ${MOEDA.format(base.preco)}`,
  ];
  if (extras.length) {
    linhas.push("", "Módulos extras:");
    extras.forEach((m) => linhas.push(`• ${m.nome} — ${MOEDA.format(m.preco)}`));
  }
  linhas.push(
    "",
    `Total estimado: ${MOEDA.format(total)}`,
    `Prazo estimado: ${dias} dias úteis`,
    "",
    "Podemos conversar sobre esse escopo?"
  );
  return linhas.join("\n");
}

function montarOpcao(item, indice, tipo) {
  const multipla = tipo === "extra";
  return `
    <label class="opcao">
      <input type="${multipla ? "checkbox" : "radio"}" name="${tipo}"
             value="${indice}" ${!multipla && indice === 0 ? "checked" : ""} />
      <span class="opcao__nome">${item.nome}</span>
      <span class="opcao__preco">${multipla ? "+ " : ""}${MOEDA.format(item.preco)}</span>
      <span class="opcao__prazo">${multipla ? "+" : ""}${item.dias} dias</span>
    </label>`;
}

function lerSelecao(form) {
  const dados = new FormData(form);
  return {
    base: BASES_PROJETO[Number(dados.get("base"))] || BASES_PROJETO[0],
    extras: dados.getAll("extra").map((i) => MODULOS_EXTRAS[Number(i)]),
  };
}

function atualizarResumo(form) {
  const { base, extras } = lerSelecao(form);
  const { total, dias } = calcularOrcamento(base, extras);

  document.getElementById("calc-total").textContent = MOEDA.format(total);
  document.getElementById("calc-prazo").textContent = `Entrega em até ${dias} dias úteis`;
  document.getElementById("calc-itens").innerHTML = [base, ...extras]
    .map((i) => `<li>${i.nome}</li>`)
    .join("");
  document
    .getElementById("calc-cta")
    .setAttribute("href", montarLinkWhatsapp(montarBriefing(base, extras)));
}

function renderizarCalculadora() {
  const form = document.getElementById("calculadora");
  if (!form || typeof BASES_PROJETO === "undefined") return;

  document.getElementById("calc-bases").innerHTML = BASES_PROJETO.map((b, i) =>
    montarOpcao(b, i, "base")
  ).join("");
  document.getElementById("calc-extras").innerHTML = MODULOS_EXTRAS.map((m, i) =>
    montarOpcao(m, i, "extra")
  ).join("");

  form.addEventListener("change", () => atualizarResumo(form));
  form.addEventListener("submit", (e) => e.preventDefault());
  atualizarResumo(form);
}

document.addEventListener("DOMContentLoaded", () => {
  aplicarLinksDeContato();
  renderizarPortfolio();
  renderizarCalculadora();
  ativarRevealOnScroll();
  preencherAno();
});
