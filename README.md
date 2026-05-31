# Curated Lounge Index

Catálogo curado de salas VIP de aeroportos usado pelo app **Voy** (projeto Supabase `voyori`). Este repositório é a **fonte de verdade editorial** dos dados de lounges: o que está aqui no git deve, no futuro, abastecer a tabela `public.lounges` do banco de produção via pipeline automatizado (ver `docs/PLANO_INTEGRACAO.md`).

> **Status atual:** 736/736 registros enriquecidos (decisões de curadoria + flags). Schema do JSON ainda não está 100% uniforme (~150 registros em variantes a normalizar) e a sincronização git → banco ainda não está implementada.

---

## Para que serve este repo

- Manter um **dataset de 736 salas VIP** com schema rico (horários, amenidades, programas aceitos, política de acompanhantes, operador, etc.) em vez do dado escasso e poluído que hoje vive no banco.
- Sinalizar registros problemáticos (duplicatas, fechados, inexistentes, "não é uma sala") sem apagá-los — vira input para limpeza do banco.
- Servir de **base de versionamento**: cada alteração de dado é um commit auditável, com diff revisável em PR, em vez de UPDATE solto em produção.
- Futuramente, conectar este repo direto ao Supabase via GitHub Action de modo que `git push` → banco atualizado → app atualizado, sem deploy do app.

---

## Estrutura do repositório

```
curated-lounge-index/
├── README.md                       ← este arquivo
├── salas_vip.json                  ← FONTE BRUTA (736 registros do banco original)
├── scripts/
│   └── build_cleanup.py            ← classifica registros sinalizados → cleanup.json
├── data/
│   └── enriched/
│       ├── batch_01.json           ← 10 registros enriquecidos (índices 0–9)
│       ├── batch_02.json           ← 10 registros (índices 10–19)
│       ├── ...
│       ├── batch_74.json           ← 6 registros (índices 730–735, último)
│       └── cleanup.json            ← derivado: lista os 250 registros sinalizados
└── docs/
    └── PLANO_INTEGRACAO.md         ← plano detalhado de integração git → Supabase → Voy
```

**Por que batches de 10?** Foi a unidade de trabalho do enriquecimento (commit a cada 10 para manter histórico granular). Não é unidade lógica — o dataset final é a **concatenação dos 74 arquivos na ordem dos arquivos**, sempre 1:1 com os índices do `salas_vip.json`.

---

## O dataset

### Fonte
`salas_vip.json` — array com **736 objetos** copiados do banco original. Cada objeto tem chaves do CSV de exportação (note o BOM em `﻿Nome`):

```json
{
  "ID Supabase": "uuid",
  "﻿Nome": "Nome da Sala",
  "IATA": "GRU",
  "Aeroporto": "São Paulo Guarulhos",
  "Terminal": "Terminal 3",
  "Descrição": "texto livre original"
}
```

### Enriquecimento (schema canônico — 23 campos)

Cada registro em `data/enriched/batch_NN.json` deve seguir este schema:

| Campo | Tipo | Obrigatório | Observações |
|---|---|---|---|
| `lounge_id` | uuid | sim | mesmo `ID Supabase` da fonte (chave para sync) |
| `name` | string | sim | nome canônico |
| `airport_iata` | string | sim | código IATA de 3 letras |
| `airport_name` | string | sim | nome do aeroporto |
| `terminal` | string | sim | identificação do terminal |
| `location_description` | string | sim | descrição em PT do local físico |
| `hours_open_text` | string | sim | horário em texto livre (ex.: "05:00–23:00") |
| `open_days` | string[] | sim | dias da semana (`monday`…`sunday`) |
| `is_24h` | boolean | sim | true se aberto 24h |
| `amenities` | string[] | sim | tokens do vocabulário controlado (ver abaixo) |
| `accepted_programs` | string[] | sim | tokens do vocabulário controlado (ver abaixo) |
| `max_stay_minutes` | int \| null | sim | tempo máximo permitido |
| `children_policy` | string | sim | política para crianças em PT |
| `guest_policy` | string | sim | política para acompanhantes em PT |
| `voucher_info` | string \| null | sim | observações sobre vouchers |
| `photo_urls` | string[] | **sempre `[]`** | regra: jamais usar fotos da fonte (são genéricas) |
| `photo_quality` | string | **sempre `"none"`** | regra |
| `website_url` | string \| null | sim | site oficial |
| `operator` | string \| null | sim | quem opera (Plaza Premium, Cia aérea, etc.) |
| `source_urls` | string[] | sim | URLs de pesquisa (referência editorial) |
| `last_verified` | date | **sempre `"2026-05-28"`** | data da onda atual de verificação |
| `completeness_score` | int | sim | 0–72 (heurística, ver abaixo) |
| `notes` | string | sim | **deve terminar em `"Foto anterior generica removida."`** |

