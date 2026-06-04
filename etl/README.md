# ETL — Carga dos dados reais

**Disciplina:** Database Design · **Grupo:** Stratfy (FIAP GS 2026.1)
Sistema de Detecção de Incêndios Florestais.

Este ETL ingere os dados públicos reais de 2025 (INPE BDQueimadas, INMET BDMEP, INPE PRODES,
IBGE), gera os comandos `INSERT` do banco e **valida** a carga executando o DDL e os inserts
em um banco SQLite-espelho, encerrando com 5 consultas analíticas.

---

## 1. Pré-requisitos

- **Python 3.9+** (testado em 3.13).
- Apenas a **biblioteca padrão** é necessária para o fluxo principal:
  `csv`, `json`, `sqlite3`, `re`, `os`, `sys`, `datetime`.
- Os CSVs reais devem estar em `build/dados-preparados/` (padrão) ou, como fallback, na
  pasta `dados/` deste repositório (já incluída).

Para a conexão **opcional** com Oracle:

```bash
pip install oracledb
```

---

## 2. Como rodar

```bash
cd build/repos/database/etl
python carga.py
```

Saídas geradas:

| Artefato | Descrição |
|---|---|
| `sql/insercoes_dados_reais.sql` | INSERTs reais para Oracle (gerado/atualizado a cada execução) |
| `deteccao_incendios.sqlite` | Banco-espelho de validação (recriado a cada execução) |
| *(stdout)* | 5 consultas analíticas de verificação |

O script é **idempotente**: cada execução recria o `.sql` e o `.sqlite` a partir das fontes,
sem efeitos colaterais acumulados.

---

## 3. O que o ETL faz, passo a passo

1. **Leitura** dos CSVs (`build/dados-preparados/` ou `dados/`).
2. **Limpeza:** converte o sentinela `-999 → NULL`; normaliza datas/timestamps; trata
   campos vazios; mapeia siglas de UF e nomes de bioma para os IDs do modelo.
3. **Amostragem:** focos limitados a **~2.000** linhas (amostragem sistemática ao longo de
   todo o ano, preservando a sazonalidade real) e medições a **~1.000** linhas, para manter
   o `.sql` leve. **O DDL e o mirror suportam o volume completo** — basta aumentar
   `MAX_FOCOS` / `MAX_MEDICOES` no topo de `carga.py`.
4. **Geração** de `insercoes_dados_reais.sql` na ordem correta de dependência (biomas →
   estados → satélites → municípios → focos → estações → localizações → medições →
   associativa N:N → desmatamento).
5. **Validação em SQLite:** traduz o DDL Oracle (tipos `NUMBER/VARCHAR2/TIMESTAMP` →
   `INTEGER/REAL/TEXT`, remove `SEQUENCE`/`COMMENT`) e os inserts
   (`TO_TIMESTAMP`/`TO_DATE` → literais), aplica com `PRAGMA foreign_keys = ON` e **aborta
   se houver qualquer violação de integridade**.
6. **Consultas analíticas (5):**
   - Q1 — contagem de registros por tabela (sanidade da carga);
   - Q2 — focos por bioma com risco e FRP médios;
   - Q3 — top UFs por número de focos (esperado: MATOPIBA + arco);
   - Q4 — desmatamento PRODES 2025 × focos por bioma;
   - Q5 — condição climática associada aos focos (junção da associativa N:N).

---

## 4. Conexão opcional com Oracle (`oracledb`)

Não há instância Oracle obrigatória para a validação (feita via SQLite). Caso queira
carregar em um Oracle real, o trecho abaixo é o caminho recomendado — basta executar os
dois arquivos `.sql` já gerados:

```python
import oracledb

# Thin mode (não requer Oracle Instant Client):
conn = oracledb.connect(
    user="SEU_USUARIO",
    password="SUA_SENHA",
    dsn="localhost:1521/XEPDB1",   # host:porta/serviço
)
cur = conn.cursor()

def executar_arquivo(caminho):
    with open(caminho, "r", encoding="utf-8") as fh:
        conteudo = fh.read()
    # separa por ';' simples (os arquivos não usam blocos PL/SQL)
    for stmt in conteudo.split(";"):
        s = stmt.strip()
        if not s or s.startswith("--"):
            continue
        cur.execute(s)
    conn.commit()

executar_arquivo("../sql/deteccao_incendios_oracle.sql")
executar_arquivo("../sql/insercoes_dados_reais.sql")

cur.execute("""
    SELECT b.NM_BIOMA, COUNT(*) 
      FROM T_FOCO_CALOR f JOIN T_BIOMA b ON b.ID_BIOMA = f.ID_BIOMA
     GROUP BY b.NM_BIOMA ORDER BY 2 DESC
""")
for nome, total in cur.fetchall():
    print(nome, total)

cur.close()
conn.close()
```

> Dica: no Oracle, o arquivo de DDL já dá `COMMIT` ao final dos inserts de exemplo. Ao
> carregar `insercoes_dados_reais.sql` por cima, use as tabelas vazias (há um bloco de
> `DELETE` comentado no topo do arquivo de inserts) para evitar conflito de chave primária
> com a amostra ilustrativa do DDL.

---

## 5. Estrutura dos dados-fonte

Ver `build/dados-preparados/MANIFESTO.md` para o schema completo de cada CSV. Resumo:

| CSV | Tabela(s)-alvo |
|---|---|
| `estados_ibge.csv` | `T_ESTADO` |
| `municipios_ibge.csv` + `focos_municipios_agg.csv` | `T_MUNICIPIO` |
| `focos_amostra.csv` | `T_FOCO_CALOR`, `T_SATELITE`, `T_BIOMA` |
| `estacoes_inmet.csv` | `T_ESTACAO_METEOROLOGICA`, `T_LOCALIZACAO_ESTACAO` |
| `medicoes_amostra.csv` | `T_MEDICAO_CLIMATICA` |
| `prodes_desmatamento_biomas_2025.csv` | `T_DESMATAMENTO_BIOMA` |
| (derivado focos × medições) | `T_FOCO_CONDICAO_CLIM` |
