/*
 * Dados da seção de portfólio (#portfolio).
 *
 * Edite só este arquivo quando tiver novos projetos prontos — o layout em
 * js/script.js lê essa lista e monta os cards sozinho, sem precisar mexer
 * em HTML ou CSS.
 *
 * Campos de cada projeto:
 *   nome_cliente     — nome do negócio do cliente
 *   segmento         — categoria curta (aparece como tag no card)
 *   link             — URL do site publicado (use "#" enquanto não tiver)
 *   imagem_capa      — screenshot do site (recomendado: 1200x900px, .jpg/.png)
 *   descricao_curta  — 1-2 frases sobre o que foi feito
 */

const PROJETOS = [
  {
    nome_cliente: "Studio Fernandes Advocacia",
    segmento: "Advocacia",
    link: "https://studio-fernandes-advocacia.vercel.app/",
    imagem_capa: "assets/case-studio-fernandes-advocacia.jpg",
    descricao_curta:
      "Site institucional para escritório de advocacia trabalhista e empresarial em Curitiba, com áreas de atuação, depoimentos e agendamento de consulta.",
  },
  {
    nome_cliente: "Doce Ponto Confeitaria",
    segmento: "Confeitaria",
    link: "https://doce-ponto-confeitaria.vercel.app/",
    imagem_capa: "assets/case-doce-ponto-confeitaria.jpg",
    descricao_curta:
      "Catálogo de bolos, tortas e doces artesanais com pedido direto pelo WhatsApp — sem depender de programador para atualizar o cardápio.",
  },
  {
    nome_cliente: "Barbearia Malandro",
    segmento: "Barbearia",
    link: "https://barbearia-malandro.vercel.app/",
    imagem_capa: "assets/case-barbearia-malandro.jpg",
    descricao_curta:
      "Site direto ao ponto para barbearia: serviços, horário e agendamento pelo WhatsApp em um clique, sem formulário complicado.",
  },
];
