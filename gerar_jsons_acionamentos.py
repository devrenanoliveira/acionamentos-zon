#!/usr/bin/env python3
"""
gerar_jsons_acionamentos.py
Dashboard de Acionamentos — Z-ON Card / Assessorias

Lê Carteira.csv + Acionamentos.csv da mesma pasta e gera:
  • YYYY-MM.json           (KPIs, atraso, valor, matriz, volume, motivos)
  • YYYY-MM-analitico.json (tabela individual compacta)
  • index.json             (lista acumulativa de meses)

Uso:
  1. Coloque este script na mesma pasta que os dois CSVs
  2. Ajuste MES_ID, MES_LABEL, MES_PERIODO abaixo
  3. Execute:  python gerar_jsons_acionamentos.py
  4. Suba os 3 arquivos gerados na pasta data/ do GitHub
"""

import os, sys, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
import pandas as pd

# ================================================================
#  CONFIGURAÇÃO — ajuste antes de rodar a cada mês
# ================================================================
MES_ID      = "2026-08"
MES_LABEL   = "Agosto 2026"
MES_PERIODO = "01–31 ago/2026"
# ================================================================

SCRIPT_DIR = Path(__file__).parent
BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")

# ── Faixas de atraso ────────────────────────────────────────────
FA_LABELS = ["1–30d","31–65d","66–90d","91–120d","121–150d","151–180d","181–360d","361–720d",">720d","Acordo","Sem atraso"]
FA_BREAKS = [30, 65, 90, 120, 150, 180, 360, 720]
FA_ACORDO_IDX     = 9   # índice especial para clientes em acordo (Situação=ativo, Dias=0, saldo>0)
FA_SEM_ATRASO_IDX = 10  # índice especial para clientes sem saldo (quitados/regularizados) — 11/08/2026

# ── Faixas de valor ─────────────────────────────────────────────
FV_LABELS = ["R$0–500","R$500–1k","R$1k–5k","R$5k+"]
FV_BREAKS = [500, 1000, 5000]   # último label captura tudo acima do último break

# ── Códigos de status ───────────────────────────────────────────
STATUS_LABELS = {
    "NL": "Não Localizado",       "NA": "Não Atendeu",
    "AD": "Atendeu e Desligou",   "PP": "Promessa de Pagamento",
    "RC": "Recado",               "SF": "Sem Condições Financeiras",
    "RE": "Reagendado",           "SI": "Sem Interesse",
    "AP": "Alega Pagamento",      "DE": "Desempregado",
    "DD": "Desconhece Dívida",    "FA": "Falecido",
    "SM": "SMS/WhatsApp",
}
TEL_STATUS     = {"NL","NA","AD","PP","RC","SF","RE","SI","AP","DE","DD","FA"}
DIGITAL_STATUS = {"SM"}

# ── Paleta de cores para motivos ────────────────────────────────
MOTIVO_COLORS = {
    "NL": "#6B7280", "NA": "#9CA3AF", "AD": "#EF4444",
    "PP": "#10B981", "RC": "#F59E0B", "SF": "#F97316",
    "RE": "#3B82F6", "SI": "#DC2626", "AP": "#059669",
    "DE": "#8B5CF6", "DD": "#EC4899", "FA": "#1F2937",
    "SM": "#1D4ED8",
}
DEFAULT_COLORS = ["#1D4ED8","#3B82F6","#60A5FA","#7C3AED","#059669",
                  "#10B981","#F59E0B","#EF4444","#6B7280","#EC4899","#F97316","#14B8A6"]


# ================================================================
#  Helpers
# ================================================================
def fa_idx(dias: int) -> int:
    for i, b in enumerate(FA_BREAKS):
        if dias <= b:
            return i
    return len(FA_BREAKS)   # >720d → índice 8

def fv_idx(saldo: float) -> int:
    for i, b in enumerate(FV_BREAKS):
        if saldo <= b:
            return i
    return len(FV_BREAKS)   # última faixa: acima do último break (ex: R$5k+)

def safe_float(v, default=0.0) -> float:
    """Converte número em formato brasileiro (1.234,56) ou americano (1234.56) para float."""
    try:
        s = str(v).strip()
        if ',' in s:
            # Formato BR: ponto = milhar, vírgula = decimal → remove ponto, troca vírgula
            s = s.replace('.', '').replace(',', '.')
        return float(s)
    except Exception:
        return default

