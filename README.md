# Database Design — Sistema de Detecção de Incêndios Florestais

**FIAP — Global Solution 2026.1 · Tema macro: Economia Espacial**
**Disciplina:** Database Design
**Grupo:** Stratfy — Turma 2ESPH (Engenharia de Software)

| Integrante | RM |
|---|---|
| Anthony Sforzin | RM562096 |
| Luigi Mendes Cabrini | RM563552 |
| Rogério Cruz Arroyo | RM563517 |
| Bruno Koeke | RM561309 |

---

## 1. Visão geral

Este repositório entrega a **camada de dados** do projeto da Stratfy para a Global
Solution 2026: um **Sistema de Detecção de Incêndios Florestais** que cruza três fontes
públicas reais de **2025** sobre o Brasil:

- **Focos de calor por satélite** — INPE / Programa Queimadas (BDQueimadas), **3.466.399
  focos** detectados em 2025 por **13 satélites** (referência: **AQUA_M-T**).
- **Clima** — estações meteorológicas automáticas do **INMET / BDMEP** (medições horárias
  e agregados mensais).
- **Desmatamento** — supressão de vegetação por bioma, sistema **PRODES / INPE**.
- **Malha territorial** — Estados e Municípios do **IBGE** (códigos oficiais), usados para
  espacializar os focos (taxa de casamento município→IBGE de **99,75%**).

A "Economia Espacial" entra como **infraestrutura orbital de sensoriamento remoto**: são os
satélites que geram o dado primário (focos de calor, FRP, risco de fogo) que alimenta toda a
cadeia de decisão — da estatística (Data Science) ao roteamento de combate (Dynamic
Programming) e ao painel executivo (BI).

O **design lógico/relacional** já existia (PDFs técnicos — ver `docs/`). Este repositório
entrega a **parte executável e os complementos**:

1. **DDL Oracle completo** (`sql/deteccao_incendios_oracle.sql`) — 10 tabelas com
   SEQUENCEs, PK, FK, UNIQUE, CHECK, índices, `COMMENT ON` e INSERTs de exemplo reais.
2. **ETL em Python** (`etl/carga.py`) — lê os CSVs reais, gera os INSERTs de carga
   (`sql/insercoes_dados_reais.sql`), valida tudo num **mirror SQLite** e roda 5 consultas
   analíticas.
3. **Item 7 — Arquitetura Integrada** (`docs/arquitetura_integrada.md` + seção 6 deste
   README) que faltava no design original.
4. Dicionário de dados e justificativa de normalização (`docs/`).

---

## 2. Modelo de dados (10 tabelas)

```
T_BIOMA ──────────────┐
   │                  │
   │ 1:N              │ 1:N
   ▼                  ▼
T_DESMATAMENTO_BIOMA  T_FOCO_CALOR ──N:1── T_SATELITE
                          │   │
                   N:1 ───┘   └─── N:1 ─── T_MUNICIPIO ──N:1── T_ESTADO
                          │                                        ▲
                          │ N:N (T_FOCO_CONDICAO_CLIM)             │ 1:N
                          ▼                                        │
                   T_MEDICAO_CLIMATICA ──N:1── T_ESTACAO_METEOROLOGICA
                                                   │
                                                   │ 1:1
                                                   ▼
                                          T_LOCALIZACAO_ESTACAO
```

| # | Tabela | Papel | Cardinalidade-chave |
|---|---|---|---|
| 1 | `T_BIOMA` | Dimensão: 6 biomas brasileiros | — |
| 2 | `T_ESTADO` | Dimensão: 27 UFs (código IBGE) | — |
| 3 | `T_MUNICIPIO` | Dimensão: municípios IBGE + centroide | N:1 → `T_ESTADO` |
| 4 | `T_SATELITE` | Dimensão: 13 satélites (flag de referência) | — |
| 5 | `T_FOCO_CALOR` | **Fato**: focos de calor detectados | N:1 → satélite, município, bioma |
| 6 | `T_ESTACAO_METEOROLOGICA` | Dimensão: estações INMET | N:1 → `T_ESTADO` |
| 7 | `T_LOCALIZACAO_ESTACAO` | Geolocalização da estação | **1:1** → estação |
| 8 | `T_MEDICAO_CLIMATICA` | **Fato**: medições horárias | N:1 → estação |
| 9 | `T_FOCO_CONDICAO_CLIM` | **Associativa N:N** foco ↔ medição | PK composta |
| 10 | `T_DESMATAMENTO_BIOMA` | Fato anual PRODES por bioma | N:1 → `T_BIOMA` |

