# Plano de Integração — git → Supabase → Voy

> Plano de ação para conectar este repositório (fonte de verdade editorial) ao banco de produção do app **Voy** (projeto Supabase `voyori`, tabela `public.lounges`), de modo que `git push` → banco atualizado → app atualizado, sem mexer no app.

**Status:** plano aprovado, **nada foi executado ainda em nenhum banco**. Decisões abertas no final do documento.

---

## 1. Estado real (medido em 2026-05-31)

### 1.1 Banco `voyori.lounges` (produção)

| Métrica | Valor | Implicação |
|---|---|---|
| Total de linhas | **736** | Mesmos IDs do repo → sync é **UPSERT por `id`**, nunca insert do zero |
| Com `lat`/`lng` | **736 (100%)** | ⚠️ O banco TEM coordenadas; o JSON **não tem** → precisa ser preservado |
| Com `photo_url` | **489** | São as fotos genéricas que a regra editorial manda zerar |
| `status='approved'` | **736 (100%)** | ⚠️ O app está mostrando os 250 problemáticos hoje |
| `source` distintos | 2 | (não bloqueia integração) |
| `status` distintos | 1 | tudo `approved` — não há vocabulário de status no banco |

**Schema atual da tabela (campos relevantes):**
- `id` (uuid, PK) — chave do upsert
- `name`, `airport_iata`, `airport_name`, `terminal`, `location_description`
- `amenities` (text[]), `accepted_programs` (text[])
- `hours_open_text`, `voucher_info`, `photo_url`, `website_url`
- `lat`, `lng` (double precision) — **só no banco**
- `source` (default `'curated'`), `status` (default `'approved'`)
- `submitted_by`, `created_at`, `updated_at`

### 1.2 Repositório git / JSON enriquecido

**736 registros distribuídos em 74 batches**, mas o schema **não está 100% uniforme**:

| Grupo de batches | Qtde | Diferença em relação ao canônico |
|---|---|---|
| Schema rico (586 registros) | 586 | OK — é a referência |
| `batch_62`–`batch_66` (reduzido) | 50 | Faltam: `airport_name`, `hours_open_text`, `open_days`, `is_24h`, `location_description`, `max_stay_minutes`, `children_policy`, `guest_policy`, `voucher_info`, `website_url`, `operator`, `source_urls` |
| `batch_57`–`batch_61` + `batch_67`–`batch_71` (variante) | 100 | Usam `iata`/`city`/`country`/`flags`/`classifier_notes` em lugar dos nomes canônicos; mesmas lacunas acima |
| Typo isolado em `batch_53` | 1 | `completeness_score_` (com underscore) |
| Notes sem sufixo padrão | 3 | Não terminam em `"Foto anterior generica removida."` |

**Drift de vocabulário:**
- `amenities`: **55 tokens distintos** (vs. ~30 do vocabulário oficial). Exemplos: `shower` vs `showers`, `spa` vs `spa_services`, `sleep_pods` / `sleeping_pods` / `sleep_rooms`, `meeting_room` vs `meeting_rooms`.
- `accepted_programs`: **192 tokens distintos** (vs. ~70 oficiais). Existem duplicatas por caixa (`priority_pass` E `Priority Pass`), tokens snake_case fora do padrão (`pay_per_use`, `oneworld_emerald`, `business_class`), variantes de companhias que deveriam ser canonicalizadas.

**Conclusão:** o git **ainda não está pronto** para virar fonte de verdade — precisa ser saneado primeiro (Parte 2A).

---

## 2. O que precisa ser corrigido

### 2A. No JSON / git (pré-requisito — trabalho 100% no repo, sem tocar em banco)

1. **Uniformizar os 150 registros divergentes** ao schema canônico de 23 campos:
   - Renomear `iata` → `airport_iata`
   - Mapear `city` + `country` para `airport_name` e/ou `location_description`
   - Consolidar `flags` / `classifier_notes` dentro de `notes` no padrão de flags PT-BR
   - Adicionar os 12 campos faltantes (`hours_open_text`, `open_days`, `is_24h`, etc.) com null/[]/valores neutros quando não disponíveis