def find_col(df: pd.DataFrame, candidates: list):
    """Retorna a primeira coluna que casa com algum candidato (case-insensitive)."""
    norm = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        hit = norm.get(cand.strip().lower())
        if hit:
            return hit
    return None

def fmt_dia(date_str: str) -> str:
    """'2026-08-01' → '01/08'"""
    parts = date_str.split("-")
    return f"{parts[2]}/{parts[1]}" if len(parts) >= 3 else date_str

def is_fds(date_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.weekday() >= 5   # 5=Sáb, 6=Dom
    except Exception:
        return False

def motivo_color(name: str, idx: int) -> str:
    return MOTIVO_COLORS.get(name, DEFAULT_COLORS[idx % len(DEFAULT_COLORS)])


# ================================================================
#  Detectar e carregar CSVs
# ================================================================
print("=" * 62)
print(f"  Dashboard Acionamentos — {MES_LABEL}")
print("=" * 62)

def find_csv(hints: list):
    for p in sorted(SCRIPT_DIR.glob("*.csv")):
        for h in hints:
            if h.lower() in p.name.lower():
                return p
    return None

cart_path  = find_csv(["carteira"])
acion_path = find_csv(["acionamento", "relatorio"])

if not cart_path:
    print("ERRO: Carteira.csv não encontrado na pasta do script.")
    sys.exit(1)
if not acion_path:
    print("ERRO: Acionamentos.csv (ou RELATORIO_*.csv) não encontrado.")
    sys.exit(1)

print(f"\nCarteira:     {cart_path.name}")
print(f"Acionamentos: {acion_path.name}")

print("\n[1/5] Carregando CSVs...")
cart  = pd.read_csv(cart_path,  encoding="utf-8-sig", low_memory=False)
acion = pd.read_csv(acion_path, encoding="utf-8-sig", low_memory=False)
print(f"  Carteira:     {len(cart):,} linhas  | colunas: {list(cart.columns)}")
print(f"  Acionamentos: {len(acion):,} linhas | colunas: {list(acion.columns)}")


# ================================================================
#  [2] Normalizar Carteira
# ================================================================
print("\n[2/5] Normalizando Carteira...")

cpf_c   = find_col(cart, ["cpf/cnpj","cpf","cnpj","documento","cod cliente","codigo","cod_cliente"])
nome_c  = find_col(cart, ["nome","cliente","nome cliente"])
tipo_c  = find_col(cart, ["tipo pessoa","tipo_pessoa","tipo","pessoa"])
ag_c    = find_col(cart, ["agrupador"])
dias_c  = find_col(cart, ["dias","dias em atraso","dias_atraso","dias atraso"])
sc_c    = find_col(cart, ["saldo contábil","saldo_contabil","saldo contabil"])
sta_c   = find_col(cart, ["saldo total em atraso","saldo_total_em_atraso","saldo total atraso"])
sea_c   = find_col(cart, ["saldo em atraso","saldo_em_atraso"])
sat_c   = find_col(cart, ["saldo atual","saldo_atual"])
uf_c    = find_col(cart, ["uf","estado"])
cid_c   = find_col(cart, ["cidade","municipio","município"])
ass_c   = find_col(cart, ["assessorias","assessoria"])
sit_c   = find_col(cart, ["situação","situacao","situação do cliente","situacao_cliente","status cliente","status_cliente"])

print(f"  CPF:{cpf_c}  Nome:{nome_c}  Tipo:{tipo_c}  Agrupador:{ag_c}")
print(f"  Dias:{dias_c}  SC:{sc_c}  STA:{sta_c}  SAT:{sat_c}")
print(f"  UF:{uf_c}  Cidade:{cid_c}  Assessoria(s):{ass_c}  Situação:{sit_c}")

cart["_cpf"]    = cart[cpf_c].astype(str).str.strip() if cpf_c else ""
cart["_nome"]   = cart[nome_c].astype(str).str.strip() if nome_c else ""
cart["_tipo"]   = cart[tipo_c].astype(str).str.strip().str.upper().str[:1] if tipo_c else "F"
cart["_ag"]     = cart[ag_c].astype(str).str.strip() if ag_c else ""
cart["_dias"]   = pd.to_numeric(cart[dias_c], errors="coerce").fillna(0).astype(int) if dias_c else 0
cart["_uf"]     = cart[uf_c].astype(str).str.strip().str.upper() if uf_c else ""
cart["_cidade"] = cart[cid_c].astype(str).str.strip() if cid_c else ""
cart["_as"]     = cart[ass_c].astype(str).str.strip() if ass_c else "—"
cart["_situacao"] = cart[sit_c].astype(str).str.strip().str.lower() if sit_c else ""

def get_saldo(row) -> float:
    for col in [sc_c, sta_c, sea_c, sat_c]:
        if col:
            v = safe_float(row[col])
            if v > 0:
                return v
    return 0.0

cart["_saldo"] = cart.apply(get_saldo, axis=1)

# Deduplicar por CPF: manter linha de maior saldo
cart = (cart
        .sort_values("_saldo", ascending=False)
        .drop_duplicates(subset="_cpf")
        .reset_index(drop=True))

print(f"  → {len(cart):,} clientes únicos após deduplicação por CPF")

# Clientes sem saldo (Saldo Contábil = 0 E Saldo Total em Atraso = 0, etc.) NÃO são mais
# excluídos da carteira (mudança de 11/08/2026) — eles continuam existindo no CobranSaaS e
# podem ter tido acionamento no mês (ex: SMS de cobrança disparado antes da baixa). Excluí-los
# fazia o dashboard subcontar acionamentos reais. Em vez disso, eles entram numa faixa própria
# "Sem atraso" (FA_SEM_ATRASO_IDX) — aparecem normalmente em quantidade, mas como saldo=0,
# não distorcem nenhuma métrica de valor (R$0 somado não altera nenhum total).
# São dois perfis, ambos "sem dívida ativa" hoje: Situação=Ativo → quitaram recentemente;
# Situação=Em Cobrança → nunca tiveram acordo, apenas estão em dia.
n_sem_atraso = int((cart["_saldo"] == 0.0).sum())
print(f"  → {n_sem_atraso:,} clientes com saldo zerado (faixa 'Sem atraso' — quitados/em dia, mantidos na carteira)")
print(f"  → {len(cart):,} clientes na carteira de cobrança")

# Marcar clientes com acordo: Situação="Ativo" + dias=0 + saldo>0
# (agora precisa checar saldo>0 explicitamente, já que clientes com saldo=0 não são mais
# removidos antes desta etapa — sem essa checagem, os quitados "Ativo+dias=0+saldo=0"
# seriam incorretamente classificados como acordo)
cart["_is_acordo"] = (
    (cart["_situacao"] == "ativo") & (cart["_dias"] == 0) & (cart["_saldo"] > 0)
).astype(int)
n_acordos = int(cart["_is_acordo"].sum())
print(f"  → {n_acordos:,} clientes identificados como acordo (Ativo + dias=0 + saldo>0)")

# Índices de faixa — saldo=0 vai para "Sem atraso"; acordos vão para "Acordo" (FA_ACORDO_IDX)
cart["_fa"] = cart.apply(
    lambda r: (FA_SEM_ATRASO_IDX if r["_saldo"] == 0.0
               else (FA_ACORDO_IDX if r["_is_acordo"] else fa_idx(r["_dias"]))),
    axis=1
)
cart["_fv"] = cart["_saldo"].apply(fv_idx)

# Lookups para arrays compactos
ag_list  = sorted(cart["_ag"].unique().tolist())
uf_list  = sorted(cart["_uf"].unique().tolist())
as_list  = sorted(cart["_as"].unique().tolist())
ag_map   = {a: i for i, a in enumerate(ag_list)}
uf_map   = {u: i for i, u in enumerate(uf_list)}
as_map   = {a: i for i, a in enumerate(as_list)}

cart["_ag_idx"] = cart["_ag"].map(ag_map).fillna(0).astype(int)
cart["_uf_idx"] = cart["_uf"].map(uf_map).fillna(0).astype(int)
cart["_as_idx"] = cart["_as"].map(as_map).fillna(0).astype(int)

print(f"  Assessorias na carteira: {as_list}")


# ================================================================
#  [3] Normalizar Acionamentos
# ================================================================
print("\n[3/5] Normalizando Acionamentos...")

cpf_a    = find_col(acion, ["cpf/cnpj","cpf","cnpj","documento","cod cliente","codigo","cod_cliente","cliente"])
acao_a   = find_col(acion, ["ação","acao","tipo acao","tipo_acao","canal","tipo de acao"])
# Prioridade: "Motivo Contato" (resultado real) antes de "Tipo Motivo" (útil/não útil)
motivo_a = find_col(acion, ["motivo contato","motivo_contato",
                             "tipo motivo","tipo_motivo",
                             "motivo","cod motivo","cod_motivo","situação","situacao"])
data_a   = find_col(acion, ["data"])
ass_a    = find_col(acion, ["assessoria"])

print(f"  CPF:{cpf_a}  Ação:{acao_a}  Motivo:{motivo_a}  Data:{data_a}  Assessoria:{ass_a}")

acion["_cpf"]    = acion[cpf_a].astype(str).str.strip() if cpf_a else ""
acion["_acao"]   = acion[acao_a].astype(str).str.strip().str.upper() if acao_a else ""
acion["_motivo"] = acion[motivo_a].astype(str).str.strip() if motivo_a else ""
acion["_as"]     = acion[ass_a].astype(str).str.strip() if ass_a else "—"

if data_a:
    acion["_data"] = pd.to_datetime(acion[data_a], errors="coerce", dayfirst=True)
else:
    acion["_data"] = pd.NaT

# Classificar canal (telefônico = contato telefônico; demais = digital/WhatsApp)
acion["_is_tel"] = acion["_acao"].str.contains(r"TEL|CONTATO", na=False, regex=True)

# Filtrar apenas CPFs que estão na carteira
cart_cpfs   = set(cart["_cpf"])
acion_valid = acion[acion["_cpf"].isin(cart_cpfs)].copy()
print(f"  → {len(acion):,} acionamentos  |  {len(acion_valid):,} de clientes na carteira")


# ================================================================
#  calc_block — gera bloco de métricas para um subset
#  Retorna estrutura EXATA esperada pelo HTML (sem normalização extra)
# ================================================================
def calc_block(df_c: pd.DataFrame, df_a: pd.DataFrame) -> dict:
    c = df_c.copy()
    a = df_a[df_a["_cpf"].isin(set(c["_cpf"]))].copy()

    n_total    = len(c)
    n_acionado = int(c["_acionado"].sum())
    n_nao      = n_total - n_acionado
    # Promessas: desde que o motivo passou a vir da coluna "Motivo Contato" (texto
    # completo, ex: "Promessa de Pagamento"), a comparação não pode mais ser pelo
    # código de 2 letras ("PP") — senão nunca bate e "com_promessa" fica sempre 0.
    n_pp       = int(c["_ultimo"].astype(str).str.strip().str.lower()
                      .str.contains("promessa", na=False).sum())
    n_total_a  = len(a)                              # total de acionamentos (linhas)

    # ── Atraso ──────────────────────────────────────────────────
    atraso = []
    for fi, fl in enumerate(FA_LABELS):
        fc  = c[c["_fa"] == fi]
        ft  = len(fc)
        fn  = int((~fc["_acionado"]).sum())
        fs  = round(float(fc["_saldo"].sum()), 2)
        atraso.append({
            "label": fl,
            "total": ft,                                              # ← "total" (não "tot")
            "acion": ft - fn,
            "nao":   fn,
            "pct":   round((ft - fn) / ft * 100, 1) if ft else 0.0,
            "saldo": fs,
        })

    # ── Valor ────────────────────────────────────────────────────
    valor = []
    for vi, vl in enumerate(FV_LABELS):
        vc  = c[c["_fv"] == vi]
        vt  = len(vc)
        vn  = int((~vc["_acionado"]).sum())
        vs  = round(float(vc["_saldo"].sum()), 2)
        valor.append({
            "label": vl,
            "total": vt,
            "acion": vt - vn,
            "nao":   vn,
            "pct":   round((vt - vn) / vt * 100, 1) if vt else 0.0,
            "saldo": vs,
        })

    # ── Matriz 2D [fa_idx][fv_idx] = [nao, total] ───────────────
    grp = (c.groupby(["_fa", "_fv"])
            .agg(tot=("_cpf", "count"), acion_sum=("_acionado", "sum"))
            .reset_index())
    matrix = [[list([0, 0]) for _ in range(len(FV_LABELS))] for _ in range(len(FA_LABELS))]
    for _, r in grp.iterrows():
        fi, vi = int(r["_fa"]), int(r["_fv"])
        if 0 <= fi < len(FA_LABELS) and 0 <= vi < len(FV_LABELS):
            tot = int(r["tot"])
            nao = tot - int(r["acion_sum"])
            matrix[fi][vi] = [nao, tot]

    max_nao = max(
        (cell[0] for row in matrix for cell in row if cell[1] > 0),
        default=0
    )

    # ── Frequência: [{n:"0x", v:N}, ...] ────────────────────────
    freq_labels = ["0x","1x","2x","3x","4x","5x+"]
    freq_data   = [0] * 6
    for v in c["_qtd"]:
        freq_data[min(int(v), 5)] += 1
    freq = [{"n": l, "v": v} for l, v in zip(freq_labels, freq_data)]

    # ── Volume diário: [{dia:"DD/MM", digital:N, tel:N, fds:bool, pm:{motivo:[digital,tel]}}]
    # "pm" (por motivo) permite ao dashboard filtrar o volume diário por
    # Canal/Motivo — sem isso o filtro só conseguia atuar sobre o total
    # agregado do dia (digital/tel), nunca sobre um motivo específico.
    volume = []
    if len(a) and a["_data"].notna().any():
        a_dated = a[a["_data"].notna()].copy()
        a_dated["_ds"] = a_dated["_data"].dt.strftime("%Y-%m-%d")
        vol_grp = a_dated.groupby(["_ds", "_is_tel"]).size().reset_index(name="cnt")
        vol_dict: dict = defaultdict(lambda: {"digital": 0, "tel": 0})
        for _, r in vol_grp.iterrows():
            d = r["_ds"]
            if r["_is_tel"]:
                vol_dict[d]["tel"] += int(r["cnt"])
            else:
                vol_dict[d]["digital"] += int(r["cnt"])

        pm_grp = (a_dated[a_dated["_motivo"].astype(str).str.strip() != ""]
                  .groupby(["_ds", "_motivo", "_is_tel"]).size().reset_index(name="cnt"))
        pm_dict: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for _, r in pm_grp.iterrows():
            d, mot = r["_ds"], r["_motivo"]
            idx = 1 if r["_is_tel"] else 0
            pm_dict[d][mot][idx] += int(r["cnt"])

        volume = [
            {
                "dia": fmt_dia(d), "digital": v["digital"], "tel": v["tel"], "fds": is_fds(d),
                "pm": {mot: cnts for mot, cnts in pm_dict.get(d, {}).items()},
            }
            for d, v in sorted(vol_dict.items())
        ]

    total_tel = sum(d["tel"] for d in volume)

    # ── Motivos: [{name, value, color}] ──────────────────────────
    # Usa TODOS os acionamentos (todos os canais) para cobrir
    # todos os valores possíveis de "Motivo Contato" no filtro do dashboard
    mot_cnt = a["_motivo"].value_counts()
    motivos = [
        {
            "name":  cod,
            "value": int(cnt),
            "color": motivo_color(cod, i),
        }
        for i, (cod, cnt) in enumerate(mot_cnt.items())
        if cod and cod.strip() and cod.upper() != "NAN"
    ]

    return {
        # KPIs globais
        "total_clientes":     n_total,
        "acionados":          n_acionado,
        "sem_acionamento":    n_nao,
        "com_promessa":       n_pp,
        "total_acionamentos": n_total_a,
        "total_tel":          total_tel,
        "max_nao":            max_nao,
        # Blocos de dados
        "atraso":   atraso,
        "valor":    valor,
        "matrix":   matrix,
        "freq":     freq,
        "volume":   volume,
        "motivos":  motivos,
    }


# ================================================================
#  [4] Calcular métricas
# ================================================================
print("\n[4/5] Calculando métricas...")

# Estatísticas por cliente
acion_cnt = acion_valid.groupby("_cpf").size().rename("_qtd")

if acion_valid["_data"].notna().any():
    ultimo_st = (acion_valid
                 .sort_values("_data")
                 .groupby("_cpf")["_motivo"]
                 .last()
                 .rename("_ultimo"))
else:
    ultimo_st = acion_valid.groupby("_cpf")["_motivo"].last().rename("_ultimo")

freq_st = (acion_valid
           .groupby("_cpf")["_motivo"]
           .agg(lambda x: x.value_counts().index[0] if len(x) else "")
           .rename("_freq_st"))

# Contagem de acionamentos por canal (telefônico vs digital) por cliente
tel_cnt = (acion_valid[acion_valid["_is_tel"]]
           .groupby("_cpf").size()
           .rename("_qtd_tel"))

cart = (cart
        .join(acion_cnt,  on="_cpf")
        .join(ultimo_st,  on="_cpf")
        .join(freq_st,    on="_cpf")
        .join(tel_cnt,    on="_cpf"))
cart["_qtd"]      = cart["_qtd"].fillna(0).astype(int)
cart["_qtd_tel"]  = cart["_qtd_tel"].fillna(0).astype(int)
cart["_ultimo"]   = cart["_ultimo"].fillna("").astype(str)
cart["_freq_st"]  = cart["_freq_st"].fillna("").astype(str)
cart["_acionado"] = cart["_qtd"] > 0

total     = len(cart)
acionados = int(cart["_acionado"].sum())
cobertura = round(acionados / total * 100, 1) if total else 0
print(f"  Total: {total:,} | Acionados: {acionados:,} | Não: {total-acionados:,} | Cobertura: {cobertura}%")

# Bloco global
bloco_global = calc_block(cart, acion_valid)

# Blocos por assessoria (re-keyed por índice numérico)
#
# IMPORTANTE: os acionamentos são filtrados pela coluna "Assessoria" do próprio
# Acionamentos.csv (quem efetivamente FEZ o contato), não apenas pelo CPF do cliente.
# Isso é proposital: quando um cliente migra de assessoria (ex: Fácil → PG+/Decisão),
# o histórico de acionamento antigo dele continua tagueado com a assessoria que
# REALMENTE fez aquele contato. Filtrar só por CPF creditaria à nova assessoria
# (PG+/Decisão) o trabalho que a assessoria anterior (Fácil) já tinha feito antes
# da migração — testado e descartado em 11/08/2026 após comparação com os CSVs
# brutos (PG+ tem só 61 linhas "PG+" no Acionamentos.csv; o resto do histórico dos
# clientes hoje em PG+/Decisão pertence à Fácil).
by_assessoria: dict = {}
if len(as_list) > 1:
    for idx, ass in enumerate(as_list):
        c_sub = cart[cart["_as"] == ass].copy()
        a_sub = acion_valid[acion_valid["_as"] == ass].copy()

        # Recalcular _qtd e _acionado exclusivamente para esta assessoria
        cnt_sub = a_sub.groupby("_cpf").size().rename("_qtd_s")
        c_sub   = c_sub.join(cnt_sub, on="_cpf")
        c_sub["_qtd"]      = c_sub["_qtd_s"].fillna(0).astype(int)
        c_sub["_acionado"] = c_sub["_qtd"] > 0
        c_sub = c_sub.drop(columns=["_qtd_s"], errors="ignore")

        bloco = calc_block(c_sub, a_sub)
        by_assessoria[str(idx)] = bloco          # ← chave = String(índice)

        n  = bloco["total_clientes"]
        ac = bloco["acionados"]
        print(f"    [{idx}] {ass}: {n:,} clientes | {ac:,} acionados ({round(ac/n*100,1) if n else 0}%)")


# ================================================================
#  Montar YYYY-MM.json
# ================================================================
mes_json: dict = {
    # Meta (campos lidos diretamente pelo HTML)
    "periodo":            MES_PERIODO,
    "atualizado_em":      HOJE,
    # Listas de lookup (nomes de chave que o HTML usa)
    "assessoria_list":    as_list,
    "ag_list":            ag_list,
    "uf_list":            uf_list,
    "fa_labels":          FA_LABELS,
    "fv_labels":          FV_LABELS,
    "status_label":       STATUS_LABELS,
    # KPIs globais (espalhados no nível raiz)
    **bloco_global,
    # Acordos — para o dashboard poder excluí-los das métricas de cobertura
    "n_acordos": n_acordos,
    "fa_acordo_idx": FA_ACORDO_IDX,
    # Sem atraso (saldo zerado — quitados/em dia) — sempre visível em quantidade,
    # nunca distorce valor (saldo=0)
    "n_sem_atraso": n_sem_atraso,
    "fa_sem_atraso_idx": FA_SEM_ATRASO_IDX,
}
if by_assessoria:
    mes_json["by_assessoria"] = by_assessoria


# ================================================================
#  Montar YYYY-MM-analitico.json
#  Array plano — formato lido diretamente por ANALITICO.filter(...)
#  [CPF, Nome, Tipo, Dias, fa_idx, Saldo, fv_idx,
#   ag_idx, uf_idx, Cidade, QtdAcion, UltimoStatus, StatusFreq, as_idx, is_acordo, QtdTel]
# ================================================================
print("  Montando analítico...")
rows = []
for _, r in cart.iterrows():
    rows.append([
        str(r["_cpf"]),                     # 0  CPF/CNPJ
        str(r["_nome"]),                    # 1  Nome
        str(r["_tipo"]),                    # 2  Tipo (F/J)
        int(r["_dias"]),                    # 3  Dias em atraso
        int(r["_fa"]),                      # 4  fa_idx  (inteiro)
        round(float(r["_saldo"]), 2),       # 5  Saldo
        int(r["_fv"]),                      # 6  fv_idx  (inteiro)
        int(r["_ag_idx"]),                  # 7  ag_idx
        int(r["_uf_idx"]),                  # 8  uf_idx
        str(r["_cidade"]),                  # 9  Cidade
        int(r["_qtd"]),                     # 10 Qtd acionamentos
        str(r["_ultimo"]),                  # 11 Último status
        str(r["_freq_st"]),                 # 12 Status mais frequente
        int(r["_as_idx"]),                  # 13 as_idx
        int(r["_is_acordo"]),               # 14 is_acordo (1=acordo, 0=normal)
        int(r["_qtd_tel"]),                 # 15 qtd_tel  (acionamentos telefônicos)
    ])

print(f"  → {len(rows):,} registros no analítico")


# ================================================================
#  Atualizar index.json (preserva histórico)
# ================================================================
idx_path = SCRIPT_DIR / "index.json"
if idx_path.exists():
    with open(idx_path, "r", encoding="utf-8") as f:
        idx_data = json.load(f)
    print(f"  index.json existente: {len(idx_data.get('meses', []))} mês(es)")
else:
    idx_data = {"meses": []}

idx_data["meses"] = [m for m in idx_data["meses"] if m.get("id") != MES_ID]
idx_data["meses"].insert(0, {
    "id":      MES_ID,
    "label":   MES_LABEL,
    "periodo": MES_PERIODO,
    "total":        bloco_global["total_clientes"],
    "acionados":    bloco_global["acionados"],
    "cobertura_pct": round(bloco_global["acionados"] / bloco_global["total_clientes"] * 100, 1)
                     if bloco_global["total_clientes"] else 0,
})


# ================================================================
#  [5] Salvar JSONs
# ================================================================
print(f"\n[5/5] Salvando JSONs em {SCRIPT_DIR}...")

mes_path      = SCRIPT_DIR / f"{MES_ID}.json"
analitico_path = SCRIPT_DIR / f"{MES_ID}-analitico.json"

with open(mes_path, "w", encoding="utf-8") as f:
    json.dump(mes_json, f, ensure_ascii=False, separators=(",", ":"))
print(f"  ✓ {mes_path.name:<38} {mes_path.stat().st_size / 1024:>6.0f} KB")

with open(analitico_path, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))   # array plano
print(f"  ✓ {analitico_path.name:<38} {analitico_path.stat().st_size / 1024:>6.0f} KB")

with open(idx_path, "w", encoding="utf-8") as f:
    json.dump(idx_data, f, ensure_ascii=False, indent=2)
print(f"  ✓ index.json{' ':27} {idx_path.stat().st_size / 1024:>6.0f} KB  ({len(idx_data['meses'])} mês(es))")

print(f"""
{'='*62}
  ✅  Concluído!

  Suba estes 3 arquivos na pasta data/ do GitHub:
    • {mes_path.name}
    • {analitico_path.name}
    • index.json

  GitHub Pages atualiza em ~1 minuto após o commit.
{'='*62}
""")
