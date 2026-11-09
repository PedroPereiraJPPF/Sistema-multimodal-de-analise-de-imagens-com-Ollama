# Histórico do prompt

Cada mudança no prompt ganha uma versão (`PROMPT_VERSION` em [`app/prompts.py`](app/prompts.py)), é medida no benchmark antes de ser aceita e fica registrada aqui. O resumo de cada execução fica em [`benchmark/results/history.md`](benchmark/results/history.md); os relatórios completos são gerados localmente em `benchmark/results/` e não são versionados.

## v4 (descartada): títulos de seção, preços por tamanho e observações com asterisco

**Mudanças:**
- **Prompt** (descrições dos campos em [`app/presets.py`](app/presets.py)): títulos de seção não são itens; com vários preços por tamanho, usar o primeiro; observação com `*` que vale para um grupo não é descrição de um item.
- **Validação** (fora do prompt, em [`app/service.py`](app/service.py)): o texto `"null"` ou `"none"` vira `null` de verdade antes da validação Pydantic.
- **Gabarito** de `menus-real`: transcrição literal, com os erros que estão impressos ("Malho", "Romou", "paiha", "Quatro Quejos"), como manda a regra 3 do system prompt; categorias com "(375ml)". Com o gabarito novo, a v3 vai de 86% / 78% / 75% para 87% / 77% / 73%.
- **Relatórios por execução** (`benchmark/results/*.json`, `*.md`) saíram do git; só o `history.md` continua versionado.

**Resultado** (6 cardápios reais). Para isolar o efeito do prompt, a limpeza do `"null"` foi aplicada também às respostas da v3:

| Modelo | v3 | v3 + limpeza | v4 |
|---|---|---|---|
| qwen3.5:4b | 87% | 87% | 84% |
| gemma3:4b | 77% | 79% | 79% |
| qwen2.5vl:3b | 73% | 78% | 77% |

Sintético v4: 100% / 92% / 98% (v3: 100% / 90% / 95%).

**Leitura:**
- **O ganho veio da validação, não do prompt.** A limpeza do `"null"` sozinha leva o gemma na Comida Caseira de 79% para 90% e o qwen2.5vl de 73% para 100%.
- **Regra de preço por tamanho funcionou:** o qwen2.5vl preencheu os preços da pizzaria (57% → 79%).
- **Regra de título de seção foi ignorada:** o qwen3.5 continua listando "Porções", "Bebidas" e "Pratos Principais" como itens.
- **Regra do asterisco atrapalhou:** o qwen2.5vl no Sabores do Brasil passou a preencher a descrição com o nome do item vizinho (88% → 62%).
- **A queda do qwen3.5 (87% → 84%) é uma única troca:** "Nosso Boteco" virou "Boteco Nosso" (o mesmo erro da v2). Com 6 imagens, um campo errado move a média geral em cerca de 3 pontos. O dataset ainda é pequeno demais para separar diferenças dessa ordem.

**Decisão: v4 descartada.** As regras de prompt voltaram ao texto da v3 (`PROMPT_VERSION = "v3"`). Ficam a validação do `"null"` (código, vale para qualquer versão), o gabarito literal e os relatórios fora do git. A regra de preço por tamanho, a única que ajudou, é candidata a voltar sozinha numa próxima versão.

## v3: regras de cardápio para os erros vistos em fotos reais

**Problema observado (v2):** o dataset sintético estava em 100% e já não diferenciava versões. Com 3 cardápios reais (`menus-real`, só os gabaritos versionados, já que as imagens são de terceiros), a precisão caiu para cerca de 70%, e as respostas mostraram cinco padrões:

1. Descrição colada no nome: `"Feijoada Completa (acompanha arroz, ...)"`.
2. Categoria inventada: sem títulos de seção, o modelo repetia o nome do prato em `category`.
3. Preço copiado do vizinho em itens sem preço (Mousse, Suco, Água).
4. "CARDÁPIO" devolvido como nome do restaurante.
5. Cardápio cujos pratos só têm descrição: todos os modelos usaram a descrição como `name`.

**Mudança:** as descrições dos campos de `MenuItem` e `Menu` (em [`app/presets.py`](app/presets.py)) ganharam a regra que faltava em cada caso: `name` é só o título e fica `null` quando não há título; `description` vem sem parênteses; `price` é `null` se o item não tem preço próprio; `category` é `null` sem títulos de seção; "Cardápio" não é nome de restaurante. As regras ficaram nos campos, e não no system prompt, porque só valem para cardápios.

**Mudança na métrica:** os itens eram pareados pelo primeiro campo (o nome). Um prato sem nome nunca era pareado, nem quando a resposta estava certa. Agora o pareamento usa o primeiro campo **preenchido**. Para comparar com justiça, a v2 foi recalculada com a métrica nova:

| Dataset | Modelo | v2 (métrica antiga) | v2 (métrica nova) | v3 |
|---|---|---|---|---|
| menus-real (3) | qwen3.5:4b | 70% | 75% | **88%** |
| | gemma3:4b | 69% | 73% | **79%** |
| | qwen2.5vl:3b | 67% | 66% | **74%** |
| menus-synthetic (12) | qwen3.5:4b | 100% | | 100% |
| | gemma3:4b | | | 90% |
| | qwen2.5vl:3b | | | 95% |

**O que funcionou:** preço inventado sumiu (`items.price` 100% nos três modelos no dataset real); o gemma parou de repetir o nome do prato como categoria; o qwen3.5 parou de chamar o cardápio de "CARDÁPIO" e acertou 100% no Nosso Boteco. Sem regressão no sintético para o qwen3.5.

**O que não funcionou:**
- **Prato sem nome (Casa de Mainha):** os três modelos continuam pondo a descrição em `name`, apesar da regra explícita. A queda de `items.name` e `items.description` no dataset real vem daqui: com a métrica nova, esses itens passam a ser pareados e o erro aparece, em vez de sumir no F1 de `items`. Regras em texto não bastaram; o próximo passo é testar um exemplo (few-shot) ou mudar a ordem dos campos.
- **Modelos menores ignoram parte das regras:** o qwen2.5vl ainda junta a descrição ao nome, ainda repete "Chapa Mista" como categoria e ainda devolve "Cardápio"; o gemma mantém os parênteses.
- **Correção indevida:** a imagem tem "faranja"; o qwen3.5 e o gemma leem "farinha".

**Custo:** nenhum no tempo de inferência (14,0 s no qwen3.5, igual à v2).

**Validação com 6 cardápios** (3 novos: drinks com nomes repetidos entre seções, duas colunas, pizzaria com 3 preços por item):

| Modelo | 3 cardápios | 6 cardápios |
|---|---|---|
| qwen3.5:4b | 88% | **86%** |
| gemma3:4b | 79% | 78% |
| qwen2.5vl:3b | 74% | 75% |

A v3 se sustenta, e a ordem dos modelos não muda. Erros novos, candidatos para a v4:
- **A string `"null"`:** o gemma e o qwen2.5vl escrevem `"null"` entre aspas em vez de `null` (o gemma em 17 descrições, o qwen2.5vl no nome do restaurante). Isso se corrige na validação, não no prompt.
- **Título de seção como item:** "Porções", "Bebidas" e "Batidas" aparecem como pratos (o qwen3.5 ainda dá preço a eles).
- **Vários preços por item** (Broto/Média/Grande): o schema só tem um `price`. Cada modelo reage de um jeito: o qwen3.5 pega o primeiro, o gemma mistura tamanhos, o qwen2.5vl desiste (`null`). O preço de vizinho voltou (Pepperoni Lovers com o preço da pizza de cima). É uma limitação do schema.
- **Observação com asterisco** (vale para um grupo de itens) vira descrição do item mais próximo.
- **Duas colunas:** o gemma partiu "Costela Fogo de Chão" em dois itens e pôs a "Tábua Mista G" em Bebidas.

**Ressalva sobre o gabarito:** duas convenções minhas custam pontos que não são erro de leitura. A categoria foi rotulada sem "(375ml)", e o qwen3.5 incluiu, o que derruba `items.category` dele para 42% no Sabores do Brasil. E os textos com erros de imagem gerada por IA ("Malho", "Romou", "golabada") foram rotulados com a palavra correta, o que contradiz a regra 3 do prompt (transcrever exatamente).

## v2: descrever os campos dos itens de listas

**Problema observado (v1):** no benchmark de cardápios, `items.description` acertava só **36%**. A análise dos erros mostrou um padrão único: o modelo **nunca** preenchia a descrição (51 omissões, 0 descrições erradas). Os 36% eram apenas os pratos que de fato não têm descrição, em que `null` é o correto.

**Hipótese:** o prompt listava só os campos de primeiro nível (`restaurant_name`, `items`). Os campos de cada item (`name`, `description`, `price`, `category`) só existiam no JSON Schema, sem explicação. Somado à regra "use null se não estiver visível", o modelo não sabia que `description` é o texto impresso abaixo do nome do prato.

**Mudança:** `describe_fields` passou a descrever recursivamente os campos dos itens de listas. A mudança é genérica: vale também para os itens da nota fiscal e do inventário.

| Dataset | Modelo | v1 | v2 |
|---|---|---|---|
| menus-synthetic (12) | qwen3.5:4b | 88% | **100%** |
| ↳ `items.description` | | 36% | **100%** |
| ↳ inferência média | | 10,2 s | 12,6 s |

**Custo:** +2,4 s por cardápio, porque o modelo agora transcreve as descrições.

## v1: linha de base

Primeira versão rastreada. Ela já incorporava uma lição anterior ao versionamento: pedir datas **como impressas** (DD/MM/AAAA) em vez de convertidas para AAAA-MM-DD. O modelo de 4B lia `03/11/2026` como 11 de março ao converter, mas transcreve corretamente.
