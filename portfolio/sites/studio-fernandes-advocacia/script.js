// Troque pelo seu número (só dígitos, com DDI+DDD) e e-mail reais antes de publicar.
const WHATSAPP_NUMERO = "SEUNUMEROAQUI";
const WHATSAPP_MENSAGEM = "Olá! Vi o site do Studio Fernandes e gostaria de agendar uma consulta.";
const EMAIL_CONTATO = "seuemail@exemplo.com";

const linkWhatsapp = `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(WHATSAPP_MENSAGEM)}`;

document.querySelectorAll('[data-whatsapp-link]').forEach((el) => {
  el.href = linkWhatsapp;
  el.target = "_blank";
  el.rel = "noopener";
});

document.querySelectorAll('[data-email-link]').forEach((el) => {
  el.href = `mailto:${EMAIL_CONTATO}`;
  el.textContent = EMAIL_CONTATO;
});

const burger = document.getElementById('burger');
const nav = document.getElementById('nav');
if (burger && nav) {
  burger.addEventListener('click', () => {
    const aberto = nav.classList.toggle('header__nav--aberto');
    burger.setAttribute('aria-expanded', String(aberto));
  });
}