#### Vocabulário controlado — amenities
Tokens permitidos (subset estável; canonicalização pendente — ver Parte 2A do plano):
`wifi, food, beverages, showers, seating_areas, business_center, bar, spa_services, gym, sleeping_pods, kids_area, entertainment, parking, nursing_room, meeting_rooms, prayer_room, medical_services, smoking_area, transit_hotel, luggage_storage, printing_services, currency_exchange, retail, games_room, terrace, pool, jacuzzi, massage_services`

#### Vocabulário controlado — accepted_programs
Tokens permitidos (subset estável; canonicalização pendente):
`Priority Pass, LoungeKey, DragonPass, Diners Club, Amex Platinum, Amex Centurion, Mastercard Black, Visa Infinite, Capital One Venture X, Chase Sapphire Reserve, Citi Prestige, HSBC Premier, Star Alliance Gold` + variantes por companhia aérea (lista completa em `docs/PLANO_INTEGRACAO.md`).

#### `completeness_score` (heurística editorial)
- **55–72** — sala real, bem documentada, horários e programas confirmados
- **38–52** — sala real mas com lacunas (horário não confirmado, etc.)
- **10–30** — sinalizada (fechada, inexistente, duplicata, não é sala)
- **0–9** — registro inválido/sem informação

#### Sinalizações (flags) — devem aparecer no campo `notes`
| Flag | Quando usar |
|---|---|
| `DUPLICATA` | mesmo lounge já existe em outro registro do dataset |
| `CONFLITO` | dados contraditórios entre fontes |
| `FECHAD` ou `PERMANENTE` | **somente** se ESTE lounge específico está fechado |
| `NAO E UMA SALA` | é restaurante, bar, balcão de check-in, taxi aéreo, etc. |
| `VERIFICAR EXISTENCIA` | suspeita de não existir (cia não opera no aeroporto, etc.) |

> ⚠️ **Regra crítica:** para se referir a OUTROS lounges fechados dentro do texto da nota, usar "encerrou/encerrado" — nunca "fechado/PERMANENTE". O classificador automático em `scripts/build_cleanup.py` procura essas palavras.

---

## Arquivo derivado — `cleanup.json`

Gerado por `python3 scripts/build_cleanup.py`. Lê todos os `batch_*.json`, classifica pelas palavras-chave em `notes` e produz uma lista plana dos registros que precisam de ação:

```json
[
  {
    "lounge_id": "uuid",
    "name": "Nome",
    "airport_iata": "XXX",
    "issue_type": "duplicate" | "closed" | "nonexistent" | "data_conflict" | "not_a_lounge",
    "recommended_action": "...",
    "related_id_hint": "uuid ou null",
    "detail": "trecho da nota"
  }
]
```

**Estatísticas atuais (250 sinalizados):**
- 84 `duplicate`
- 61 `nonexistent`
- 51 `data_conflict`
- 39 `not_a_lounge`
- 15 `closed`

---

## Estatísticas gerais

| Métrica | Valor |
|---|---|
| Total de registros | 736 |
| `completeness_score` médio | **47.7** |
| Score médio dos **normais** (não sinalizados) | 53.3 |
| Score médio dos **sinalizados** | 16.8–44.6 (por categoria) |
| Abertos 24h | 123 (16.7%) |
| Sinalizados para cleanup | 250 (34%) |
| Saudáveis | 486 (66%) |

---

## Estado do banco (Supabase `voyori`, tabela `public.lounges`)