Detalhe completo de atributos em `docs/dicionario_de_dados.md`; justificativa de
normalização (1FN/2FN/3FN) em `docs/normalizacao.md`.

---

## 3. Estrutura do repositório

```
database/
├── README.md                          # este arquivo
├── sql/
│   ├── deteccao_incendios_oracle.sql  # DDL Oracle COMPLETO + inserts de exemplo
│   └── insercoes_dados_reais.sql      # INSERTs reais (gerado pelo ETL)
├── etl/
│   ├── carga.py                       # ETL: gera o SQL, valida em SQLite, roda queries
│   └── README.md                      # como rodar o ETL / conectar no Oracle
├── dados/                             # CSVs reais de referência (cópia local)
│   ├── estados_ibge.csv
│   ├── municipios_ibge.csv
│   ├── prodes_desmatamento_biomas_2025.csv
│   ├── focos_municipios_agg.csv
│   ├── focos_amostra.csv              # amostra de focos
│   ├── estacoes_inmet.csv
│   ├── clima_mensal_estacao.csv
│   ├── medicoes_amostra.csv
│   └── focos_resumo.json              # estatísticas globais de validação
├── deteccao_incendios.sqlite          # mirror gerado pelo ETL (validação)
└── docs/
    ├── dicionario_de_dados.md
    ├── arquitetura_integrada.md       # item 7
    ├── normalizacao.md
    ├── Deteccao_Incendios_Database_Design.pdf
    ├── Modelagem Logica.pdf
    └── Modelagem Relacional.pdf
```

---

## 4. Como executar o DDL (Oracle)

Pré-requisito: usuário Oracle com privilégios de `CREATE TABLE`/`CREATE SEQUENCE`.

```sql
-- No SQL*Plus / SQL Developer / SQLcl, conectado ao schema desejado:
@sql/deteccao_incendios_oracle.sql   -- cria sequences, tabelas, índices, comments
@sql/insercoes_dados_reais.sql       -- carrega os dados reais gerados pelo ETL
COMMIT;
```

O `deteccao_incendios_oracle.sql` já traz **INSERTs de exemplo** (amostra ilustrativa) e dá
`COMMIT`. Para a **carga em volume**, rode o ETL (seção 5) e depois execute
`insercoes_dados_reais.sql`.

> Observação: o `insercoes_dados_reais.sql` usa `ID_*` explícitos (não usa as SEQUENCEs),
> portanto pode ser carregado **isoladamente** sobre as tabelas vazias, sem conflito com os
> inserts de exemplo. Se quiser apenas a carga real, comente a seção 8 do DDL ou rode um
> `DELETE` antes (há um bloco de `DELETE` comentado no topo do arquivo de inserts).

---

## 5. Como executar o ETL e validar (Python)

Não é necessário ter Oracle instalado para validar o modelo: o ETL constrói um **mirror em
SQLite** que executa o **mesmo DDL** (traduzido) e os **mesmos INSERTs**, garantindo que
PK/FK/UNIQUE/CHECK são satisfeitos pelos dados reais.

```bash
cd build/repos/database/etl
python carga.py
```

O script:

1. lê os CSVs de `build/dados-preparados/` (fallback: `dados/`);
2. converte sentinela **-999 → NULL**;
3. gera `sql/insercoes_dados_reais.sql` (idempotente — reescreve a cada execução);
4. cria `deteccao_incendios.sqlite`, aplica o DDL e os INSERTs (**0 violações de
   integridade**);
5. imprime **5 consultas analíticas** de verificação.

Dependências: apenas a biblioteca padrão do Python (`csv`, `sqlite3`, `re`, `json`). Para a
conexão **opcional** com Oracle, use `oracledb` (ver `etl/README.md`).

### Evidência da última execução (resumo)