2. **Corrigir o typo** `completeness_score_` em `batch_53.json`
3. **Ajustar as 3 notas** que não terminam em `"Foto anterior generica removida."`
4. **Canonicalizar vocabulários:**
   - Tabela de-para reduzindo `amenities` de ~55 → ~30 tokens
   - Tabela de-para reduzindo `accepted_programs` de ~192 → ~70 tokens
   - Aplicar em todos os 736 registros
5. **Versionar 1 schema oficial:**
   - `docs/lounge.schema.json` (JSON Schema 2020-12) com enums dos vocabulários
   - Validador automático em CI rejeita PR que diverja
6. **Snapshot consolidado para sync:**
   - Script `scripts/build_consolidated.py` que concatena os 74 batches em `data/dist/lounges.json` (gerado, ignorado pelo git ou commitado conforme decisão)

### 2B. No banco `lounges` (expandir — nunca reduzir)

O banco atual **não consegue receber** os campos ricos do JSON porque as colunas não existem. Precisa ganhar (via migration):

| Campo do JSON | Coluna a criar | Tipo PostgreSQL |
|---|---|---|
| `is_24h` | `is_24h` | `boolean` |
| `open_days` | `open_days` | `text[]` |
| `max_stay_minutes` | `max_stay_minutes` | `integer` |
| `children_policy` | `children_policy` | `text` |
| `guest_policy` | `guest_policy` | `text` |
| `operator` | `operator` | `text` |
| `completeness_score` | `completeness_score` | `integer` |
| `last_verified` | `last_verified` | `date` |
| `source_urls` | `source_urls` | `text[]` |
| `notes` (curadoria) | `curation_notes` | `text` |

**Reaproveitando colunas existentes:**
- `status`: ampliar vocabulário para `'approved'`/`'duplicate'`/`'closed'`/`'nonexistent'`/`'not_a_lounge'`/`'needs_review'`. Os 250 sinalizados são **demovidos** para o status apropriado (não deletados — auditável e reversível). O app filtra `status='approved'`.
- `source`: continua sendo `'curated'` para tudo que vem deste repo.

**Colunas que permanecem só no banco:**
- `lat`, `lng` (o JSON não tem coordenadas — preservar)
- `created_at`, `updated_at` (geridos pelo Postgres)
- `submitted_by` (não se aplica a curado)

**Migration (rascunho — NÃO APLICAR sem revisão):**
```sql
-- supabase/migrations/YYYYMMDDHHMMSS_lounges_enrichment.sql
ALTER TABLE public.lounges
  ADD COLUMN IF NOT EXISTS is_24h boolean,
  ADD COLUMN IF NOT EXISTS open_days text[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS max_stay_minutes integer,
  ADD COLUMN IF NOT EXISTS children_policy text,
  ADD COLUMN IF NOT EXISTS guest_policy text,
  ADD COLUMN IF NOT EXISTS operator text,
  ADD COLUMN IF NOT EXISTS completeness_score integer,
  ADD COLUMN IF NOT EXISTS last_verified date,
  ADD COLUMN IF NOT EXISTS source_urls text[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS curation_notes text;

-- vocabulário de status (constraint, não enum, para permitir evolução)
ALTER TABLE public.lounges
  ADD CONSTRAINT lounges_status_check
  CHECK (status IN ('approved','duplicate','closed','nonexistent','not_a_lounge','needs_review'));
```

---

## 3. Arquitetura "git conectado direto no projeto"

O Supabase **não puxa do git nativamente**. O padrão que entrega o efeito desejado (`git push` → app atualizado) e que recomendamos é o **GitHub Action no push**:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. dev faz commit/PR alterando data/enriched/batch_NN.json       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. PR check: validate-schema.yml                                 │
│    - roda scripts/validate.py contra docs/lounge.schema.json     │
│    - falha se schema/vocabulário divergem                        │
│    - merge bloqueado se não passar                               │
└──────────────────────────────────────────────────────────────────┘
                              │ (merge na main)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. sync-supabase.yml                                             │
