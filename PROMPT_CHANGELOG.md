# Histórico do prompt

Cada mudança no prompt ganha uma versão (`PROMPT_VERSION` em [`app/prompts.py`](app/prompts.py)), é medida no benchmark antes de ser aceita e fica registrada aqui. Os números completos de cada execução estão em [`benchmark/results/`](benchmark/results/).

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
