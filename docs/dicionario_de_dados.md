# Dicionário de Dados

**Sistema de Detecção de Incêndios Florestais** — Database Design
**Grupo Stratfy** (FIAP GS 2026.1) · SGBD-alvo: Oracle 19c+

Convenções:
- **Obrig.** = obrigatoriedade (NOT NULL = Sim).
- Tipos no padrão Oracle. No mirror SQLite: `NUMBER(p,s)→REAL`, `NUMBER(p)→INTEGER`,
  `VARCHAR2/CHAR→TEXT`, `TIMESTAMP/DATE→TEXT`.
- **PK** = chave primária; **FK** = chave estrangeira; **UK** = chave única.
- Sentinela `-999` das fontes é convertido em **NULL** na carga.

---

## 1. T_BIOMA — Biomas brasileiros

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_BIOMA | Identificador substituto do bioma | NUMBER | 4 | Sim | **PK** | 2 |
| NM_BIOMA | Nome do bioma | VARCHAR2 | 40 | Sim | **UK** (NM_BIOMA) | `Cerrado` |

---

## 2. T_ESTADO — Unidades da Federação (IBGE)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_ESTADO | Código IBGE da UF | NUMBER | 4 | Sim | **PK** | 51 |
| NM_ESTADO | Nome da UF | VARCHAR2 | 60 | Sim | — | `Mato Grosso` |
| SG_UF | Sigla da UF (2 letras) | CHAR | 2 | Sim | **UK** (SG_UF) | `MT` |
| NM_REGIAO | Região geográfica | VARCHAR2 | 15 | Sim | CHECK ∈ {Norte, Nordeste, Centro-Oeste, Sudeste, Sul} | `Centro-Oeste` |

---

## 3. T_MUNICIPIO — Municípios (IBGE) com centroide

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_MUNICIPIO | Código IBGE do município (7 díg.) | NUMBER | 8 | Sim | **PK** | 5103254 |
| NM_MUNICIPIO | Nome do município | VARCHAR2 | 120 | Sim | **UK** (NM_MUNICIPIO, ID_ESTADO) | `Colniza` |
| ID_ESTADO | UF do município | NUMBER | 4 | Sim | **FK** → T_ESTADO | 51 |
| CD_MICRORREGIAO | Código IBGE da microrregião | NUMBER | 6 | Não | — | 510170 |
| LATITUDE | Latitude do centroide (graus dec.) | NUMBER | 9,6 | Não | CHECK −90..90 | -9.160572 |
| LONGITUDE | Longitude do centroide (graus dec.) | NUMBER | 9,6 | Não | CHECK −180..180 | -60.207402 |

---

## 4. T_SATELITE — Plataformas de detecção (INPE)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_SATELITE | Identificador substituto do satélite | NUMBER | 4 | Sim | **PK** | 1 |
| NM_SATELITE | Nome do satélite/sensor | VARCHAR2 | 40 | Sim | **UK** (NM_SATELITE) | `AQUA_M-T` |
| FL_REFERENCIA | Satélite de referência do INPE (S/N) | CHAR | 1 | Sim | CHECK ∈ {S, N}; default `N` | `S` |

---

## 5. T_FOCO_CALOR — Focos de calor detectados (tabela fato)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_FOCO | Identificador substituto do foco | NUMBER | 12 | Sim | **PK** | 1042 |
| FOCO_ID_BDQ | ID de origem no BDQueimadas | VARCHAR2 | 40 | Não | — | `BDQ-2025-001042` |
| ID_SATELITE | Satélite que detectou o foco | NUMBER | 4 | Sim | **FK** → T_SATELITE | 1 |
| ID_MUNICIPIO | Município do foco | NUMBER | 8 | Não | **FK** → T_MUNICIPIO | 5103254 |
| ID_BIOMA | Bioma do foco | NUMBER | 4 | Não | **FK** → T_BIOMA | 1 |
| DT_PASSAGEM | Data/hora UTC da passagem | TIMESTAMP | — | Sim | — | `2025-09-12 17:30:00` |
| LATITUDE | Latitude do foco (graus dec.) | NUMBER | 9,6 | Sim | CHECK −90..90 | -9.160572 |
| LONGITUDE | Longitude do foco (graus dec.) | NUMBER | 9,6 | Sim | CHECK −180..180 | -60.207402 |
| NUM_DIAS_SEM_CHUVA | Dias sem chuva até o foco | NUMBER | 4 | Não | CHECK ≥ 0 | 12 |
| PRECIPITACAO_MM | Precipitação associada (mm) | NUMBER | 7,2 | Não | CHECK ≥ 0 | 0.0 |
| RISCO_FOGO | Índice de risco de fogo do INPE | NUMBER | 4,3 | Não | CHECK 0..1 | 0.910 |
| FRP_MW | Fire Radiative Power (MW) | NUMBER | 9,2 | Não | CHECK ≥ 0 | 78.40 |