│    - rebuild de data/dist/lounges.json                           │
│    - mapeia para schema do banco (DROP photo_urls/photo_quality, │
│      mantém lat/lng intactos, mapeia flags → status)             │
│    - executa UPSERT idempotente via SERVICE_ROLE_KEY:            │
│      INSERT ... ON CONFLICT (id) DO UPDATE SET ...               │
│        (lista explícita de colunas — NUNCA lat, lng)             │
│    - reporta diff (linhas mudadas) no run                        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. Supabase voyori.lounges atualizado                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. App Voy reflete na hora (é só dado — sem redeploy)            │
└──────────────────────────────────────────────────────────────────┘
```

### Alternativas consideradas

| Opção | Pró | Contra |
|---|---|---|
| **GitHub Action no push (recomendada)** | Padrão da indústria, fácil rollback (revert do commit), logs centralizados | Precisa de secret no GitHub |
| Edge Function + webhook do GitHub | Tudo dentro do Supabase | Mais frágil, debug pior, retry manual |
| `supabase db push` manual | Simples | Operação manual ≠ "git é fonte de verdade" |
| Realtime broadcast direto | Latência mínima | Não resolve persistência |

---

## 4. Roadmap por fases

> Cada fase tem critério de saída claro. Nenhuma fase começa antes da anterior estar verificada.

### Fase 0 — Snapshot defensivo *(antes de QUALQUER coisa em banco)*
- **Branch Supabase** do `voyori` ou snapshot da tabela `lounges` em `lounges_backup_YYYYMMDD`
- Critério de saída: snapshot acessível e testado

### Fase 1 — Sanear o JSON (Parte 2A)
- Uniformizar os 150 registros divergentes
- Canonicalizar amenities + accepted_programs
- Adicionar `docs/lounge.schema.json`
- Adicionar `scripts/validate.py`
- Critério de saída: `python3 scripts/validate.py` → 0 erros em todos os 736

### Fase 2 — CI de validação
- `.github/workflows/validate-schema.yml` roda em todo PR
- Required check no branch `main`
- Critério de saída: PR experimental com schema quebrado é bloqueado

### Fase 3 — Migration do banco (Parte 2B)
- Adicionar `supabase/migrations/YYYYMMDDHHMMSS_lounges_enrichment.sql`
- Aplicar via `supabase db push` em ambiente de staging primeiro
- Critério de saída: colunas novas existem, constraints validadas, RLS revisada

### Fase 4 — Script de sync idempotente
- `scripts/sync_to_supabase.py`:
  - Lê todos os `batch_*.json` em ordem
  - Aplica de-para JSON → colunas do banco
  - Calcula `status` a partir das flags em `notes`
  - Faz `UPSERT ON CONFLICT (id)` com **lista explícita de colunas** (zero risco de tocar `lat`/`lng`)
  - Modo `--dry-run` que imprime diff sem executar
- Critério de saída: dry-run mostra mudança esperada exata; smoke test em staging passa

### Fase 5 — Secret + Action de sync
- Criar `SUPABASE_SERVICE_ROLE_KEY` como secret do repositório
- `.github/workflows/sync-supabase.yml` roda em push para `main`
- Critério de saída: merge experimental em staging dispara sync; tabela reflete

### Fase 6 — Ajustes no app Voy
- Garantir que queries filtram `status='approved'`
- (Opcional) Expor campos novos na UI (is_24h, política de acompanhantes, etc.)
- Critério de saída: app não mostra mais os 250 sinalizados; campos novos visíveis quando desejado

### Fase 7 — Cutover de produção
- Aplicar migration em produção
- Liberar Action de sync para `main` apontando para produção
- Monitorar 24h
- Critério de saída: contagens ok, sem regressão de UX no Voy

---

## 5. Mapeamento de-para (referência)

### JSON → banco (UPSERT)
```
batch.lounge_id          → lounges.id                       (chave)
batch.name               → lounges.name
batch.airport_iata       → lounges.airport_iata
batch.airport_name       → lounges.airport_name
batch.terminal           → lounges.terminal
batch.location_description → lounges.location_description
batch.hours_open_text    → lounges.hours_open_text
batch.amenities          → lounges.amenities
batch.accepted_programs  → lounges.accepted_programs
batch.voucher_info       → lounges.voucher_info
batch.website_url        → lounges.website_url
batch.is_24h             → lounges.is_24h                   (coluna nova)
batch.open_days          → lounges.open_days                (coluna nova)
batch.max_stay_minutes   → lounges.max_stay_minutes         (coluna nova)
batch.children_policy    → lounges.children_policy          (coluna nova)
batch.guest_policy       → lounges.guest_policy             (coluna nova)
batch.operator           → lounges.operator                 (coluna nova)
batch.completeness_score → lounges.completeness_score       (coluna nova)
batch.last_verified      → lounges.last_verified            (coluna nova)
batch.source_urls        → lounges.source_urls              (coluna nova)
batch.notes              → lounges.curation_notes           (coluna nova)

