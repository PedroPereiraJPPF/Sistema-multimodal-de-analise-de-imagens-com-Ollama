# 🔎 Analisador de Imagens

> 🧪 **Projeto pessoal de estudo.** Este repositório é um laboratório para **testar LLMs rodando localmente** e praticar **engenharia de prompt** de forma mensurável. Não é um produto: o objetivo é experimentar modelos pequenos, mudar prompts e **medir** o efeito de cada mudança.

Sistema **multimodal** que analisa fotos e documentos com um modelo de visão rodando **localmente** no [Ollama](https://ollama.com), retorna **JSON validado** com campos definidos pelo sistema e mede a **qualidade** dos modelos a partir da **revisão humana**.

Feito para rodar em hardware doméstico: desenvolvido e testado em uma **RTX 3050 com 6 GB de VRAM**.

## Por que este projeto existe

Quis responder, na prática, a algumas perguntas:

- **Até onde vai um modelo de visão de 4B rodando em casa?** Sem API paga, sem nuvem — só Ollama e uma GPU de entrada.
- **Quanto um prompt bem escrito muda o resultado?** Cada versão do prompt é registrada, comparada num benchmark com gabarito e documentada em [`PROMPT_CHANGELOG.md`](PROMPT_CHANGELOG.md).
- **Como avaliar um LLM de forma objetiva?** Precisão por campo, item a item, a partir de gabaritos e de revisão humana, em vez de "parece bom".

## Resultados

Benchmark de **extração de cardápios** (foto → catálogo com pratos, descrições, preços e seções), com gabarito, tudo rodando localmente.

**Dataset sintético** (12 imagens), `qwen3.5:4b`:

| Prompt | Precisão geral | `items.description` | `items.price` | JSON válido | Inferência média |
|---|---|---|---|---|---|
| v1 | 88% | 36% | 100% | 100% | 10,2 s |
| **v2** | **100%** | **100%** | 100% | 100% | 12,6 s |

A avaliação apontou o problema (o modelo **nunca** preenchia a descrição), a análise dos erros sugeriu a causa (os campos dos itens não estavam explicados no prompt) e o benchmark confirmou a correção.

**Cardápios reais** (6 imagens de terceiros: fotos de celular, fontes decorativas, duas colunas, pratos sem nome, vários preços por item). No sintético, a v2 já estava em 100% e não diferenciava mais versões de prompt; nos reais, ela cai para cerca de 70%:

| Modelo | v2 (3 imagens) | v3 (3 imagens) | v3 (6 imagens)¹ |
|---|---|---|---|
| `qwen3.5:4b` | 75% | **88%** | **87%** |
| `gemma3:4b` | 73% | 79% | 79% |
| `qwen2.5vl:3b` | 66% | 74% | 78% |

¹ Com gabarito de transcrição literal e a normalização de `"null"` na validação.

A **v4 foi testada e descartada**: das três regras novas, uma ajudou, uma foi ignorada e uma piorou um dos modelos. A história completa de cada versão, inclusive a que não deu certo, está em [`PROMPT_CHANGELOG.md`](PROMPT_CHANGELOG.md).

> ⚠️ Com 6 imagens, um único campo errado move a média em cerca de 3 pontos. O dataset real ainda é pequeno para separar diferenças dessa ordem.

```
foto ──► normalização ──► prompt + JSON Schema ──► Ollama (visão) ──► validação ──► PostgreSQL
                                                                                       │
                                     métricas ◄── revisão humana ◄── interface web ◄───┘
```

## Funcionalidades

| | |
|---|---|
| **Análise configurável** | Tipos prontos (descrição geral, **cardápio**, nota fiscal, conta de consumo, rótulo de produto, inventário), **pergunta livre** sobre a imagem ou **campos personalizados** definidos na hora. |
| **Saída estruturada** | O modelo é obrigado a seguir um JSON Schema (decodificação restrita do Ollama) e a resposta ainda é validada com Pydantic. |
| **Comparação de modelos** | Marque vários modelos e a mesma imagem é analisada por todos, lado a lado, com tempo de resposta e tokens. |
| **Revisão humana** | Corrija o resultado; o sistema destaca os campos alterados e calcula a precisão por campo. |
| **Avaliação** | Painel por modelo, tipo de análise e **versão do prompt**: taxa de JSON válido, tempo médio, tempo de carga na VRAM e precisão medida. |
| **Benchmark com gabarito** | Script que roda modelos sobre um dataset rotulado e mede a precisão **por campo e item a item**, com histórico entre versões do prompt. |
| **Histórico e relatórios** | Busca textual nos resultados, filtros por tipo e modelo, exportação CSV (abre direto no Excel). |
| **API JSON** | Os mesmos recursos via HTTP, para automações e scripts. |

## Visão técnica

### O que foi construído

1. **Pipeline de extração multimodal.** A imagem é normalizada (Pillow: correção de orientação EXIF, redimensionamento para no máximo 1024 px, conversão para JPEG) e enviada em base64 ao endpoint `/api/chat` do Ollama, junto com o system prompt, o prompt da tarefa e o JSON Schema do resultado esperado.
2. **Schemas como fonte única da verdade.** Cada tipo de análise é um modelo Pydantic. Dele saem a lista de campos descrita no prompt, o JSON Schema usado na decodificação restrita e a validação da resposta. Campos personalizados geram um modelo Pydantic dinâmico (`create_model`) em tempo de execução.
3. **Validação em duas camadas.** O Ollama restringe a geração ao schema; depois, a resposta passa por uma normalização (o texto `"null"` vira `null`) e pela validação Pydantic. Resposta fora do schema é gravada como inválida e entra na métrica, em vez de ser descartada.
4. **Persistência e revisão humana.** Cada análise grava modelo, versão do prompt, resposta bruta, resultado validado, tempo de inferência, tempo de carga na VRAM e tokens. A tela de revisão compara a correção humana com a resposta e calcula a precisão por campo.
5. **Benchmark offline com gabarito.** Um runner reutiliza exatamente a mesma função de extração do app, roda N modelos sobre um dataset rotulado, gera relatórios por campo e por imagem e acrescenta uma linha ao histórico de versões.
6. **Geração de dados sintéticos.** Cardápios desenhados com Pillow a partir de dados aleatórios com semente fixa, com variação de layout, fonte, formato de preço, rotação e desfoque. O gabarito é conhecido por construção.
7. **Ciclo de engenharia de prompt.** Toda mudança de prompt incrementa `PROMPT_VERSION`, é medida nos dois datasets (sintético e real) e só é aceita se melhorar. Versões descartadas também ficam registradas.

### Conceitos aplicados

| Conceito | Onde aparece |
|---|---|
| **Modelos de visão e linguagem (VLM)** | Um único modelo lê a imagem e gera texto estruturado, sem OCR separado |
| **Quantização (Q4_K_M)** | Modelos de 3B a 4B parâmetros com pesos em 4 bits, cerca de 3 GB de VRAM |
| **Decodificação restrita / saída estruturada** | O JSON Schema passado no `format` do Ollama limita os tokens que o modelo pode gerar |
| **Engenharia de prompt** | Papel e regras numeradas, tarefa específica por tipo, campos descritos, permissão explícita para `null`, transcrever em vez de converter |
| **Mitigação de prompt injection** | Texto do usuário isolado em tags (`<question>`, `<context>`) e declarado como informação, não como instrução |
| **Inferência determinística** | `temperature: 0`, para que a diferença entre duas execuções venha do prompt ou do modelo, não do sorteio |
| **Gestão de memória da GPU** | `num_ctx` pequeno (KV cache menor), `keep_alive`, uma inferência por vez com `asyncio.Lock`, `think: false` |
| **Avaliação com gabarito** | Precisão por campo, com normalização de diferenças cosméticas (maiúsculas, espaços, `10` vs `10.0`) |
| **Pareamento aproximado de listas** | Itens previstos e esperados pareados por similaridade de texto (`difflib.SequenceMatcher`, limiar 0,8), independente da ordem |
| **F1 de detecção** | Para listas: o modelo encontrou os itens certos sem inventar extras? |
| **Human-in-the-loop** | Correções na tela de revisão viram métrica de produção e podem ser exportadas como novo dataset rotulado |
| **Versionamento de prompt e ablação** | Cada versão medida contra a anterior; mudanças que não ajudam são descartadas, mesmo quando parecem boas |
| **Dados sintéticos** | Gabarito gratuito e reprodutível para começar a medir antes de ter dados reais |

### IAs utilizadas

Todos os modelos rodam **localmente** pelo [Ollama](https://ollama.com), sem API paga nem envio de imagens para a nuvem:

| Modelo | Família | Parâmetros | Papel no projeto |
|---|---|---|---|
| `qwen3.5:4b` | Qwen 3.5 (Alibaba) | 4B | Modelo padrão; o melhor nos benchmarks |
| `gemma3:4b` | Gemma 3 (Google) | 4B | Comparação |
| `qwen2.5vl:3b` | Qwen 2.5-VL (Alibaba) | 3B | Comparação; o mais rápido e o mais fiel na transcrição literal |

O desenvolvimento do código, dos experimentos e da documentação foi feito com apoio do [Claude Code](https://claude.com/claude-code) (Anthropic) como assistente de programação.

### Bibliotecas e ferramentas

| Camada | Tecnologia | Uso |
|---|---|---|
| Linguagem | Python 3.12 | |
| API e web | [FastAPI](https://fastapi.tiangolo.com) + Uvicorn | Rotas da interface web e da API JSON, documentação OpenAPI automática |
| Validação | [Pydantic](https://docs.pydantic.dev) + pydantic-settings | Schemas das análises, validação das respostas, configuração por variáveis de ambiente |
| Cliente HTTP | [httpx](https://www.python-httpx.org) (assíncrono) | Chamadas ao Ollama |
| Imagens | [Pillow](https://python-pillow.org) | Normalização das fotos e geração dos cardápios sintéticos |
| Banco de dados | [SQLAlchemy](https://www.sqlalchemy.org) 2 + psycopg 3 | PostgreSQL 16 no Docker; SQLite quando roda sem Docker |
| Interface | Jinja2 + [Pico CSS](https://picocss.com) | Páginas renderizadas no servidor, sem build de frontend |
| Upload | python-multipart | Formulários com imagem |
| Inferência | [Ollama](https://ollama.com) | Servidor de modelos local, rodando no host com acesso à GPU |
| Infraestrutura | Docker Compose | App + PostgreSQL; o container acessa o Ollama do host por `host.docker.internal` |
| Testes | Pytest + `TestClient` do FastAPI | Chamada ao modelo substituída por resposta fixa, testes sem GPU |
| Biblioteca padrão | `difflib`, `statistics`, `asyncio` | Pareamento de itens, métricas, fila de inferência |

## Como rodar

**Pré-requisitos:** Docker e Ollama instalados.

```bash
# 1. Baixe um modelo com suporte a visão
ollama pull qwen3.5:4b

# 2. Suba a aplicação e o banco
docker compose up -d --build

# 3. Abra no navegador
http://localhost:8000
```

O container acessa o Ollama do host por `host.docker.internal`. Confira com:

```bash
curl http://localhost:8000/health
# {"status":"ok","vision_models":["qwen3.5:4b"]}
```

<details>
<summary>Rodar sem Docker (usa SQLite)</summary>

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```
</details>

## Como usar

1. **Nova análise** — envie a imagem, escolha o tipo de extração e os modelos.
2. **Resultado** — a imagem fica ao lado das respostas de cada modelo, com tempo e tokens.
3. **Revisar / corrigir** — edite o JSON e salve. Os campos que você corrigiu ficam destacados e a precisão é calculada.
4. **Avaliação** — veja qual modelo acerta mais, qual é mais rápido e onde cada um erra.

### Pergunta livre

Escolha **Pergunta livre** e pergunte o que quiser sobre a imagem — por exemplo, *"Quais blocos aparecem na imagem? Diga o nome de cada um."* A resposta vem em dois campos: `answer` (texto) e `items` (lista, quando a pergunta pede para listar coisas).

### Campos personalizados

Quando você quer sempre os mesmos dados estruturados, escolha **Campos personalizados** e descreva um campo por linha (nomes curtos):

```
placa: placa do veículo
cor: cor predominante do veículo
modelo: marca e modelo do carro
```

### API

```bash
# Analisar (preset: general | menu | receipt | bill | product_label | inventory | question | custom)
curl -F "image=@cupom.jpg" -F "preset=receipt" http://localhost:8000/api/analyze

# Comparar dois modelos
curl -F "image=@foto.jpg" -F "models=qwen3.5:4b" -F "models=gemma3:4b" http://localhost:8000/api/analyze

# Pergunta livre
curl -F "image=@foto.jpg" -F "preset=question" -F "fields=Quantas pessoas aparecem?" \
     http://localhost:8000/api/analyze

# Campos personalizados
curl -F "image=@carro.jpg" -F "preset=custom" -F $'fields=placa: placa do veículo\ncor: cor' \
     http://localhost:8000/api/analyze

# Consultar o histórico
curl "http://localhost:8000/api/analyses?q=mercado&preset=receipt"
```

A documentação interativa (OpenAPI) fica em `http://localhost:8000/docs`.

## Engenharia de prompt

Este é o coração do projeto: o app e o benchmark existem para que cada ideia de prompt possa ser **testada e medida**, não só intuída.

O prompt foi pensado para **modelos pequenos e quantizados**, que seguem bem instruções curtas e objetivas e erram quando precisam "raciocinar" sobre formato. Ver [`app/prompts.py`](app/prompts.py).

- **Papel e regras numeradas no system prompt** — curto, sem ambiguidade, igual para todas as análises.
- **Uma tarefa específica por tipo** — "extraia os dados desta conta de consumo" em vez de "analise a imagem".
- **Lista explícita de campos com descrição e formato**, gerada a partir do mesmo modelo Pydantic que valida a resposta (uma única fonte da verdade).
- **Permissão explícita para `null`** — todos os campos são opcionais; dizer ao modelo que "não sei" é aceitável é a forma mais eficaz de reduzir valores inventados.
- **Entrada do usuário isolada em tags (`<question>`, `<context>`)** e declarado como informação, não como novas regras (mitiga *prompt injection* acidental).
- **Saída restrita por JSON Schema** (`format` do Ollama) + **validação Pydantic** — se ainda assim a resposta não bater com o schema, ela é registrada como inválida e entra na métrica.
- **`temperature: 0`** — extrações determinísticas e reproduzíveis, essencial para comparar modelos.
- **Campos de itens de listas também descritos** — cada prato, item de nota ou objeto tem seus campos explicados no prompt (foi o que levou o benchmark de 88% a 100%).
- **Transcrever em vez de converter** — veja o caso abaixo.
- **Prompt versionado** — `PROMPT_VERSION` é gravado em cada análise e em cada execução do benchmark; toda mudança é medida antes de ser aceita e registrada em [`PROMPT_CHANGELOG.md`](PROMPT_CHANGELOG.md).

### Um caso real que a avaliação revelou

Num cupom com `Data: 03/11/2026`, o modelo devolvia `2026-03-11` (leu no formato americano). Acrescentar no prompt "as datas no Brasil são DD/MM/AAAA, converta para AAAA-MM-DD" **não resolveu**: o modelo de 4B transcreve bem, mas erra ao converter. A solução foi pedir a data **exatamente como impressa** — acertou em todas as execuções. Valores monetários, ao contrário, ele converte bem (`R$ 93,52` → `93.52`).

## Otimização para 6 GB de VRAM

| Decisão | Por quê |
|---|---|
| Modelo de 4B quantizado em Q4_K_M | ~3,1 GB na VRAM, roda **100% na GPU** com folga |
| Imagem redimensionada para no máximo 1024 px e convertida para JPEG | Fotos de celular têm 4000 px+ e vários MB; o encoder de visão reduz de qualquer jeito. Menos dados, menos tokens de imagem |
| `num_ctx: 4096` | Contexto pequeno = KV cache pequeno. Imagem + prompt + resposta cabem com folga |
| `think: false` | Desliga os tokens de raciocínio do Qwen 3.5: mais rápido e sem ganho para extração |
| Uma inferência por vez (`asyncio.Lock`) | Evita dois modelos disputando a VRAM, o que jogaria camadas para a CPU |
| `keep_alive: 5m` | O modelo fica carregado entre análises seguidas e libera a VRAM depois |

Medido na RTX 3050 6 GB (cupom fiscal sintético, `qwen3.5:4b`):

| Situação | Tempo |
|---|---|
| Primeira análise (carregando o modelo na VRAM) | ~80 s, dos quais ~39 s de carga |
| Análises seguintes (modelo já carregado) | **~10 s** |

Todos os parâmetros são configuráveis por variável de ambiente (veja [`.env.example`](.env.example) e [`app/config.py`](app/config.py)).

## Avaliação de qualidade

Há duas formas de medir, com **a mesma métrica** ([`app/evaluation.py`](app/evaluation.py)):

| | Referência | Para quê |
|---|---|---|
| Página **Avaliação** (no app) | Suas correções na tela de revisão | Acompanhar a qualidade no uso do dia a dia |
| **Benchmark** (`benchmark/`) | Dataset com gabarito | Comparar modelos e versões de prompt de forma reproduzível |

### Como a precisão é calculada

- **Campos simples:** acerto ou erro, ignorando diferenças cosméticas (maiúsculas, espaços, `10` vs `10.0`).
- **Listas** (pratos, itens da nota): os itens previstos são **pareados** com os do gabarito pelo nome, com tolerância a pequenos erros de leitura e independente da ordem. Então:
  - `items` recebe o **F1** do pareamento: encontrou os itens certos, sem inventar extras?
  - `items.price`, `items.description`, … recebem a **precisão de cada subcampo** nos itens pareados.
- **Precisão geral** = média de todas essas notas. Resposta fora do schema = 0 em tudo.

Isso mostra **onde** o modelo erra ("acerta 100% dos preços, mas só 36% das descrições"), não apenas quanto.

### Benchmark com gabarito

Um dataset é uma pasta com cada imagem e um `.json` de mesmo nome com a resposta esperada:

```
benchmark/datasets/menus-synthetic/menu_01.png
benchmark/datasets/menus-synthetic/menu_01.json
```

```bash
# Rodar (um ou mais modelos)
docker compose run --rm app python -m benchmark.run benchmark/datasets/menus-synthetic --preset menu
docker compose run --rm app python -m benchmark.run benchmark/datasets/menus-synthetic --preset menu \
    --models qwen3.5:4b gemma3:4b

# Gerar cardápios sintéticos (gabarito conhecido por construção, semente fixa)
docker compose run --rm --no-deps app python -m benchmark.synthetic_menus --count 12

# Transformar análises revisadas no app em gabarito (fotos reais → dataset)
docker compose run --rm app python -m benchmark.export_reviewed --preset menu \
    --out benchmark/datasets/menus-real
```

Cada execução grava em `benchmark/results/` um relatório Markdown (resumo, precisão por campo, precisão por imagem), o JSON bruto com todas as respostas e uma linha por modelo em [`history.md`](benchmark/results/history.md), que é o histórico de evolução entre versões do prompt. Só o `history.md` é versionado; os relatórios ficam locais.

O dataset `menus-real` usa imagens de cardápios de terceiros: apenas os gabaritos `.json` estão no repositório. Os gabaritos seguem **transcrição literal**, inclusive erros impressos na imagem, porque é isso que o prompt pede ao modelo.

**Ciclo de melhoria:** fotografe → analise → revise no app → `export_reviewed` → mude o prompt e incremente `PROMPT_VERSION` → `benchmark.run` → compare no `history.md` → registre no `PROMPT_CHANGELOG.md`.

## Testes

```bash
docker compose run --rm --no-deps app pytest
```

Os testes não dependem do Ollama: a chamada ao modelo é substituída por uma resposta fixa. Cobrem normalização de imagem, construção do prompt, campos personalizados, validação de schema, comparação de modelos, revisão, pontuação item a item, benchmark e busca.

## Estrutura

```
app/
├── main.py         # rotas: interface web + API JSON
├── service.py      # casos de uso: analisar, revisar, buscar
├── presets.py      # tipos de análise e seus schemas (Pydantic)
├── prompts.py      # system prompt e construção do prompt
├── llm.py          # cliente HTTP do Ollama
├── images.py       # normalização das imagens
├── evaluation.py   # pontuação (campo a campo e item a item) e métricas
├── db.py           # modelo de dados (SQLAlchemy)
├── config.py       # configurações via variáveis de ambiente
├── templates/      # páginas Jinja2
└── static/         # CSS
benchmark/
├── run.py              # roda modelos sobre um dataset e gera relatórios
├── synthetic_menus.py  # gera cardápios com gabarito
├── export_reviewed.py  # revisões do app → dataset rotulado
├── datasets/           # imagens + gabaritos .json
└── results/            # relatórios e history.md
tests/                  # pytest
```

### Adicionando um novo tipo de análise

Crie um modelo Pydantic e registre um `Preset` em [`app/presets.py`](app/presets.py) — o schema, o prompt e a validação saem dele automaticamente:

```python
class WineLabel(BaseModel):
    name: str | None = Field(None, description="Wine name")
    vintage: str | None = Field(None, description="Vintage year")
    grape: str | None = Field(None, description="Grape variety")

Preset("wine", "Rótulo de vinho", "Extract the information from this wine label.", WineLabel)
```

## Modelos sugeridos (até 6 GB de VRAM)

| Modelo | Tamanho | Observação |
|---|---|---|
| `qwen3.5:4b` | ~3,4 GB | Padrão. Bom em OCR e documentos |
| `gemma3:4b` | ~3,3 GB | Boa alternativa para comparação |
| `qwen2.5vl:3b` | ~3,2 GB | Focado em visão e documentos |

Modelos de 7B+ com visão tendem a não caber inteiros na VRAM e ficam bem mais lentos.

## Limitações e próximos passos

- PDFs ainda não são aceitos diretamente — fotografe ou exporte a página como imagem.
- As análises rodam de forma síncrona; com muitos usuários simultâneos valeria uma fila de tarefas.
- Ampliar o dataset de cardápios reais: com 6 imagens, diferenças de até ~3 pontos ainda são ruído.
- Prato impresso sem nome (só descrição): todos os modelos usam a descrição como nome, mesmo com regra explícita. Próximo teste: exemplo no prompt (few-shot) ou `description` antes de `name` no schema.
- Vários preços por item (Broto/Média/Grande): o schema só tem um `price`.
- Migrações com Alembic se o modelo de dados crescer (hoje há uma migração mínima em `db.py`).