---

## 6. T_ESTACAO_METEOROLOGICA — Estações INMET

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_ESTACAO | Identificador substituto da estação | NUMBER | 6 | Sim | **PK** | 1 |
| CD_WMO | Código WMO/OMM | VARCHAR2 | 10 | Sim | **UK** (CD_WMO) | `A001` |
| NM_ESTACAO | Nome da estação | VARCHAR2 | 120 | Sim | — | `BRASILIA` |
| ID_ESTADO | UF da estação | NUMBER | 4 | Sim | **FK** → T_ESTADO | 53 |
| DT_FUNDACAO | Início de operação | DATE | — | Não | — | `2000-05-07` |

---

## 7. T_LOCALIZACAO_ESTACAO — Geolocalização da estação (1:1)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_ESTACAO | Estação (PK e FK 1:1) | NUMBER | 6 | Sim | **PK** + **FK** → T_ESTACAO_METEOROLOGICA | 1 |
| LATITUDE | Latitude da estação (graus dec.) | NUMBER | 9,6 | Sim | CHECK −90..90 | -15.789444 |
| LONGITUDE | Longitude da estação (graus dec.) | NUMBER | 9,6 | Sim | CHECK −180..180 | -47.925833 |
| ALTITUDE_M | Altitude (m) | NUMBER | 7,2 | Não | — | 1160.96 |

---

## 8. T_MEDICAO_CLIMATICA — Medições horárias (INMET, tabela fato)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_MEDICAO | Identificador substituto da medição | NUMBER | 12 | Sim | **PK** | 1 |
| ID_ESTACAO | Estação da medição | NUMBER | 6 | Sim | **FK** → T_ESTACAO_METEOROLOGICA | 1 |
| DT_HORA_UTC | Data/hora UTC da medição | TIMESTAMP | — | Sim | **UK** (ID_ESTACAO, DT_HORA_UTC) | `2025-01-01 00:00:00` |
| PRECIPITACAO_MM | Precipitação na hora (mm) | NUMBER | 7,2 | Não | CHECK ≥ 0 | 0.00 |
| PRESSAO_HPA | Pressão ao nível da estação (hPa) | NUMBER | 7,2 | Não | — | 886.10 |
| PRESSAO_MAX_HPA | Pressão máxima na hora (hPa) | NUMBER | 7,2 | Não | — | 886.10 |
| PRESSAO_MIN_HPA | Pressão mínima na hora (hPa) | NUMBER | 7,2 | Não | — | 885.50 |
| RADIACAO_KJ_M2 | Radiação global (kJ/m²) | NUMBER | 9,2 | Não | — | NULL |
| TEMP_AR_C | Temperatura do ar — bulbo seco (°C) | NUMBER | 5,2 | Não | — | 20.80 |
| TEMP_ORVALHO_C | Temperatura do ponto de orvalho (°C) | NUMBER | 5,2 | Não | — | 19.50 |
| TEMP_MAX_C | Temperatura máxima na hora (°C) | NUMBER | 5,2 | Não | — | 20.90 |
| TEMP_MIN_C | Temperatura mínima na hora (°C) | NUMBER | 5,2 | Não | — | 20.70 |
| UMIDADE_REL_PCT | Umidade relativa do ar (%) | NUMBER | 5,2 | Não | CHECK 0..100 | 92 |
| UMIDADE_MAX_PCT | Umidade máxima na hora (%) | NUMBER | 5,2 | Não | CHECK 0..100 | 92 |
| UMIDADE_MIN_PCT | Umidade mínima na hora (%) | NUMBER | 5,2 | Não | CHECK 0..100 | 90 |
| VENTO_DIR_GRAUS | Direção do vento (graus) | NUMBER | 5,2 | Não | CHECK 0..360 | 8 |
| VENTO_RAJADA_MS | Rajada máxima de vento (m/s) | NUMBER | 6,2 | Não | CHECK ≥ 0 | 3.60 |
| VENTO_VEL_MS | Velocidade média do vento (m/s) | NUMBER | 6,2 | Não | CHECK ≥ 0 | 1.80 |