batch.photo_urls=[]      → lounges.photo_url = NULL         (zera as 489 fotos genéricas)
batch.photo_quality      → (descartado — informação derivada)

NUNCA TOCAR:
  lounges.lat
  lounges.lng
  lounges.created_at
  lounges.updated_at  (gerido por trigger)
  lounges.submitted_by
  lounges.source       (mantém 'curated')
```

### Flags em `notes` → `status` no banco
```
"DUPLICATA" presente           → status = 'duplicate'
"FECHAD" ou "PERMANENTE"       → status = 'closed'
"NAO E UMA SALA"               → status = 'not_a_lounge'
"VERIFICAR EXISTENCIA"         → status = 'nonexistent'
"CONFLITO" presente            → status = 'needs_review'
nenhuma flag                   → status = 'approved'
```
**Precedência** (caso múltiplas flags): `closed` > `not_a_lounge` > `duplicate` > `nonexistent` > `needs_review` > `approved`.

---

## 6. Decisões em aberto (revisar com o time)

### 6.1 `lat`/`lng` — onde vive a fonte de verdade?
- **Opção A (recomendada no curto prazo):** ficam só no banco. O sync nunca toca essas colunas. Quando precisar editar coordenadas, edita direto no banco ou via admin.
- **Opção B:** exportar uma vez do banco e trazer para o JSON, e o git passa a ser dono completo (inclusive coordenadas). Bom no longo prazo, custo de migração agora.

### 6.2 Fotos reais
A regra atual zera tudo. Quando quiserem fotos reais:
- Criar tabela `lounge_photos` (espelhar `poi_photos` que já existe no projeto)
- Bucket no Storage para uploads
- Manter `photo_url` na `lounges` como "foto principal" (cover) → primeira aprovada de `lounge_photos`

### 6.3 Vocabulário de `status`
Confirmar tokens finais: `approved`, `duplicate`, `closed`, `nonexistent`, `not_a_lounge`, `needs_review`. Falta algum?

### 6.4 Quem dispara o sync
- Push automático em `main`? (recomendado, mais simples)
- Ou um workflow manual `workflow_dispatch` aprovado pelo time? (mais seguro no início)

### 6.5 Ambiente intermediário
- Aplicar migrations e Actions primeiro num **branch do Supabase** ou projeto de staging?
- Recomendação: sim — o `voyori` é produção; ter staging evita risco.

---

## 7. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Sync sobrescreve `lat`/`lng` por engano | Lista explícita de colunas no UPSERT; **nunca** `SELECT *`; teste com `pg_dump` antes/depois |
| Token novo aparece no JSON e quebra constraint | Validação em CI rejeita antes do merge |
| App quebra ao ver `status≠approved` | Auditar queries do Voy **antes** de aplicar status novo |
| Service role key vaza | Secret no GitHub (não em variables); rotacionar pós-incidente |
| Rollback necessário | `git revert` no commit + re-run da Action restaura estado anterior; snapshot da Fase 0 é o último recurso |

---

## 8. Critérios de "pronto"

- [ ] Todos os 736 registros validam contra `docs/lounge.schema.json`
- [ ] `cleanup.json` regenerado e auditado
- [ ] Migration aplicada em staging sem erro
- [ ] Sync em staging mostra diff exato esperado em dry-run
- [ ] App em staging mostra apenas registros `approved`
- [ ] Sync de produção rodado e auditado
- [ ] README do repo atualizado refletindo o pipeline ao vivo
- [ ] Runbook de incidentes documentado (`docs/RUNBOOK.md`)

---

**Nada deste documento foi executado em qualquer banco.** É um plano para revisão e aprovação do time antes de qualquer ação.
