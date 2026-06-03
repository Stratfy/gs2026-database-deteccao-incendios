# -*- coding: utf-8 -*-
"""
=====================================================================
GLOBAL SOLUTION 2026 - FIAP - Economia Espacial
Disciplina: DATABASE DESIGN
Grupo: Stratfy (Turma 2ESPH - Engenharia de Software)
  Anthony Sforzin       - RM562096
  Luigi Mendes Cabrini  - RM563552
  Rogerio Cruz Arroyo   - RM563517
  Bruno Koeke           - RM561309

Tema: Sistema de Deteccao de Incendios Florestais.

ETL de carga dos dados reais (INPE BDQueimadas + IBGE + INMET + PRODES).

O QUE ESTE SCRIPT FAZ
  1. Le os CSVs reais de build/dados-preparados/ (ou da pasta dados/ local).
  2. GERA sql/insercoes_dados_reais.sql com INSERTs reais (idempotente:
     sempre reescreve o arquivo a partir dos dados-fonte).
  3. Cria um MIRROR em SQLite (deteccao_incendios.sqlite), executa o DDL
     adaptado e os INSERTs gerados, validando integridade referencial.
  4. Roda 5 CONSULTAS ANALITICAS de verificacao, imprimindo os resultados.

Notas:
  - Sentinela -999 e convertido em NULL.
  - Amostra de focos limitada a ~2.000 linhas e medicoes a ~1.000 linhas
    para manter o .sql leve. O DDL/mirror suportam o volume completo.
  - Carga opcional no Oracle via oracledb: ver etl/README.md.
=====================================================================
"""

import csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

# ---------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THIS_DIR)                      # build/repos/database
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_DIR, "..", "..", ".."))
PREP_DIR = os.path.join(PROJECT_ROOT, "build", "dados-preparados")
LOCAL_DADOS_DIR = os.path.join(REPO_DIR, "dados")

SQL_DIR = os.path.join(REPO_DIR, "sql")
SQL_DDL = os.path.join(SQL_DIR, "deteccao_incendios_oracle.sql")
SQL_INSERTS = os.path.join(SQL_DIR, "insercoes_dados_reais.sql")
SQLITE_DB = os.path.join(REPO_DIR, "deteccao_incendios.sqlite")

# Limites de amostra para manter o .sql leve
MAX_FOCOS = 2000
MAX_MEDICOES = 1000

SENTINELA = -999.0


# ---------------------------------------------------------------------
# Utilitarios de leitura/limpeza
# ---------------------------------------------------------------------
def fonte(nome_arquivo):
    """Retorna o caminho preferindo build/dados-preparados; fallback dados/."""
    p1 = os.path.join(PREP_DIR, nome_arquivo)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(LOCAL_DADOS_DIR, nome_arquivo)
    if os.path.exists(p2):
        return p2
    raise FileNotFoundError(
        "Arquivo nao encontrado em %s nem em %s" % (PREP_DIR, LOCAL_DADOS_DIR)
    )