---

## 9. T_FOCO_CONDICAO_CLIM — Associativa N:N (foco ↔ medição)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_FOCO | Foco de calor | NUMBER | 12 | Sim | **PK** (composta) + **FK** → T_FOCO_CALOR | 1 |
| ID_MEDICAO | Medição climática associada | NUMBER | 12 | Sim | **PK** (composta) + **FK** → T_MEDICAO_CLIMATICA | 1 |
| DISTANCIA_KM | Distância foco↔estação (km) | NUMBER | 8,3 | Não | CHECK ≥ 0 | 842.350 |
| DIF_TEMPO_MIN | Diferença de tempo (min) | NUMBER | 8 | Não | — | 45 |

---

## 10. T_DESMATAMENTO_BIOMA — Desmatamento anual por bioma (PRODES)

| Atributo | Descrição | Tipo | Tam. | Obrig. | Restrição | Exemplo real |
|---|---|---|---|---|---|---|
| ID_DESMAT | Identificador substituto do registro | NUMBER | 8 | Sim | **PK** | 2 |
| ID_BIOMA | Bioma | NUMBER | 4 | Sim | **FK** → T_BIOMA; **UK** (ID_BIOMA, ANO_PRODES) | 2 |
| ANO_PRODES | Ano de referência do PRODES | NUMBER | 4 | Sim | CHECK 1988..2100; **UK** (ID_BIOMA, ANO_PRODES) | 2025 |
| AREA_SUPRIMIDA_KM2 | Área suprimida no ano (km²) | NUMBER | 12,2 | Sim | CHECK ≥ 0 | 7235.27 |
| VARIACAO_PCT | Variação % frente ao ano anterior | NUMBER | 6,2 | Não | — | -11.49 |
| FONTE | Fonte do dado | VARCHAR2 | 60 | Não | — | `INPE/PRODES-BiomasBR` |

---

## Índices secundários

| Índice | Tabela | Coluna(s) | Finalidade |
|---|---|---|---|
| IX_FOCO_DT_PASSAGEM | T_FOCO_CALOR | DT_PASSAGEM | Séries temporais / sazonalidade |
| IX_FOCO_BIOMA | T_FOCO_CALOR | ID_BIOMA | Agregação por bioma |
| IX_FOCO_MUNICIPIO | T_FOCO_CALOR | ID_MUNICIPIO | Junção/agregação por município |
| IX_FOCO_SATELITE | T_FOCO_CALOR | ID_SATELITE | Análise por satélite |
| IX_FOCO_RISCO | T_FOCO_CALOR | RISCO_FOGO | Filtros por faixa de risco |
| IX_MUNICIPIO_ESTADO | T_MUNICIPIO | ID_ESTADO | Junção município→UF |
| IX_MEDICAO_ESTACAO | T_MEDICAO_CLIMATICA | ID_ESTACAO | Junção medição→estação |
| IX_MEDICAO_DT | T_MEDICAO_CLIMATICA | DT_HORA_UTC | Séries temporais climáticas |
| IX_ESTACAO_ESTADO | T_ESTACAO_METEOROLOGICA | ID_ESTADO | Junção estação→UF |
| IX_DESMAT_BIOMA | T_DESMATAMENTO_BIOMA | ID_BIOMA | Junção desmatamento→bioma |
