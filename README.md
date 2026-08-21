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

## E-mail e MEI (enriquecimento pela Receita)

**O Google Maps não tem e-mail de empresa** — o campo não existe na base do
Google, nem na API oficial paga. Quem tem é a Receita Federal, cuja base de CNPJ
é pública. O módulo `prospector/cnpj.py` faz a ponte, em duas etapas:

```
nome + município  --(busca)-->  CNPJ  --(consulta)-->  e-mail, porte, MEI
```

Na barra lateral, **Enriquecer pela Receita → Buscar e-mail e CNPJ**. Ele consulta
só quem ainda não foi consultado, respeitando os filtros da tela, e grava cada lead
assim que responde — interromper no meio preserva o que já foi consultado, desde que
a aba continue aberta (veja *Onde os leads ficam*).

Antes do primeiro uso, confirme que os provedores respondem da sua rede:

```powershell
python -m prospector.cnpj --diagnostico
```

**A etapa frágil é achar o CNPJ pelo nome.** Nome fantasia do Maps quase nunca é
igual à razão social da Receita. Cada candidato recebe uma nota por sobreposição
de palavras próprias (as genéricas do ramo — "advocacia", "pet shop" — não contam,
senão dois negócios diferentes casariam entre si), e abaixo de
`LIMIAR_SIMILARIDADE` o campo fica em branco. **Preferimos não preencher a colar
o CNPJ de outra empresa no seu lead.**

Quando ele não achar, a coluna **CNPJ** da tabela é editável: cole o número, salve
e clique em enriquecer de novo — com o CNPJ em mãos o acerto é garantido.

Casos que a busca automática não resolve sozinha: MEI registrado no nome civil
("Barbearia do Zé" é `JOSÉ CARLOS SILVA`) e nomes feitos só de termos do ramo
("Escritório de Advocacia"). Não há sinal suficiente para casar com segurança.

Ritmo: o `publica.cnpj.ws` limita a 3 consultas/minuto, então lotes grandes
demoram. O `minhareceita.org` é tentado primeiro justamente por ser mais rápido.

Terceira via, ainda não implementada: **e-mail na bio do Instagram**, quando a
coluna *Link social* está preenchida.

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
  cnpj.py                   Receita: e-mail, porte, MEI (+ --diagnostico)
  models.py                 Lead, telefone BR, textos das mensagens
  storage.py                leads em memória (st.session_state)
  funil.py                  funil de contato em SQLite (persiste)
  funil.db                  criado no 1º uso — NÃO versionar
```

## Onde os leads ficam

São **dois níveis de dado**, de propósito:

**1. Resultado da busca — só na sessão.** `storage.py` é um dicionário em
`st.session_state`, indexado pela chave do local. Nome, telefone, endereço, nota:
tudo isso **some ao fechar a aba, dar F5 ou reiniciar o Streamlit**. É o
comportamento pretendido, não um bug — refazer a busca é barato.

Enquanto a aba fica aberta, os leads acumulam entre buscas, deduplicados pelo
identificador do local.

**2. Funil de contato — persistido em `prospector/funil.db`.** Quem você já
abordou, em que estágio está e quando foi a última mensagem **não pode sumir**,
senão você manda a mesma primeira mensagem duas vezes para o mesmo negócio. Esse
pedaço vive em SQLite (`funil.py`) e volta sozinho por cima da sessão quando você
reabre o app e refaz a busca — junto com `status` e as suas notas.

> ⚠️ `funil.db` guarda **nome e telefone reais** de quem foi abordado. Está no
> `.gitignore` e não deve ser versionado nem compartilhado.

Como o resultado da busca não persiste, **exportar continua sendo o jeito de não
perder a coleta**: botões **Excel** e **CSV** no rodapé da tabela.

## Follow-up de WhatsApp

A sequência tem 3 mensagens e termina — sem bot, sem automação de envio, para não
arriscar o número. O app decide **quem está pronto**; o envio continua sendo seu
clique dentro do WhatsApp.

```
estágio 0  nunca contatado       →  abordagem inicial
estágio 1  1ª mensagem enviada   →  espera DIAS_ATE_FOLLOWUP1 (4 dias)
estágio 2  1º follow-up enviado  →  espera DIAS_ATE_FOLLOWUP2 (6 dias)
estágio 3  2º follow-up enviado  →  encerrado, não insiste mais
```

Os prazos são constantes no topo de `prospector/funil.py`; os textos das três
mensagens ficam em `prospector/models.py` (`PITCH_GERAL`, `ABORDAGEM_FOLLOWUP1`,
`ABORDAGEM_FOLLOWUP2`).

Na tabela, a coluna **WhatsApp** só vira link quando há mensagem liberada — a
coluna **Situação** ao lado diz o porquê (`aguardando (3d)`, `sequência
concluída`). Depois de enviar, marque **"Enviei essa mensagem"** e clique em
*Salvar alterações*: isso avança o estágio, carimba a data e agenda o próximo.

O expander **📤 Fila de hoje** lista só quem está liberado agora, do mais atrasado
ao mais recente, com um botão que abre todas as conversas em abas. Essa fila
**ignora os filtros da tabela** de propósito: assim que um lead recebe a primeira
mensagem ele vira `contatado` e sairia do filtro padrão (`novo`) — a fila ficaria
vazia justamente no dia de mandar o follow-up.

## Trocar o scraping pela API oficial

Se o scraping começar a dar trabalho: a Places API (New) devolve `websiteUri` e
`nationalPhoneNumber` direto, com 10k chamadas grátis por mês. É só escrever um
`prospector/places_api.py` que exponha a mesma função `buscar()` de `scraper.py`
— ela devolve `Lead`, e nem o app nem o armazenamento precisam mudar.