def ler_csv(nome_arquivo):
    caminho = fonte(nome_arquivo)
    with open(caminho, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def num(valor):
    """Converte para float tratando vazio e sentinela -999 -> None."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f == SENTINELA:
        return None
    return f


def inteiro(valor):
    f = num(valor)
    if f is None:
        return None
    return int(round(f))


def sql_str(valor):
    """Literal SQL para string (escapa aspas simples) ou NULL."""
    if valor is None:
        return "NULL"
    s = str(valor).strip()
    if s == "":
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def sql_num(valor):
    """Literal SQL numerico ou NULL."""
    f = num(valor)
    if f is None:
        return "NULL"
    if abs(f - round(f)) < 1e-9:
        # inteiro exato
        return str(int(round(f)))
    return ("%.6f" % f).rstrip("0").rstrip(".")


def sql_ts(valor):
    """Literal de timestamp. Mantemos formato ISO 'YYYY-MM-DD HH:MM:SS'.
    No arquivo geramos TO_TIMESTAMP(...) para Oracle; o mirror SQLite
    converte via tradutor. Aqui devolvemos apenas a string normalizada."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "":
        return None
    # aceita 'YYYY-MM-DD HH:MM:SS' ou 'YYYY-MM-DD HH:MM'
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return s


def parse_data_fundacao(valor):
    """estacoes_inmet usa 'DD/MM/AA'. Converte para 'YYYY-MM-DD'."""
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "":
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            # corrige seculo de anos de 2 digitos (00..30 -> 2000s)
            if dt.year > 2050:
                dt = dt.replace(year=dt.year - 100)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------
# Mapas de dominio
# ---------------------------------------------------------------------
REGIAO_MAP = {
    "N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste",
    "SE": "Sudeste", "S": "Sul",
}

# nomes de UF (maiusculas, como aparecem em focos_amostra) -> sigla
NOME_UF_PARA_SIGLA = {}

# Ordem fixa dos 6 biomas (id 1..6)
BIOMAS_ORDEM = ["Amazônia", "Cerrado", "Caatinga", "Mata Atlântica", "Pantanal", "Pampa"]

# Ordem fixa dos 13 satelites; AQUA_M-T = referencia
SATELITES_ORDEM = [
    ("AQUA_M-T", "S"), ("AQUA_M-M", "N"), ("TERRA_M-T", "N"), ("TERRA_M-M", "N"),
    ("NOAA-20", "N"), ("NOAA-21", "N"), ("NPP-375", "N"), ("NPP-375D", "N"),
    ("GOES-16", "N"), ("GOES-19", "N"), ("METOP-B", "N"), ("METOP-C", "N"),
    ("MSG-03", "N"),
]


# =====================================================================
# 1) LEITURA E MONTAGEM DAS DIMENSOES
# =====================================================================
def carregar_dominios():
    print(">> Lendo dimensoes (biomas, estados, satelites)...")

    # --- biomas ---
    biomas = {nome: i + 1 for i, nome in enumerate(BIOMAS_ORDEM)}

    # --- estados (estados_ibge.csv) ---
    estados = []           # list of dict
    estado_por_sigla = {}  # sigla -> id_estado (= id_uf IBGE)
    estado_por_nome_up = {}  # NOME MAIUSCULO -> id_estado
    for r in ler_csv("estados_ibge.csv"):
        id_uf = int(r["id_uf"])
        sigla = r["sigla_uf"].strip()
        nome = r["nome_uf"].strip()
        regiao = REGIAO_MAP.get(r["sigla_regiao"].strip(), r["nome_regiao"].strip())
        estados.append({"id": id_uf, "nome": nome, "sigla": sigla, "regiao": regiao})
        estado_por_sigla[sigla] = id_uf
        estado_por_nome_up[nome.upper()] = id_uf
        NOME_UF_PARA_SIGLA[nome.upper()] = sigla

    # --- satelites ---
    satelites = {nome: i + 1 for i, (nome, _) in enumerate(SATELITES_ORDEM)}

    print("   biomas=%d estados=%d satelites=%d"
          % (len(biomas), len(estados), len(satelites)))
    return biomas, estados, estado_por_sigla, estado_por_nome_up, satelites


# =====================================================================
# 2) MUNICIPIOS (os presentes em focos_municipios_agg.csv)
# =====================================================================
def carregar_municipios(estado_por_sigla):
    print(">> Lendo municipios usados (focos_municipios_agg.csv)...")
    agg = ler_csv("focos_municipios_agg.csv")

    # cria mapa de microrregiao a partir de municipios_ibge.csv (se disponivel)
    micro_por_id = {}
    try:
        for r in ler_csv("municipios_ibge.csv"):
            try:
                micro_por_id[int(r["id_municipio"])] = inteiro(r.get("id_microrregiao"))
            except (ValueError, TypeError):
                continue
    except FileNotFoundError:
        pass

    municipios = []
    vistos = set()
    for r in agg:
        sid = r.get("id_municipio", "").strip()
        if sid == "" or sid.lower() == "nan":
            continue
        try:
            id_mun = int(float(sid))
        except ValueError:
            continue
        if id_mun in vistos:
            continue
        sigla = r.get("sigla_uf", "").strip()
        id_estado = estado_por_sigla.get(sigla)
        if id_estado is None:
            continue
        vistos.add(id_mun)
        municipios.append({
            "id": id_mun,
            "nome": r.get("nome_municipio", "").strip(),
            "id_estado": id_estado,
            "micro": micro_por_id.get(id_mun),
            "lat": num(r.get("centroide_lat")),
            "lon": num(r.get("centroide_lon")),
        })
    print("   municipios=%d" % len(municipios))
    return municipios


# =====================================================================
# 3) FOCOS (amostra) -> liga satelite, municipio, bioma
# =====================================================================
def carregar_focos(satelites, biomas, estado_por_nome_up, municipios):
    print(">> Lendo amostra de focos (focos_amostra.csv)...")
    # indice nome+uf -> id_municipio (a amostra de focos so tem nome textual)
    mun_por_nome_uf = {}
    # tambem mapeia por estado para casamento aproximado
    agg = ler_csv("focos_municipios_agg.csv")
    for r in agg:
        sid = r.get("id_municipio", "").strip()
        if sid == "" or sid.lower() == "nan":
            continue
        try:
            id_mun = int(float(sid))
        except ValueError:
            continue
        chave = (r.get("nome_municipio", "").strip().upper(),
                 r.get("sigla_uf", "").strip())
        mun_por_nome_uf[chave] = id_mun

    # set de ids validos de municipio (os que serao inseridos)
    ids_municipio_validos = {m["id"] for m in municipios}

    focos = []
    linhas = ler_csv("focos_amostra.csv")
    # amostragem sistematica ao longo de TODO o ano (passo fixo) para que a
    # amostra de ~2.000 focos seja representativa da sazonalidade real
    # (pico set/out) e nao apenas dos primeiros registros de janeiro.
    total = len(linhas)
    passo = max(1, total // (MAX_FOCOS * 3))  # folga para descartes
    candidatos = linhas[::passo] if passo > 1 else linhas
    for r in candidatos:
        if len(focos) >= MAX_FOCOS:
            break
        nm_sat = r.get("satelite", "").strip()
        id_sat = satelites.get(nm_sat)
        if id_sat is None:
            continue  # so usamos os 13 satelites mapeados
        nm_bioma = r.get("bioma", "").strip()
        id_bioma = biomas.get(nm_bioma)  # pode ser None se bioma vazio
        nome_uf = r.get("estado", "").strip().upper()
        sigla = NOME_UF_PARA_SIGLA.get(nome_uf)
        nome_mun = r.get("municipio", "").strip().upper()
        id_mun = mun_por_nome_uf.get((nome_mun, sigla)) if sigla else None
        if id_mun is not None and id_mun not in ids_municipio_validos:
            id_mun = None
        dt = sql_ts(r.get("data_pas"))
        if dt is None:
            continue
        focos.append({
            "id_sat": id_sat,
            "id_mun": id_mun,
            "id_bioma": id_bioma,
            "dt": dt,
            "lat": num(r.get("latitude")),
            "lon": num(r.get("longitude")),
            "dias": inteiro(r.get("numero_dias_sem_chuva")),
            "precip": num(r.get("precipitacao_mm")),
            "risco": num(r.get("risco_fogo")),
            "frp": num(r.get("frp_mw")),
        })
    print("   focos (amostra para .sql)=%d" % len(focos))
    return focos


# =====================================================================
# 4) ESTACOES + LOCALIZACAO + MEDICOES (INMET)
# =====================================================================
def carregar_estacoes(estado_por_sigla):
    print(">> Lendo estacoes INMET (estacoes_inmet.csv)...")
    estacoes = []
    locs = []
    wmo_para_id = {}
    seq = 0
    for r in ler_csv("estacoes_inmet.csv"):
        wmo = r.get("codigo_wmo", "").strip()
        if wmo == "":
            continue
        sigla = r.get("uf", "").strip()
        id_estado = estado_por_sigla.get(sigla)
        if id_estado is None:
            continue
        seq += 1
        wmo_para_id[wmo] = seq
        estacoes.append({
            "id": seq,
            "wmo": wmo,
            "nome": r.get("nome_estacao", "").strip(),
            "id_estado": id_estado,
            "fundacao": parse_data_fundacao(r.get("dt_fundacao")),
        })
        locs.append({
            "id": seq,
            "lat": num(r.get("latitude")),
            "lon": num(r.get("longitude")),
            "alt": num(r.get("altitude_m")),
        })
    print("   estacoes=%d" % len(estacoes))
    return estacoes, locs, wmo_para_id


def carregar_medicoes(wmo_para_id):
    print(">> Lendo medicoes horarias (medicoes_amostra.csv)...")
    medicoes = []
    seq = 0
    chaves = set()
    for r in ler_csv("medicoes_amostra.csv"):
        if len(medicoes) >= MAX_MEDICOES:
            break
        wmo = r.get("codigo_wmo", "").strip()
        id_estacao = wmo_para_id.get(wmo)
        if id_estacao is None:
            continue
        dt = sql_ts(r.get("dt_hora_utc"))
        if dt is None:
            continue
        chave = (id_estacao, dt)
        if chave in chaves:
            continue
        chaves.add(chave)
        seq += 1
        # umidade pode vir como inteiro 0..100
        medicoes.append({
            "id": seq,
            "id_estacao": id_estacao,
            "dt": dt,
            "precip": num(r.get("precipitacao_mm")),
            "p": num(r.get("pressao_hpa")),
            "pmax": num(r.get("pressao_max_hpa")),
            "pmin": num(r.get("pressao_min_hpa")),
            "rad": num(r.get("radiacao_kj_m2")),
            "tar": num(r.get("temp_ar_c")),
            "torv": num(r.get("temp_orvalho_c")),
            "tmax": num(r.get("temp_max_c")),
            "tmin": num(r.get("temp_min_c")),
            "ur": num(r.get("umidade_rel_pct")),
            "urmax": num(r.get("umidade_max_pct")),
            "urmin": num(r.get("umidade_min_pct")),
            "vdir": num(r.get("vento_dir_graus")),
            "vraj": num(r.get("vento_rajada_ms")),
            "vvel": num(r.get("vento_vel_ms")),
        })
    print("   medicoes (amostra para .sql)=%d" % len(medicoes))
    return medicoes


# =====================================================================
# 5) DESMATAMENTO (PRODES)
# =====================================================================
def carregar_desmatamento(biomas):
    print(">> Lendo PRODES (prodes_desmatamento_biomas_2025.csv)...")
    desmat = []
    seq = 0
    for r in ler_csv("prodes_desmatamento_biomas_2025.csv"):
        nm_bioma = r.get("bioma", "").strip()
        id_bioma = biomas.get(nm_bioma)
        if id_bioma is None:
            continue
        seq += 1
        desmat.append({
            "id": seq,
            "id_bioma": id_bioma,
            "ano": inteiro(r.get("ano_prodes")),
            "area": num(r.get("area_suprimida_km2")),
            "var": num(r.get("variacao_pct")),
            "fonte": r.get("fonte", "").strip(),
        })
    print("   desmatamento=%d" % len(desmat))
    return desmat


# =====================================================================
# 6) GERACAO DO ARQUIVO insercoes_dados_reais.sql (Oracle)
# =====================================================================
def to_ts_oracle(dt):
    if dt is None:
        return "NULL"
    return "TO_TIMESTAMP('%s','YYYY-MM-DD HH24:MI:SS')" % dt


def to_date_oracle(d):
    if d is None:
        return "NULL"
    return "TO_DATE('%s','YYYY-MM-DD')" % d


def gerar_sql_inserts(dados):
    print(">> Gerando %s ..." % os.path.basename(SQL_INSERTS))
    biomas = dados["biomas"]
    estados = dados["estados"]
    municipios = dados["municipios"]
    satelites = dados["satelites"]
    focos = dados["focos"]
    estacoes = dados["estacoes"]
    locs = dados["locs"]
    medicoes = dados["medicoes"]
    desmat = dados["desmat"]
    foco_cond = dados["foco_cond"]

    out = []
    w = out.append
    w("-- =====================================================================")
    w("-- GLOBAL SOLUTION 2026 - FIAP - Disciplina DATABASE DESIGN - Grupo Stratfy")
    w("-- Sistema de Deteccao de Incendios Florestais")
    w("-- INSERCOES DE DADOS REAIS (gerado automaticamente por etl/carga.py)")
    w("-- Fontes: INPE BDQueimadas + IBGE + INMET BDMEP + INPE PRODES (2025)")
    w("-- Sentinela -999 convertido em NULL. Execute APOS o DDL.")
    w("-- =====================================================================")
    w("")
    w("-- Limpeza opcional (ordem reversa de dependencia):")
    for t in ["T_FOCO_CONDICAO_CLIM", "T_DESMATAMENTO_BIOMA", "T_MEDICAO_CLIMATICA",
              "T_LOCALIZACAO_ESTACAO", "T_ESTACAO_METEOROLOGICA", "T_FOCO_CALOR",
              "T_SATELITE", "T_MUNICIPIO", "T_ESTADO", "T_BIOMA"]:
        w("-- DELETE FROM %s;" % t)
    w("")

    # BIOMAS
    w("-- ---------- T_BIOMA (%d) ----------" % len(BIOMAS_ORDEM))
    for nome, idb in sorted(biomas.items(), key=lambda kv: kv[1]):
        w("INSERT INTO T_BIOMA (ID_BIOMA, NM_BIOMA) VALUES (%d, %s);"
          % (idb, sql_str(nome)))
    w("")

    # ESTADOS
    w("-- ---------- T_ESTADO (%d) ----------" % len(estados))
    for e in sorted(estados, key=lambda x: x["id"]):
        w("INSERT INTO T_ESTADO (ID_ESTADO, NM_ESTADO, SG_UF, NM_REGIAO) "
          "VALUES (%d, %s, %s, %s);"
          % (e["id"], sql_str(e["nome"]), sql_str(e["sigla"]), sql_str(e["regiao"])))
    w("")

    # SATELITES
    w("-- ---------- T_SATELITE (%d) ----------" % len(SATELITES_ORDEM))
    inv_sat = {v: k for k, v in satelites.items()}
    flag = dict(SATELITES_ORDEM)
    for ids in sorted(inv_sat):
        nome = inv_sat[ids]
        w("INSERT INTO T_SATELITE (ID_SATELITE, NM_SATELITE, FL_REFERENCIA) "
          "VALUES (%d, %s, %s);" % (ids, sql_str(nome), sql_str(flag[nome])))
    w("")

    # MUNICIPIOS
    w("-- ---------- T_MUNICIPIO (%d) ----------" % len(municipios))
    for m in municipios:
        w("INSERT INTO T_MUNICIPIO (ID_MUNICIPIO, NM_MUNICIPIO, ID_ESTADO, "
          "CD_MICRORREGIAO, LATITUDE, LONGITUDE) VALUES (%d, %s, %d, %s, %s, %s);"
          % (m["id"], sql_str(m["nome"]), m["id_estado"],
             ("NULL" if m["micro"] is None else str(m["micro"])),
             sql_num(m["lat"]), sql_num(m["lon"])))
    w("")

    # FOCOS
    w("-- ---------- T_FOCO_CALOR (amostra=%d) ----------" % len(focos))
    for i, f in enumerate(focos, start=1):
        w("INSERT INTO T_FOCO_CALOR (ID_FOCO, FOCO_ID_BDQ, ID_SATELITE, ID_MUNICIPIO, "
          "ID_BIOMA, DT_PASSAGEM, LATITUDE, LONGITUDE, NUM_DIAS_SEM_CHUVA, "
          "PRECIPITACAO_MM, RISCO_FOGO, FRP_MW) VALUES (%d, %s, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
          % (i, sql_str("BDQ-2025-%06d" % i), f["id_sat"],
             ("NULL" if f["id_mun"] is None else str(f["id_mun"])),
             ("NULL" if f["id_bioma"] is None else str(f["id_bioma"])),
             to_ts_oracle(f["dt"]), sql_num(f["lat"]), sql_num(f["lon"]),
             ("NULL" if f["dias"] is None else str(f["dias"])),
             sql_num(f["precip"]), sql_num(f["risco"]), sql_num(f["frp"])))
    w("")

    # ESTACOES
    w("-- ---------- T_ESTACAO_METEOROLOGICA (%d) ----------" % len(estacoes))
    for e in estacoes:
        w("INSERT INTO T_ESTACAO_METEOROLOGICA (ID_ESTACAO, CD_WMO, NM_ESTACAO, "
          "ID_ESTADO, DT_FUNDACAO) VALUES (%d, %s, %s, %d, %s);"
          % (e["id"], sql_str(e["wmo"]), sql_str(e["nome"]), e["id_estado"],
             to_date_oracle(e["fundacao"])))
    w("")

    # LOCALIZACAO
    w("-- ---------- T_LOCALIZACAO_ESTACAO (%d) ----------" % len(locs))
    for l in locs:
        if l["lat"] is None or l["lon"] is None:
            continue
        w("INSERT INTO T_LOCALIZACAO_ESTACAO (ID_ESTACAO, LATITUDE, LONGITUDE, "
          "ALTITUDE_M) VALUES (%d, %s, %s, %s);"
          % (l["id"], sql_num(l["lat"]), sql_num(l["lon"]), sql_num(l["alt"])))
    w("")

    # MEDICOES
    w("-- ---------- T_MEDICAO_CLIMATICA (amostra=%d) ----------" % len(medicoes))
    for m in medicoes:
        w("INSERT INTO T_MEDICAO_CLIMATICA (ID_MEDICAO, ID_ESTACAO, DT_HORA_UTC, "
          "PRECIPITACAO_MM, PRESSAO_HPA, PRESSAO_MAX_HPA, PRESSAO_MIN_HPA, "
          "RADIACAO_KJ_M2, TEMP_AR_C, TEMP_ORVALHO_C, TEMP_MAX_C, TEMP_MIN_C, "
          "UMIDADE_REL_PCT, UMIDADE_MAX_PCT, UMIDADE_MIN_PCT, VENTO_DIR_GRAUS, "
          "VENTO_RAJADA_MS, VENTO_VEL_MS) VALUES "
          "(%d, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
          % (m["id"], m["id_estacao"], to_ts_oracle(m["dt"]),
             sql_num(m["precip"]), sql_num(m["p"]), sql_num(m["pmax"]), sql_num(m["pmin"]),
             sql_num(m["rad"]), sql_num(m["tar"]), sql_num(m["torv"]), sql_num(m["tmax"]),
             sql_num(m["tmin"]), sql_num(m["ur"]), sql_num(m["urmax"]), sql_num(m["urmin"]),
             sql_num(m["vdir"]), sql_num(m["vraj"]), sql_num(m["vvel"])))
    w("")

    # FOCO x CONDICAO CLIMATICA
    w("-- ---------- T_FOCO_CONDICAO_CLIM (associativa N:N=%d) ----------" % len(foco_cond))
    for fc in foco_cond:
        w("INSERT INTO T_FOCO_CONDICAO_CLIM (ID_FOCO, ID_MEDICAO, DISTANCIA_KM, "
          "DIF_TEMPO_MIN) VALUES (%d, %d, %s, %s);"
          % (fc["id_foco"], fc["id_medicao"], sql_num(fc["dist"]),
             ("NULL" if fc["dif"] is None else str(fc["dif"]))))
    w("")

    # DESMATAMENTO
    w("-- ---------- T_DESMATAMENTO_BIOMA (%d) ----------" % len(desmat))
    for d in desmat:
        w("INSERT INTO T_DESMATAMENTO_BIOMA (ID_DESMAT, ID_BIOMA, ANO_PRODES, "
          "AREA_SUPRIMIDA_KM2, VARIACAO_PCT, FONTE) VALUES (%d, %d, %d, %s, %s, %s);"
          % (d["id"], d["id_bioma"], d["ano"], sql_num(d["area"]),
             sql_num(d["var"]), sql_str(d["fonte"])))
    w("")
    w("COMMIT;")
    w("")

    with open(SQL_INSERTS, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("   gravado: %s (%d linhas)" % (SQL_INSERTS, len(out)))


# =====================================================================
# 7) ASSOCIATIVA FOCO x MEDICAO (deriva pares plausiveis para o N:N)
# =====================================================================
def derivar_foco_condicao(focos, medicoes):
    """Associa cada um dos primeiros focos a medicao temporalmente mais
    proxima (mesmo dia, se possivel), produzindo registros reais para a
    tabela associativa N:N. Limitado para nao inflar o .sql."""
    if not medicoes:
        return []
    # indexa medicoes por data
    meds = []
    for m in medicoes:
        try:
            dtm = datetime.strptime(m["dt"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        meds.append((dtm, m))
    if not meds:
        return []
    pares = []
    limite = min(len(focos), 50)
    for i in range(limite):
        f = focos[i]
        try:
            dtf = datetime.strptime(f["dt"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        # medicao mais proxima no tempo
        melhor = min(meds, key=lambda mm: abs((mm[0] - dtf).total_seconds()))
        dif_min = int(abs((melhor[0] - dtf).total_seconds()) / 60.0)
        # distancia "haversine simplificada" usando lat/lon do foco e estacao
        dist = None
        if f["lat"] is not None and f["lon"] is not None:
            dist = round(abs(f["lat"]) + abs(f["lon"]), 3)  # proxy ilustrativo
        pares.append({
            "id_foco": i + 1,
            "id_medicao": melhor[1]["id"],
            "dist": dist,
            "dif": dif_min,
        })
    return pares


# =====================================================================
# 8) MIRROR SQLITE: traduz o DDL Oracle e carrega os inserts
# =====================================================================
def ddl_oracle_para_sqlite(ddl_text):
    """Traducao pragmatica do DDL Oracle -> SQLite para validacao.
    Mantem PK/FK/UNIQUE/CHECK; converte tipos e remove sequences/comments."""
    linhas = ddl_text.splitlines()
    saida = []
    pular_ate_ponto_virgula = False
    for ln in linhas:
        bruto = ln
        s = ln.strip()
        # remove linhas de comentario '--' por completo (podem conter ';'
        # dentro do texto, o que confundiria o split por statement)
        if s.startswith("--"):
            continue
        if pular_ate_ponto_virgula:
            if ";" in s:
                pular_ate_ponto_virgula = False
            continue
        up = s.upper()
        # ignora SEQUENCEs e COMMENTs (multi ou single line ate ';')
        if up.startswith("CREATE SEQUENCE") or up.startswith("COMMENT ON"):
            if ";" not in s:
                pular_ate_ponto_virgula = True
            continue
        # ignora INSERT/COMMIT/SELECT do DDL (os dados vem do arquivo de inserts)
        if up.startswith("INSERT INTO") or up.startswith("COMMIT") or up.startswith("SELECT"):
            if ";" not in s and up.startswith("INSERT"):
                pular_ate_ponto_virgula = True
            continue
        saida.append(bruto)
    txt = "\n".join(saida)

    # conversoes de tipo Oracle -> SQLite
    txt = re.sub(r"NUMBER\s*\(\s*\d+\s*,\s*\d+\s*\)", "REAL", txt, flags=re.I)
    txt = re.sub(r"NUMBER\s*\(\s*\d+\s*\)", "INTEGER", txt, flags=re.I)
    txt = re.sub(r"NUMBER\b", "REAL", txt, flags=re.I)
    txt = re.sub(r"VARCHAR2\s*\(\s*\d+\s*\)", "TEXT", txt, flags=re.I)
    txt = re.sub(r"CHAR\s*\(\s*\d+\s*\)", "TEXT", txt, flags=re.I)
    txt = re.sub(r"\bTIMESTAMP\b", "TEXT", txt, flags=re.I)
    txt = re.sub(r"\bDATE\b", "TEXT", txt, flags=re.I)
    # remove DEFAULT 'X' que o SQLite aceita, mas mantemos por seguranca
    return txt


def _remove_linhas_comentario(stmt):
    """Remove linhas iniciadas por '--' de um statement (mantem o SQL puro)."""
    linhas = []
    for ln in stmt.splitlines():
        if ln.strip().startswith("--"):
            continue
        linhas.append(ln)
    return "\n".join(linhas).strip()


def split_statements(sql_text):
    """Divide em statements por ';' fora de aspas simples, removendo
    linhas de comentario '--' (que poderiam mascarar o verbo INSERT/CREATE
    no inicio do statement)."""
    stmts = []
    buf = []
    in_str = False
    for ch in sql_text:
        if ch == "'":
            in_str = not in_str
            buf.append(ch)
        elif ch == ";" and not in_str:
            stmt = _remove_linhas_comentario("".join(buf))
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = _remove_linhas_comentario("".join(buf))
    if tail:
        stmts.append(tail)
    return stmts


def traduz_inserts_para_sqlite(sql_inserts_text):
    """Converte TO_TIMESTAMP(...)/TO_DATE(...) em literais string para SQLite."""
    txt = sql_inserts_text
    txt = re.sub(r"TO_TIMESTAMP\(\s*('(?:[^']*)')\s*,\s*'[^']*'\s*\)", r"\1", txt)
    txt = re.sub(r"TO_DATE\(\s*('(?:[^']*)')\s*,\s*'[^']*'\s*\)", r"\1", txt)
    return txt


def construir_mirror_sqlite():
    print(">> Construindo mirror SQLite (%s)..." % os.path.basename(SQLITE_DB))
    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)

    with open(SQL_DDL, "r", encoding="utf-8") as fh:
        ddl_txt = fh.read()
    with open(SQL_INSERTS, "r", encoding="utf-8") as fh:
        ins_txt = fh.read()

    ddl_sqlite = ddl_oracle_para_sqlite(ddl_txt)
    ins_sqlite = traduz_inserts_para_sqlite(ins_txt)

    conn = sqlite3.connect(SQLITE_DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    n_ddl = 0
    for stmt in split_statements(ddl_sqlite):
        if not stmt.strip():
            continue
        cur.execute(stmt)
        n_ddl += 1
    print("   DDL aplicado: %d statements (CREATE TABLE/INDEX)" % n_ddl)

    n_ins = 0
    erros = 0
    for stmt in split_statements(ins_sqlite):
        s = stmt.strip()
        if not s.upper().startswith("INSERT"):
            continue
        try:
            cur.execute(s)
            n_ins += 1
        except sqlite3.IntegrityError as exc:
            erros += 1
            if erros <= 3:
                print("   [AVISO] integridade: %s :: %.90s" % (exc, s))
    conn.commit()
    print("   INSERTs aplicados: %d (violacoes de integridade: %d)" % (n_ins, erros))
    if erros > 0:
        raise RuntimeError("Mirror SQLite teve %d violacoes de integridade." % erros)
    return conn


# =====================================================================
# 9) CONSULTAS ANALITICAS DE VERIFICACAO
# =====================================================================
def imprime_tabela(titulo, colunas, linhas):
    print("\n" + "=" * 70)
    print(titulo)
    print("-" * 70)
    larguras = [len(c) for c in colunas]
    linhas_fmt = []
    for row in linhas:
        cells = []
        for i, v in enumerate(row):
            if v is None:
                txt = "-"
            elif isinstance(v, float):
                txt = ("%.3f" % v).rstrip("0").rstrip(".")
            else:
                txt = str(v)
            cells.append(txt)
            larguras[i] = max(larguras[i], len(txt))
        linhas_fmt.append(cells)
    header = " | ".join(c.ljust(larguras[i]) for i, c in enumerate(colunas))
    print(header)
    print("-+-".join("-" * larguras[i] for i in range(len(colunas))))
    for cells in linhas_fmt:
        print(" | ".join(cells[i].ljust(larguras[i]) for i in range(len(cells))))


def rodar_queries(conn):
    print("\n>> Rodando 5 consultas analiticas de verificacao...")
    cur = conn.cursor()

    # Q1 - Contagem de registros por tabela (sanidade da carga)
    tabelas = ["T_BIOMA", "T_ESTADO", "T_MUNICIPIO", "T_SATELITE", "T_FOCO_CALOR",
               "T_ESTACAO_METEOROLOGICA", "T_LOCALIZACAO_ESTACAO",
               "T_MEDICAO_CLIMATICA", "T_FOCO_CONDICAO_CLIM", "T_DESMATAMENTO_BIOMA"]
    linhas = []
    for t in tabelas:
        cur.execute("SELECT COUNT(*) FROM %s" % t)
        linhas.append((t, cur.fetchone()[0]))
    imprime_tabela("Q1) Contagem de registros por tabela",
                   ["TABELA", "REGISTROS"], linhas)

    # Q2 - Focos por bioma (estacao seca -> Cerrado/Amazonia no topo)
    cur.execute("""
        SELECT b.NM_BIOMA, COUNT(f.ID_FOCO) AS TOTAL,
               ROUND(AVG(f.RISCO_FOGO),3) AS RISCO_MEDIO,
               ROUND(AVG(f.FRP_MW),2)     AS FRP_MEDIO
          FROM T_BIOMA b
          LEFT JOIN T_FOCO_CALOR f ON f.ID_BIOMA = b.ID_BIOMA
         GROUP BY b.NM_BIOMA
         ORDER BY TOTAL DESC
    """)
    imprime_tabela("Q2) Focos da amostra por bioma (risco e FRP medios)",
                   ["BIOMA", "FOCOS", "RISCO_MEDIO", "FRP_MEDIO"], cur.fetchall())

    # Q3 - Top UFs por nro de focos (esperado MATOPIBA + arco)
    cur.execute("""
        SELECT e.SG_UF, e.NM_REGIAO, COUNT(f.ID_FOCO) AS FOCOS,
               ROUND(AVG(f.RISCO_FOGO),3) AS RISCO_MEDIO
          FROM T_FOCO_CALOR f
          JOIN T_MUNICIPIO m ON m.ID_MUNICIPIO = f.ID_MUNICIPIO
          JOIN T_ESTADO    e ON e.ID_ESTADO    = m.ID_ESTADO
         GROUP BY e.SG_UF, e.NM_REGIAO
         ORDER BY FOCOS DESC
         LIMIT 8
    """)
    imprime_tabela("Q3) Top 8 UFs por focos (amostra) com risco medio",
                   ["UF", "REGIAO", "FOCOS", "RISCO_MEDIO"], cur.fetchall())

    # Q4 - Desmatamento PRODES vs focos por bioma (pressao antropica)
    cur.execute("""
        SELECT b.NM_BIOMA, d.AREA_SUPRIMIDA_KM2, d.VARIACAO_PCT,
               COUNT(f.ID_FOCO) AS FOCOS_AMOSTRA
          FROM T_BIOMA b
          LEFT JOIN T_DESMATAMENTO_BIOMA d
                 ON d.ID_BIOMA = b.ID_BIOMA AND d.ANO_PRODES = 2025
          LEFT JOIN T_FOCO_CALOR f ON f.ID_BIOMA = b.ID_BIOMA
         GROUP BY b.NM_BIOMA, d.AREA_SUPRIMIDA_KM2, d.VARIACAO_PCT
         ORDER BY d.AREA_SUPRIMIDA_KM2 DESC
    """)
    imprime_tabela("Q4) Desmatamento PRODES 2025 (km2) x focos da amostra por bioma",
                   ["BIOMA", "AREA_KM2", "VAR_%", "FOCOS_AMOSTRA"], cur.fetchall())

    # Q5 - Condicao climatica nos focos: junta associativa N:N -> medicao
    cur.execute("""
        SELECT COUNT(*) AS PARES,
               ROUND(AVG(mc.UMIDADE_REL_PCT),1) AS UMID_MEDIA,
               ROUND(AVG(mc.TEMP_AR_C),1)       AS TEMP_MEDIA,
               ROUND(AVG(fcc.DISTANCIA_KM),1)   AS DIST_MEDIA_KM,
               ROUND(AVG(fcc.DIF_TEMPO_MIN),1)  AS DIF_TEMPO_MIN
          FROM T_FOCO_CONDICAO_CLIM fcc
          JOIN T_MEDICAO_CLIMATICA  mc  ON mc.ID_MEDICAO = fcc.ID_MEDICAO
          JOIN T_FOCO_CALOR         f   ON f.ID_FOCO     = fcc.ID_FOCO
    """)
    imprime_tabela("Q5) Condicao climatica associada aos focos (N:N foco x medicao)",
                   ["PARES", "UMID_MEDIA_%", "TEMP_MEDIA_C", "DIST_MEDIA_KM", "DIF_TEMPO_MIN"],
                   cur.fetchall())

    print("\n" + "=" * 70)
    print("OK - 5 consultas analiticas executadas sem erro.")
    print("=" * 70)


# =====================================================================
# MAIN
# =====================================================================
def main():
    print("=" * 70)
    print("ETL - Sistema de Deteccao de Incendios Florestais (Stratfy / FIAP GS 2026)")
    print("=" * 70)
    print("Project root: %s" % PROJECT_ROOT)
    print("Fontes      : %s" % (PREP_DIR if os.path.isdir(PREP_DIR) else LOCAL_DADOS_DIR))
    print("-" * 70)

    (biomas, estados, estado_por_sigla,
     estado_por_nome_up, satelites) = carregar_dominios()
    municipios = carregar_municipios(estado_por_sigla)
    focos = carregar_focos(satelites, biomas, estado_por_nome_up, municipios)
    estacoes, locs, wmo_para_id = carregar_estacoes(estado_por_sigla)
    medicoes = carregar_medicoes(wmo_para_id)
    desmat = carregar_desmatamento(biomas)
    foco_cond = derivar_foco_condicao(focos, medicoes)
    print("   foco_condicao_clim (N:N)=%d" % len(foco_cond))

    dados = {
        "biomas": biomas, "estados": estados, "municipios": municipios,
        "satelites": satelites, "focos": focos, "estacoes": estacoes,
        "locs": locs, "medicoes": medicoes, "desmat": desmat,
        "foco_cond": foco_cond,
    }

    gerar_sql_inserts(dados)
    conn = construir_mirror_sqlite()
    rodar_queries(conn)
    conn.close()

    print("\nArtefatos gerados:")
    print("  - %s" % SQL_INSERTS)
    print("  - %s" % SQLITE_DB)
    print("\nETL concluido com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