| | |
|---|---|
| Linhas hoje | 736 (mesmos IDs deste repo) |
| Linhas com `lat`/`lng` | 736 (100%) — **dado que o git não tem** |
| Linhas com `photo_url` | 489 (genéricas — regra manda zerar) |
| Linhas com `status='approved'` | 736 (inclusive os 250 problemáticos) |

Conclusão: o app **mostra os 250 lixos** hoje. O git tem o diagnóstico, falta o pipeline de aplicação.

Detalhes completos em [`docs/PLANO_INTEGRACAO.md`](docs/PLANO_INTEGRACAO.md).

---

## Pipeline futuro (planejado, não implementado)

```
   commit no git
        │
        ▼
  GitHub Action no push para main
        │
        ├─ valida schema canônico (falha PR se divergir)
        ├─ consolida batch_*.json em payload único
        └─ upsert idempotente por `id` na tabela lounges
                │
                ▼
        Supabase voyori.lounges atualizado
                │
                ▼
        app Voy reflete na hora (sem redeploy)
```

**Princípios de design:**
- Upsert por `id` — nunca duplica, sempre converge
- **Preserva `lat`/`lng`** no banco — o script não toca nessas colunas
- Deriva `status` das flags do `notes` → os 250 sinalizados saem do app automaticamente
- DDL (colunas novas) entra como **Supabase migration** versionada no mesmo repo

Plano detalhado, decisões em aberto e checklist de execução: [`docs/PLANO_INTEGRACAO.md`](docs/PLANO_INTEGRACAO.md).

---

## Como contribuir / editar dados

1. Edite o `batch_NN.json` correspondente ao(s) lounge(s).
2. Mantenha **TODAS** as regras do schema (em especial `photo_urls=[]`, `photo_quality="none"`, fim de `notes`).
3. Rode `python3 scripts/build_cleanup.py` para regenerar `cleanup.json`.
4. Commit + PR. Quando o pipeline estiver montado, o merge na main aplica no banco automaticamente.

### Validação manual rápida
```bash
python3 -c "
import json, glob
CANON = {'lounge_id','name','airport_iata','airport_name','terminal','location_description','hours_open_text','open_days','is_24h','amenities','accepted_programs','max_stay_minutes','children_policy','guest_policy','voucher_info','photo_urls','photo_quality','website_url','operator','source_urls','last_verified','completeness_score','notes'}
issues = []
for fn in sorted(glob.glob('data/enriched/batch_*.json')):
    for r in json.load(open(fn)):
        if r.get('photo_urls') != []: issues.append(f'{fn}: photo_urls')
        if r.get('photo_quality') != 'none': issues.append(f'{fn}: photo_quality')
        n = r.get('notes','')
        if n and not n.endswith('removida.'): issues.append(f'{fn}: notes ending')
        extra = set(r.keys()) - CANON
        missing = CANON - set(r.keys())
        if extra or missing: issues.append(f'{fn}: schema drift extra={extra} missing={missing}')
print('OK' if not issues else f'{len(issues)} issues:\\n' + '\\n'.join(issues[:20]))
"
```

---

## Para IAs (agentes)

Se você é uma IA trabalhando neste repo, leia primeiro:
1. **`docs/PLANO_INTEGRACAO.md`** — contexto completo do produto e da integração
2. Este README (especialmente a seção do schema canônico e as flags)
3. `salas_vip.json` para conferir o ID e a descrição original de qualquer registro

**Regras invioláveis quando editar `data/enriched/batch_*.json`:**
- `photo_urls` SEMPRE `[]`
- `photo_quality` SEMPRE `"none"`
- `notes` SEMPRE terminam com `"Foto anterior generica removida."`
- IDs em ordem do `salas_vip.json`
- Flags em PT-BR, palavras exatas (`DUPLICATA`, `NAO E UMA SALA`, etc.)
- Para citar OUTROS lounges fechados, usar "encerrou/encerrado" — nunca "fechado"
- Nada de inventar tokens fora dos vocabulários controlados

**Nunca executar:**
- Alterações em qualquer banco Supabase (este repo é só dado — banco é responsabilidade do pipeline)
- Force push, reset --hard, ou qualquer operação destrutiva sem instrução explícita
