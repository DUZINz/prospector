"""
Ponto unico de manutencao dos seletores do Google Maps.

Quando o scraper parar de achar resultados, quase sempre a causa esta AQUI:
o Google trocou uma classe ofuscada (ex.: `hfpxzc`, `Nv2PK`, `F7nice`).
Abra o Maps, inspecione o elemento e atualize a constante correspondente.
Nada mais no projeto depende de HTML do Google.
"""

# Container da lista de resultados da busca.
FEED = 'div[role="feed"]'

# Link do card de cada estabelecimento dentro do feed.
CARD_LINK = "a.hfpxzc"

# Botao "Site" que aparece no proprio card da lista.
# Usado como triagem rapida; a confirmacao real e feita na pagina do local.
CARD_WEBSITE = (
    'a[data-value="Website"], '
    'a[aria-label^="Visitar site"], '
    'a[aria-label^="Visit site"], '
    'a[aria-label^="Ir para o site"]'
)

# Textos que indicam que o feed chegou ao fim (pt-BR e en).
END_OF_LIST = [
    "Você chegou ao fim da lista",
    "You've reached the end of the list",
]

# --- Pagina de detalhe do estabelecimento ---

DETAIL_TITLE = "h1"
DETAIL_WEBSITE = 'a[data-item-id="authority"]'
DETAIL_PHONE = 'button[data-item-id^="phone:tel:"]'
DETAIL_ADDRESS = 'button[data-item-id="address"]'
DETAIL_PLUSCODE = 'button[data-item-id^="oloc"]'
DETAIL_CATEGORY = "button.DkEaL"
DETAIL_RATING_BLOCK = "div.F7nice"

# Botoes de consentimento de cookies (aparecem em consent.google.com).
CONSENT_BUTTONS = [
    'button:has-text("Aceitar tudo")',
    'button:has-text("Accept all")',
    'form[action*="consent"] button',
]