```
Q1) Contagem por tabela: BIOMA=6 · ESTADO=27 · MUNICIPIO=5498 · SATELITE=13 ·
    FOCO_CALOR=2000 · ESTACAO=590 · LOCALIZACAO=590 · MEDICAO=1000 ·
    FOCO_CONDICAO_CLIM=50 · DESMATAMENTO=6     (0 violações de integridade)

Q2) Focos por bioma (amostra): Cerrado 1025 · Amazônia 585 · Caatinga 186 · ...
    → reflete o ranking real (Cerrado e Amazônia concentram os focos de 2025).

Q3) Top UFs por focos (amostra): MT · TO · MA · BA · PI · PA · AM ...
    → exatamente a região MATOPIBA + arco do desmatamento.

Q4) Desmatamento PRODES 2025 (km²) × focos: Cerrado 7.235,27 · Amazônia 5.796,00 ...

Q5) Condição climática nos focos (N:N): umidade/temperatura médias associadas.
```

---

## 6. Item 7 — Arquitetura Integrada (Stratfy)

> Documento completo com diagrama Mermaid em `docs/arquitetura_integrada.md`.

O banco relacional desta disciplina é o **núcleo de persistência** de uma solução que
percorre todas as disciplinas do grupo Stratfy:

```
[Satélite/INPE] → [ETL Python] → [Banco Relacional Oracle] → [Data Science]
                                          │                        │
                                          ├──────────────→ [Dynamic Programming]
                                          │                        │
                                          └──────────────→ [BI / Dashboard] ←┘
```

1. **Satélite / INPE (Economia Espacial).** Constelação de 13 satélites (AQUA, TERRA,
   NOAA-20/21, GOES-16/19, NPP, METOP, MSG) detecta focos de calor e calcula FRP e risco de
   fogo. É o **sensor orbital** que origina o dado.
2. **ETL Python (esta disciplina).** `etl/carga.py` ingere os CSVs do INPE/INMET/IBGE/PRODES,
   limpa (sentinela -999 → NULL), normaliza e carrega o banco.
3. **Banco Relacional Oracle (esta disciplina).** Modelo em 3FN com 10 tabelas, integridade
   referencial e índices analíticos. **Fonte única de verdade** do projeto.
4. **Data Science.** Consome o banco para estatística descritiva e inferencial
   (sazonalidade, correlação focos × umidade × dias-sem-chuva × desmatamento) e modelos
   preditivos de risco.
5. **Dynamic Programming.** Usa os centroides dos municípios e o risco de fogo como **grafo
   ponderado** de risco; aplica programação dinâmica (caminho mínimo / alocação ótima de
   brigadas) sobre os focos persistidos.
6. **BI / Dashboard.** Camada de visualização executiva (mapas de calor, séries mensais,
   ranking de biomas/UFs) lendo as mesmas tabelas/consultas.

O banco é, portanto, o **ponto de integração**: todas as disciplinas leem e escrevem no
mesmo modelo, garantindo consistência entre análise estatística, otimização e visualização.

---

## 7. Fatos de validação dos dados (2025)

Extraídos do dataset completo (3.466.399 focos) e usados nas narrativas:

- **Sazonalidade:** pico em **set/2025 (833.039)**, out (823.767) e ago (594.309) — estação
  seca.
- **Biomas (focos):** Cerrado 1.784.865 · Amazônia 975.655 · Caatinga 445.091 ·
  Mata Atlântica 219.855 · Pantanal 28.936 · Pampa 11.994.
- **Estados-topo:** Maranhão, Tocantins, Mato Grosso, Piauí, Pará, Bahia (**MATOPIBA** +
  arco do desmatamento).
- **Satélites:** 13 plataformas; **AQUA_M-T** é a referência do INPE.
- **Casamento município→IBGE:** 99,75%.

---

## 8. Fontes dos dados

| Fonte | Conteúdo |
|---|---|
| INPE — Programa Queimadas (BDQueimadas) | Focos de calor, FRP, risco de fogo, satélites |
| INMET — BDMEP | Estações e medições meteorológicas |
| INPE — PRODES / BiomasBR | Desmatamento por bioma (2025) |
| IBGE — API de Localidades | Estados e municípios (códigos oficiais) |
