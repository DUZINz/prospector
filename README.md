# Prospector

Encontra negócios da sua cidade/região que **não têm site próprio** — o lead ideal
para quem vende presença digital. Busca no Google Maps, filtra quem não tem site,
e traz nome, telefone, WhatsApp, endereço, nota e link social.

## Instalação

**1. Python** — não está instalado nesta máquina. Instale uma vez:

```powershell
winget install Python.Python.3.12
```

Feche e reabra o terminal depois (o PATH só atualiza em sessão nova). Confirme com
`python --version` — se aparecer a tela da Microsoft Store, desative os aliases em
*Configurações → Aplicativos → Configurações avançadas → Aliases de execução*.

**2. Projeto:**

```powershell
cd C:\Users\eduar\Documents\projetos\prospector
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

O último passo baixa ~150 MB (o navegador que o scraper controla). É obrigatório.

## Uso

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

Abre em `http://localhost:8501`. Na barra lateral: categorias (uma por linha),
cidades/bairros (uma por linha), e **Buscar**. Cada combinação categoria × cidade
vira uma busca.

Direto pelo terminal, sem interface:

```powershell
.\.venv\Scripts\python.exe -m prospector.scraper --termo dentista --regiao "Curitiba PR" --max 40
```

Flags: `--todos` (traz também quem tem site), `--visivel` (mostra o navegador —
use quando algo parar de funcionar).

## Como o filtro "sem site" funciona

Um negócio é considerado **sem site** quando o campo de site no Maps está vazio
**ou** aponta para um agregador. A lista está em `AGREGADORES`, em
`prospector/scraper.py` — Instagram, Facebook, Linktree, Doctoralia, iFood,
`business.site` (os sites que o próprio Google gera). Um dentista cujo único link
é o Instagram continua sendo lead, e o link fica salvo na coluna *Link social*.

Ajuste essa lista conforme o seu critério de venda.

## Sobre e-mail

**O Google Maps não tem e-mail de empresa.** Não é limitação do scraper: o campo
não existe na base do Google, nem na API oficial paga. As vias reais são:

1. **WhatsApp** — já vem pronto, é o canal que converte melhor no Brasil
2. **Bio do Instagram** — quando a coluna *Link social* está preenchida, o e-mail
   costuma estar lá
3. Enriquecimento por CNPJ (ReceitaWS, BrasilAPI) — o e-mail cadastrado na Receita,
   que às vezes é o do contador, não o da empresa

## Limites que você vai encontrar

- **~120 resultados por busca.** É um teto do próprio Maps, não do scraper. Para
  cobrir uma cidade grande, busque por bairro em vez de cidade inteira — o campo
  aceita várias linhas justamente para isso.
- **O scraper quebra quando o Google muda o HTML.** Acontece algumas vezes por ano.
  Todos os seletores estão em `prospector/selectors.py`, com instruções de conserto.
  Nenhum outro arquivo depende de HTML do Google.
- **Ritmo.** Há pausas irregulares entre as requisições. Não remova: rodar rápido
  demais leva a CAPTCHA e o navegador trava esperando resolução manual.
- **Termos de uso.** Scraping do Maps é contrário aos ToS do Google. Para
  prospecção própria o risco prático é bloqueio de IP, não ação legal — mas revenda
  da base é outro assunto.

## Estrutura

```
app.py                      interface Streamlit
prospector/
  scraper.py                Playwright + CLI (emite NDJSON)
  selectors.py              seletores do Maps — conserte aqui quando quebrar
  models.py                 Lead, telefone BR, chave de deduplicação
  storage.py                SQLite
leads.db                    criado no primeiro uso
```

Os leads acumulam entre buscas, deduplicados pelo identificador do local. O
`status` (novo/contatado/negociando/fechado/descartado) e as suas notas **nunca
são sobrescritos** quando você refaz uma busca.

## Trocar o scraping pela API oficial

Se o scraping começar a dar trabalho: a Places API (New) devolve `websiteUri` e
`nationalPhoneNumber` direto, com 10k chamadas grátis por mês. É só escrever um
`prospector/places_api.py` que exponha a mesma função `buscar()` de `scraper.py`
— ela devolve `Lead`, e nem o app nem o banco precisam mudar.
