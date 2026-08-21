/*
 * Dados da seção de portfólio (#portfolio).
 *
 * Edite só este arquivo quando tiver novos projetos prontos — o layout em
 * js/script.js lê essa lista, monta os cards e as abas de filtro sozinho,
 * sem precisar mexer em HTML ou CSS.
 *
 * Campos de cada projeto:
 *   nome_cliente     — nome do negócio (site) ou do modelo de sistema
 *   categoria        — chave usada pelo filtro; precisa existir em CATEGORIAS
 *   segmento         — categoria curta (badge sobre a capa do card)
 *   tipo             — classificação da entrega (ex.: "Sistema Web / Gestão")
 *   tags             — tecnologias usadas (lista de strings, vira chip no card)
 *   link             — URL publicada. Deixe null quando não houver demo online:
 *                      o card cai automaticamente no CTA de WhatsApp.
 *   cta              — texto do botão. Opcional; tem padrão por categoria.
 *   imagem_capa      — screenshot 1200x900px (.jpg/.png) ou mockup .svg
 *   descricao_curta  — 1-2 frases sobre o problema que o projeto resolve
 */

/*
 * Abas do filtro, na ordem em que aparecem. A aba "Todos" é adicionada
 * automaticamente pelo js/script.js — não precisa entrar aqui.
 */
const CATEGORIAS = [
  { chave: "sites", rotulo: "Sites & Landing Pages" },
  { chave: "sistemas", rotulo: "Sistemas & Painéis" },
  { chave: "automacoes", rotulo: "Automações & IA" },
];

const PROJETOS = [
  {
    nome_cliente: "Studio Fernandes Advocacia",
    categoria: "sites",
    segmento: "Advocacia",
    tipo: "Site institucional",
    tags: ["HTML", "CSS", "JavaScript", "SEO"],
    link: "https://studio-fernandes-advocacia.vercel.app/",
    imagem_capa: "assets/case-studio-fernandes-advocacia.jpg",
    descricao_curta:
      "Site institucional para escritório de advocacia trabalhista e empresarial em Curitiba, com áreas de atuação, depoimentos e agendamento de consulta.",
  },
  {
    nome_cliente: "Doce Ponto Confeitaria",
    categoria: "sites",
    segmento: "Confeitaria",
    tipo: "Catálogo / Landing page",
    tags: ["HTML", "CSS", "JavaScript", "WhatsApp"],
    link: "https://doce-ponto-confeitaria.vercel.app/",
    imagem_capa: "assets/case-doce-ponto-confeitaria.jpg",
    descricao_curta:
      "Catálogo de bolos, tortas e doces artesanais com pedido direto pelo WhatsApp — sem depender de programador para atualizar o cardápio.",
  },
  {
    nome_cliente: "Barbearia Malandro",
    categoria: "sites",
    segmento: "Barbearia",
    tipo: "Landing page de conversão",
    tags: ["HTML", "CSS", "JavaScript", "Mobile-first"],
    link: "https://barbearia-malandro.vercel.app/",
    imagem_capa: "assets/case-barbearia-malandro.jpg",
    descricao_curta:
      "Site direto ao ponto para barbearia: serviços, horário e agendamento pelo WhatsApp em um clique, sem formulário complicado.",
  },
  {
    nome_cliente: "Painel Administrativo & Gestão de OS",
    categoria: "sistemas",
    segmento: "Gestão",
    tipo: "Sistema Web / Gestão",
    tags: ["React", "TypeScript", "Node.js", "PostgreSQL"],
    link: null,
    imagem_capa: "assets/mock-painel-os.svg",
    descricao_curta:
      "Acaba com a planilha compartilhada: ordens de serviço com status, histórico por cliente, níveis de acesso por equipe e relatórios prontos para o fechamento do mês.",
  },
  {
    nome_cliente: "CRM & Pipeline de Vendas Kanban",
    categoria: "sistemas",
    segmento: "Vendas",
    tipo: "Sistema Web / Vendas",
    tags: ["Next.js", "Tailwind CSS", "REST APIs"],
    link: null,
    imagem_capa: "assets/mock-crm-kanban.svg",
    descricao_curta:
      "Nenhum lead esquecido no meio do funil: cartões arrastáveis por etapa, histórico de cada interação e métricas de conversão por origem e por vendedor.",
  },
  {
    nome_cliente: "Dashboard Financeiro & Indicadores",
    categoria: "sistemas",
    segmento: "Métricas",
    tipo: "Dashboard / Métricas",
    tags: ["React", "Recharts", "API de Pagamentos"],
    link: null,
    imagem_capa: "assets/mock-dashboard-financeiro.svg",
    descricao_curta:
      "Faturamento, fluxo de caixa e inadimplência em tempo real numa tela só, com alertas operacionais avisando antes de o problema virar prejuízo.",
  },
  {
    nome_cliente: "Hub de Atendimento & Assistente de IA",
    categoria: "automacoes",
    segmento: "IA",
    tipo: "Automação / IA",
    tags: ["Python", "OpenAI/Claude API", "Webhooks"],
    link: null,
    imagem_capa: "assets/mock-hub-atendimento-ia.svg",
    descricao_curta:
      "Todas as conversas de WhatsApp da empresa em um só painel, com uma IA treinada na sua base respondendo o repetitivo e passando para um humano o que importa.",
  },
];
