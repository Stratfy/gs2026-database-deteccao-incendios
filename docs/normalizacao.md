# Normalização do Modelo

**Sistema de Detecção de Incêndios Florestais** — Database Design
**Grupo Stratfy** (FIAP GS 2026.1)

O modelo está na **3ª Forma Normal (3FN)**. Este documento justifica o enquadramento em
1FN, 2FN e 3FN e descreve as redundâncias deliberadamente evitadas.

---

## 1. Primeira Forma Normal (1FN)

> *Todos os atributos são atômicos; não há grupos repetitivos nem atributos multivalorados.*

- Cada coluna armazena **um único valor indivisível**. Ex.: latitude e longitude são colunas
  numéricas separadas (`LATITUDE`, `LONGITUDE`), nunca um campo textual "lat,lon".
- A geolocalização da estação foi **decomposta** em sua própria tabela
  (`T_LOCALIZACAO_ESTACAO`), em vez de empacotar coordenadas+altitude num campo composto.
- Listas (vários satélites por foco, várias medições por foco) **não** são armazenadas em
  colunas repetidas: viram **linhas** em tabelas próprias e relacionamentos
  (`T_FOCO_CALOR` → `T_SATELITE`; `T_FOCO_CONDICAO_CLIM` para o N:N foco↔medição).
- Toda tabela possui **chave primária** que identifica unicamente cada linha.

**Conclusão:** o modelo satisfaz a 1FN.

---

## 2. Segunda Forma Normal (2FN)

> *Está em 1FN e todo atributo não-chave depende da chave primária inteira (sem dependência
> parcial de parte de uma chave composta).*

A única chave composta do modelo é a da associativa **`T_FOCO_CONDICAO_CLIM`**
(`ID_FOCO, ID_MEDICAO`). Seus atributos não-chave — `DISTANCIA_KM` e `DIF_TEMPO_MIN` —
descrevem a **relação** entre aquele foco e aquela medição específicos, ou seja, dependem da
**chave composta inteira**, não de apenas uma das partes:

- `DISTANCIA_KM` só faz sentido para o par (foco, estação da medição);
- `DIF_TEMPO_MIN` só faz sentido para o par (passagem do foco, hora da medição).

As demais tabelas usam **chave primária simples** (atômica), de modo que dependência parcial
é impossível por definição.

**Conclusão:** o modelo satisfaz a 2FN.

---

## 3. Terceira Forma Normal (3FN)

> *Está em 2FN e não há dependências transitivas: nenhum atributo não-chave depende de outro
> atributo não-chave.*

Atributos que poderiam gerar dependência transitiva foram **extraídos para tabelas-dimensão**:

| Risco de transitividade | Como foi resolvido |
|---|---|
| Nome do bioma repetido em cada foco | `T_BIOMA` (FK `ID_BIOMA` no foco e no desmatamento) |
| Nome/UF/região do estado repetido em municípios e estações | `T_ESTADO`; município/estação guardam só `ID_ESTADO` |
| Nome do satélite e flag de referência repetidos em cada foco | `T_SATELITE` (FK `ID_SATELITE`) |
| Dados da estação (WMO, nome) repetidos em cada medição | `T_ESTACAO_METEOROLOGICA` (FK `ID_ESTACAO`) |
| Coordenadas/altitude da estação ligadas à estação, não à medição | `T_LOCALIZACAO_ESTACAO` (1:1) |

Exemplo de dependência transitiva **evitada**: em `T_ESTADO`, `NM_REGIAO` depende
funcionalmente da UF (chave), não de outro atributo não-chave — portanto é mantido. Já o
nome do estado **não** é repetido dentro de `T_MUNICIPIO`: o município referencia apenas
`ID_ESTADO`, evitando que `NM_ESTADO`/`NM_REGIAO` fossem transitivamente determinados por
`ID_MUNICIPIO`.

**Conclusão:** o modelo satisfaz a 3FN.

---

## 4. Redundâncias deliberadamente evitadas

1. **Texto de domínio repetido.** Biomas, satélites, estados e municípios nunca aparecem
   como *strings* repetidas nas tabelas fato — apenas como **FK numérica**. Isso reduz
   espaço, elimina risco de grafias divergentes ("Amazônia" × "AMAZONIA") e mantém a
   consistência via integridade referencial.

2. **Geolocalização da estação separada (1:1).** `T_LOCALIZACAO_ESTACAO` isola os atributos
   espaciais (lat/lon/altitude). Mantém a estação "limpa" (identidade administrativa) e
   permite evoluir o componente espacial (p.ex. adicionar geometria/SRID) sem alterar a
   tabela principal.

3. **Relação N:N normalizada.** Cada foco pode estar associado a várias medições e vice-versa
   (mesma estação registra muitos focos próximos). A tabela associativa
   `T_FOCO_CONDICAO_CLIM` resolve o N:N **sem duplicar** linhas de foco nem de medição, e
   ainda hospeda os atributos próprios da relação (distância e diferença de tempo).

4. **Desmatamento por (bioma, ano).** `T_DESMATAMENTO_BIOMA` tem `UNIQUE(ID_BIOMA, ANO_PRODES)`,
   impedindo duplicidade de série histórica e mantendo o fato anual independente das tabelas
   de foco.

---

## 5. Desnormalizações controladas (e por que são aceitáveis)

- **Latitude/longitude redundantes em `T_FOCO_CALOR`** além do município: o foco tem
  coordenada **própria e precisa** do ponto detectado, que **não** é igual ao centroide do
  município. Não é redundância — é um dado distinto e essencial para mapas de calor e para o
  grafo de risco (Dynamic Programming).
- **`PRECIPITACAO_MM` no foco** e nas medições climáticas: representam **medidas diferentes**
  (precipitação associada ao foco pelo INPE vs. precipitação horária da estação INMET). São
  grandezas independentes, não cópia uma da outra.

Essas escolhas preservam a integridade da 3FN porque os valores não são funcionalmente
deriváveis um do outro; representam observações distintas de fontes distintas.
