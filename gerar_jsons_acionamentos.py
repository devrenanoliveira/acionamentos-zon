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

import os, sys, json, re, unicodedata
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

# ── Novas dimensões da Carteira (20/08/2026) ────────────────────
# Gênero — direto da coluna "Sexo" (100% preenchido, 2 valores)
SEXO_LABELS = ["Feminino", "Masculino", "Não informado"]

# Faixa etária — bucketizada a partir da coluna "Idade" ("49 anos" → 49)
IDADE_LABELS = ["18–25", "26–35", "36–45", "46–55", "56–65", "66+", "Não informado"]
IDADE_BREAKS = [25, 35, 45, 55, 65]

# Faixa de renda — bucketizada a partir de "Renda Titular" (R$1.000 a R$50.000 na base)
RENDA_LABELS = ["até R$1.500", "R$1.500–3.000", "R$3.000–5.000", "R$5.000–10.000", "R$10.000+", "Não informado"]
RENDA_BREAKS = [1500, 3000, 5000, 10000]

# Faixa de Score Fatura — reaproveita as bandas OFICIAIS já documentadas nas
# instruções do projeto (Score Fatura 0–999), não uma régua nova
SCORE_LABELS = [
    "0–200 (Alto Risco)", "201–300 (Risco Elevado)", "301–400 (Risco Moderado)",
    "401–500 (Potencial)", "501–600 (Bom)", "601–700 (Ótimo)",
    "701–800 (Excelente)", "801–999 (Premium)", "Sem Score",
]
SCORE_BREAKS = [200, 300, 400, 500, 600, 700, 800]

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

def sexo_idx(v) -> int:
    s = str(v).strip().lower()
    if s.startswith("fem"):
        return 0
    if s.startswith("mas"):
        return 1
    return 2   # Não informado

def idade_idx(idade) -> int:
    if idade is None:
        return len(IDADE_LABELS) - 1   # Não informado
    for i, b in enumerate(IDADE_BREAKS):
        if idade <= b:
            return i
    return len(IDADE_BREAKS)   # 66+

def renda_idx(renda) -> int:
    if renda is None:
        return len(RENDA_LABELS) - 1   # Não informado
    for i, b in enumerate(RENDA_BREAKS):
        if renda <= b:
            return i
    return len(RENDA_BREAKS)   # R$10.000+

def score_idx(score) -> int:
    if score is None:
        return len(SCORE_LABELS) - 1   # Sem Score (último label)
    for i, b in enumerate(SCORE_BREAKS):
        if score <= b:
            return i
    return len(SCORE_BREAKS)   # 801–999 (Premium) — mesmo padrão de fa_idx/fv_idx

def norm_catprof(v) -> str:
    """Normaliza Categoria Profissão — corrige mojibake pontual visto na base
    (ex: 'Aut??nomo' → 'Autônomo', 1 caso em 69k linhas) sem tocar nas demais."""
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return "Não Informado"
    low = s.lower().replace("?", "")
    if low == "autnomo":
        return "Autônomo"
    return s

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


def _norm(s):
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


# Colunas exclusivas de cada relatório — identifica o CSV pelo cabeçalho quando
# o arquivo vem com o nome genérico de exportação do sistema (RELATORIO_<id>.csv),
# sem precisar renomear manualmente. Confirmado 25/08/2026 contra os cabeçalhos
# reais (score 4/4 no próprio tipo, 0 nos outros — ver motor_zon.py, mesma lógica).
_ASSINATURAS_CSV = {
    "carteira":     ["score fatura", "rating", "renda titular", "maior atraso"],
    "acionamentos": ["motivo contato", "tipo motivo", "data inclusao", "responsavel"],
}


def _identificar_tipo_csv(path):
    try:
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                with open(path, encoding=enc) as f:
                    primeira = f.readline()
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
    except OSError:
        return None
    sep = ";" if primeira.count(";") > primeira.count(",") else ","
    header_txt = " | ".join(_norm(c) for c in primeira.split(sep))
    melhor_tipo, melhor_score = None, 0
    for tipo, chaves in _ASSINATURAS_CSV.items():
        score = sum(1 for k in chaves if k in header_txt)
        if score > melhor_score:
            melhor_tipo, melhor_score = tipo, score
    return melhor_tipo if melhor_score >= 2 else None


def find_csv_por_conteudo(tipo, hints_nome: list):
    """Identifica o CSV pelo cabeçalho (não depende de rename manual); só cai
    pro casamento por nome do arquivo se o conteúdo não resolver sem ambiguidade."""
    candidatos = sorted(SCRIPT_DIR.glob("*.csv"))
    achados = [p for p in candidatos if _identificar_tipo_csv(p) == tipo]
    if len(achados) == 1:
        return achados[0]
    if len(achados) > 1:
        print(f"AVISO: {len(achados)} arquivos com cabeçalho de '{tipo}' "
              f"encontrados ({[p.name for p in achados]}) — usando o mais "
              f"recente por data de modificação.")
        return sorted(achados, key=lambda p: p.stat().st_mtime)[-1]
    return find_csv(hints_nome)


cart_path  = find_csv_por_conteudo("carteira", ["carteira"])
acion_path = find_csv_por_conteudo("acionamentos", ["acionamento", "relatorio"])

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
# Novas dimensões da Carteira (20/08/2026) — todas opcionais: se a coluna não
# existir no CSV daquele mês, o cliente cai no bucket "Não informado"/"Sem Score"
# em vez de quebrar o script (mesmo padrão de tolerância do find_col em geral).
sexo_c    = find_col(cart, ["sexo","gênero","genero"])
idade_c   = find_col(cart, ["idade"])
catprof_c = find_col(cart, ["categoria profissão","categoria profissao","categoria_profissao"])
renda_c   = find_col(cart, ["renda titular","renda_titular","renda"])
score_c   = find_col(cart, ["score fatura","score_fatura","score"])

print(f"  CPF:{cpf_c}  Nome:{nome_c}  Tipo:{tipo_c}  Agrupador:{ag_c}")
print(f"  Dias:{dias_c}  SC:{sc_c}  STA:{sta_c}  SAT:{sat_c}")
print(f"  UF:{uf_c}  Cidade:{cid_c}  Assessoria(s):{ass_c}  Situação:{sit_c}")
print(f"  Sexo:{sexo_c}  Idade:{idade_c}  Cat.Profissão:{catprof_c}  Renda:{renda_c}  Score:{score_c}")

cart["_cpf"]    = cart[cpf_c].astype(str).str.strip() if cpf_c else ""
cart["_nome"]   = cart[nome_c].astype(str).str.strip() if nome_c else ""
cart["_tipo"]   = cart[tipo_c].astype(str).str.strip().str.upper().str[:1] if tipo_c else "F"
cart["_ag"]     = cart[ag_c].astype(str).str.strip() if ag_c else ""
cart["_dias"]   = pd.to_numeric(cart[dias_c], errors="coerce").fillna(0).astype(int) if dias_c else 0
cart["_uf"]     = cart[uf_c].astype(str).str.strip().str.upper() if uf_c else ""
cart["_cidade"] = cart[cid_c].astype(str).str.strip() if cid_c else ""
cart["_as"]     = cart[ass_c].astype(str).str.strip() if ass_c else "—"
cart["_situacao"] = cart[sit_c].astype(str).str.strip().str.lower() if sit_c else ""

# Novas dimensões (20/08/2026)
cart["_sexo"] = cart[sexo_c].astype(str).str.strip() if sexo_c else ""
if idade_c:
    cart["_idade"] = pd.to_numeric(
        cart[idade_c].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    )
else:
    cart["_idade"] = pd.Series([None] * len(cart))
cart["_catprof"] = cart[catprof_c].apply(norm_catprof) if catprof_c else "Não Informado"
cart["_renda"] = cart[renda_c].apply(lambda v: safe_float(v, None) if pd.notna(v) else None) if renda_c else pd.Series([None] * len(cart))
cart["_score"] = pd.to_numeric(cart[score_c], errors="coerce") if score_c else pd.Series([None] * len(cart))

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

# ── Índices das novas dimensões (20/08/2026) ────────────────────
cart["_sexo_idx"]  = cart["_sexo"].apply(sexo_idx)
cart["_idade_idx"] = cart["_idade"].apply(lambda v: idade_idx(None if pd.isna(v) else float(v)))
cart["_renda_idx"] = cart["_renda"].apply(lambda v: renda_idx(None if v is None or pd.isna(v) else float(v)))
cart["_score_idx"] = cart["_score"].apply(lambda v: score_idx(None if pd.isna(v) else float(v)))

# Categoria Profissão — lista dinâmica (13 categorias reais na base atual),
# ordenada por volume decrescente pra ficar mais legível nos gráficos/tabelas
catprof_counts = cart["_catprof"].value_counts()
catprof_list   = catprof_counts.index.tolist()
catprof_map    = {c: i for i, c in enumerate(catprof_list)}
cart["_catprof_idx"] = cart["_catprof"].map(catprof_map).fillna(0).astype(int)

# ── Colaborador (funcionário do Grupo Zonta) — cruzamento por CPF ──
# Novo em 21/08/2026, a pedido do usuário: identificar quais clientes da
# carteira de cobrança são também colaboradores do grupo, para uma campanha
# de cobrança interna. Cruzamento feito SÓ por CPF — nenhum outro campo da
# planilha de RH (salário, data de nascimento) é usado ou exposto no
# dashboard. Arquivo é OPCIONAL: se não estiver na pasta, a marcação fica
# zerada para todo mundo e o resto do script roda normalmente (mesmo padrão
# de tolerância já usado pro Collection Score sem scikit-learn).
def norm_cpf(v) -> str:
    s = re.sub(r"\D", "", str(v)) if v is not None else ""
    return s.zfill(11) if s else ""

colab_path = None
for p in sorted(SCRIPT_DIR.glob("*.xlsx")):
    if "colaborador" in p.name.lower():
        colab_path = p
        break

colab_map = {}   # cpf_norm -> (filial, cargo)
if colab_path:
    try:
        colab_df = pd.read_excel(colab_path, engine="openpyxl")
        cpf_col    = find_col(colab_df, ["numcpf", "cpf", "cpf/cnpj"])
        filial_col = find_col(colab_df, ["nomfil", "filial", "nome filial"])
        cargo_col  = find_col(colab_df, ["titred", "cargo", "titulo reduzido"])
        if not cpf_col:
            print(f"  ⚠ Colaboradores: {colab_path.name} não tem coluna de CPF reconhecível "
                  f"({list(colab_df.columns)}) — marcação de colaborador fica zerada.")
        else:
            colab_df["_cpf_norm"] = colab_df[cpf_col].apply(norm_cpf)
            colab_df = colab_df[colab_df["_cpf_norm"] != ""].drop_duplicates(subset="_cpf_norm")
            for _, row in colab_df.iterrows():
                colab_map[row["_cpf_norm"]] = (
                    str(row[filial_col]).strip() if filial_col and pd.notna(row[filial_col]) else "",
                    str(row[cargo_col]).strip()  if cargo_col  and pd.notna(row[cargo_col])  else "",
                )
            print(f"  Colaboradores: {colab_path.name} — {len(colab_map):,} CPFs distintos carregados "
                  f"(Filial:{filial_col}  Cargo:{cargo_col})")
    except Exception as e:
        print(f"  ⚠ Falha ao ler planilha de colaboradores ({colab_path.name}): {e} "
              f"— marcação de colaborador fica zerada.")
        colab_map = {}
else:
    print("  (nenhuma planilha de colaboradores — nome do arquivo precisa conter "
          "\"colaborador\" — encontrada na pasta; marcação de colaborador fica zerada, "
          "não bloqueia a geração dos outros JSONs)")

cart["_cpf_norm"]       = cart["_cpf"].apply(norm_cpf)
cart["_is_funcionario"] = cart["_cpf_norm"].map(lambda c: 1 if c in colab_map else 0)
cart["_filial"] = cart["_cpf_norm"].map(lambda c: colab_map.get(c, ("", ""))[0])
cart["_cargo"]  = cart["_cpf_norm"].map(lambda c: colab_map.get(c, ("", ""))[1])

filial_list = sorted(cart.loc[cart["_is_funcionario"] == 1, "_filial"].unique().tolist())
filial_map  = {f: i for i, f in enumerate(filial_list)}
cargo_list  = sorted(cart.loc[cart["_is_funcionario"] == 1, "_cargo"].unique().tolist())
cargo_map   = {c: i for i, c in enumerate(cargo_list)}

cart["_filial_idx"] = cart.apply(
    lambda r: filial_map.get(r["_filial"], -1) if r["_is_funcionario"] == 1 else -1, axis=1)
cart["_cargo_idx"] = cart.apply(
    lambda r: cargo_map.get(r["_cargo"], -1) if r["_is_funcionario"] == 1 else -1, axis=1)

n_funcionarios = int(cart["_is_funcionario"].sum())
saldo_funcionarios = round(float(cart.loc[cart["_is_funcionario"] == 1, "_saldo"].sum()), 2)
print(f"  → {n_funcionarios:,} clientes da carteira identificados como colaborador "
      f"(saldo total R$ {saldo_funcionarios:,.2f})")


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
#  calc_dim — breakdown genérico de uma dimensão categórica
#  (mesmo formato usado por "atraso"/"valor": label/total/acion/nao/pct/saldo)
#  Usada pelas novas dimensões da Carteira (Gênero, Faixa Etária,
#  Categoria Profissão, Faixa de Renda, Score Fatura, Carteira Interna)
# ================================================================
def calc_dim(df_c: pd.DataFrame, idx_col: str, labels: list) -> list:
    out = []
    for i, label in enumerate(labels):
        sub = df_c[df_c[idx_col] == i]
        t   = len(sub)
        n   = int((~sub["_acionado"]).sum())
        s   = round(float(sub["_saldo"].sum()), 2)
        out.append({
            "label": label,
            "total": t,
            "acion": t - n,
            "nao":   n,
            "pct":   round((t - n) / t * 100, 1) if t else 0.0,
            "saldo": s,
        })
    return out


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

    # ── Novas dimensões da Carteira (20/08/2026) ─────────────────
    # Cada uma é calculada duas vezes: sobre todos os clientes do bloco (usada
    # quando o toggle "Acordos" está LIGADO) e só sobre os clientes SEM acordo
    # ativo (usada quando está DESLIGADO, o padrão) — mesmo efeito prático do
    # toggle já aplicado em Atraso/Valor, só que aqui via duas listas prontas
    # em vez de subtrair uma célula de matriz (essas dimensões não têm uma
    # linha "Acordo" própria como a Atraso tem).
    c_sem_acordo = c[c["_is_acordo"] == 0]
    genero              = calc_dim(c,            "_sexo_idx",    SEXO_LABELS)
    genero_sem_acordo   = calc_dim(c_sem_acordo, "_sexo_idx",    SEXO_LABELS)
    faixa_etaria            = calc_dim(c,            "_idade_idx",   IDADE_LABELS)
    faixa_etaria_sem_acordo = calc_dim(c_sem_acordo, "_idade_idx",   IDADE_LABELS)
    categoria_prof            = calc_dim(c,            "_catprof_idx", catprof_list)
    categoria_prof_sem_acordo = calc_dim(c_sem_acordo, "_catprof_idx", catprof_list)
    faixa_renda            = calc_dim(c,            "_renda_idx",   RENDA_LABELS)
    faixa_renda_sem_acordo = calc_dim(c_sem_acordo, "_renda_idx",   RENDA_LABELS)
    score_banda            = calc_dim(c,            "_score_idx",   SCORE_LABELS)
    score_banda_sem_acordo = calc_dim(c_sem_acordo, "_score_idx",   SCORE_LABELS)
    agrupador            = calc_dim(c,            "_ag_idx",      ag_list)
    agrupador_sem_acordo = calc_dim(c_sem_acordo, "_ag_idx",      ag_list)

    # ── Overview de Colaboradores devedores (21/08/2026) ─────────
    # Mesmo shape/template das 6 dimensões acima, mas em vez de uma categoria
    # nova, é a carteira restrita a quem bate com a planilha de RH
    # (_is_funcionario==1), bucketada pela mesma faixa de atraso (_fa) já usada
    # em "atraso" — dá o mesmo overview (KPIs + distribuição + cobertura) só
    # que olhando exclusivamente para os clientes que também são colaboradores.
    # Coluna sempre existe (fallback 0 pra todo mundo quando não há planilha de
    # RH na pasta — ver Seção 7 do doc do projeto), então nunca quebra aqui.
    colaboradores            = calc_dim(c[c["_is_funcionario"] == 1],            "_fa", FA_LABELS)
    colaboradores_sem_acordo = calc_dim(c_sem_acordo[c_sem_acordo["_is_funcionario"] == 1], "_fa", FA_LABELS)

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
        # Novas dimensões da Carteira (20/08/2026) — ver Seção 7 do doc do projeto
        "genero": genero, "genero_sem_acordo": genero_sem_acordo,
        "faixa_etaria": faixa_etaria, "faixa_etaria_sem_acordo": faixa_etaria_sem_acordo,
        "categoria_prof": categoria_prof, "categoria_prof_sem_acordo": categoria_prof_sem_acordo,
        "faixa_renda": faixa_renda, "faixa_renda_sem_acordo": faixa_renda_sem_acordo,
        "score_banda": score_banda, "score_banda_sem_acordo": score_banda_sem_acordo,
        "agrupador": agrupador, "agrupador_sem_acordo": agrupador_sem_acordo,
        "colaboradores": colaboradores, "colaboradores_sem_acordo": colaboradores_sem_acordo,
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

# Contagem de acionamentos feitos especificamente pela assessoria ATUAL do
# cliente (join por CPF + Assessoria, não só CPF) — usada no analítico (r[16])
# pra manter consistência com o "sem acionamento" por assessoria da Matriz
# (by_assessoria abaixo), que já usa essa mesma lógica de filtro. r[10]/_qtd
# continua sendo o histórico GLOBAL (qualquer assessoria que já tocou o CPF);
# _qtd_own só conta o que a assessoria que hoje tem o cliente já fez ela mesma.
own_cnt = (acion_valid
           .groupby(["_cpf", "_as"])
           .size()
           .rename("_qtd_own"))

cart = (cart
        .join(acion_cnt,  on="_cpf")
        .join(ultimo_st,  on="_cpf")
        .join(freq_st,    on="_cpf")
        .join(tel_cnt,    on="_cpf")
        .join(own_cnt,    on=["_cpf", "_as"]))
cart["_qtd"]      = cart["_qtd"].fillna(0).astype(int)
cart["_qtd_tel"]  = cart["_qtd_tel"].fillna(0).astype(int)
cart["_qtd_own"]  = cart["_qtd_own"].fillna(0).astype(int)
cart["_ultimo"]   = cart["_ultimo"].fillna("").astype(str)
cart["_freq_st"]  = cart["_freq_st"].fillna("").astype(str)
cart["_acionado"] = cart["_qtd"] > 0

total     = len(cart)
acionados = int(cart["_acionado"].sum())
cobertura = round(acionados / total * 100, 1) if total else 0
print(f"  Total: {total:,} | Acionados: {acionados:,} | Não: {total-acionados:,} | Cobertura: {cobertura}%")

# ================================================================
#  Collection Score (ex-"Propensão a Acordo") — novo em 20/08/2026,
#  renomeado e recalibrado em 21/08/2026
#  ------------------------------------------------------------
#  O QUE É: modelo estatístico (regressão logística) treinado na própria
#  carteira do mês, prevendo a probabilidade de um cliente pertencer ao
#  perfil que hoje já está em acordo formal ativo (_is_acordo==1) — usado
#  como proxy de "bom pagador / fácil de converter", já que o CSV não traz
#  histórico de pagamento real, só o snapshot atual da carteira.
#
#  NÃO é o Score Fatura, e pode até divergir dele: nos testes, clientes de
#  Score Fatura MAIS BAIXO tiveram mais chance de estar em acordo —
#  provavelmente porque são o público mais empurrado pelas assessorias pra
#  renegociação formal, não porque "score baixo = melhor pagador".
#
#  FEATURES (deliberadamente SEM Dias/Situação/fa_idx — a definição de
#  _is_acordo já usa esses campos; incluí-los tornaria o modelo tautológico,
#  não preditivo): idade, score fatura, renda, saldo (log), categoria
#  profissão, sexo, agrupador, UF.
#
#  ⚠️ QTD. DE ACIONAMENTOS FOI REMOVIDA DAS FEATURES EM 21/08/2026.
#  Na primeira versão (20/08) essa variável (log_qtd) tinha o maior peso do
#  modelo — incluí-la levava o AUC de 0,63 pra 0,87, mas o efeito colateral
#  acabou sendo dominante demais na prática: 5,6% da carteira tem zero
#  acionamentos, e 99,4% desses clientes caíam automaticamente na banda A
#  (propensão média 96 num range de 0-100, contra 47 de quem já foi
#  contatado ao menos uma vez) — o ranking virava essencialmente "quem
#  ainda não foi tocado este mês", não um perfil de potencial de pagamento.
#  Isso já é informação óbvia e visível na própria coluna Qtd. Acionamentos
#  da tabela — não precisa de modelo pra saber que vale ligar pra quem
#  nunca foi ligado. O valor do Collection Score está em achar o PERFIL de
#  maior potencial de pagamento dentro da carteira, independente de quem
#  já foi ou não contatado — por isso a variável saiu do modelo (decisão do
#  usuário, 21/08/2026). Qtd. de acionamentos continua visível e filtrável
#  na tabela, só não influencia mais o score.
#
#  SCORE FINAL: percentil (0-100) da probabilidade prevista dentro da
#  própria carteira do mês — não a probabilidade bruta (fica baixa demais
#  pra ler, já que só ~4% da carteira está em acordo). Banda A (top 25%,
#  maior propensão) a D (25% inferior, menor propensão).
# ================================================================
print("  Calculando Collection Score...")
coll_meta = None
try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer

    _catprof_top = cart["_catprof"].value_counts()
    _catprof_top = set(_catprof_top[_catprof_top > 500].index)
    _agrup_top   = {"Z ON AZUL PF", "Z ON ROSA PF", "Z ON ROXO PF"}
    _uf_top      = {"PR", "SC"}

    coll_df = pd.DataFrame({
        "idade":    cart["_idade"],
        "score":    cart["_score"],
        "renda":    cart["_renda"],
        "log_saldo": np.log1p(cart["_saldo"].clip(lower=0)),
        "catprof":  cart["_catprof"].where(cart["_catprof"].isin(_catprof_top), "Outros"),
        "sexo":     cart["_sexo"].where(cart["_sexo"].isin(["Feminino", "Masculino"]), "Não informado"),
        "agrup":    cart["_ag"].where(cart["_ag"].isin(_agrup_top), "Outros"),
        "uf":       cart["_uf"].where(cart["_uf"].isin(_uf_top), "Outros"),
    })
    coll_y = cart["_is_acordo"]

    _num_cols = ["idade", "score", "renda", "log_saldo"]
    _cat_cols = ["catprof", "sexo", "agrup", "uf"]

    _pre_num = Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())])
    _pre = ColumnTransformer([
        ("num", _pre_num, _num_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), _cat_cols),
    ])
    _clf = Pipeline([("pre", _pre), ("lr", LogisticRegression(max_iter=2000, class_weight="balanced"))])

    _n_pos = int(coll_y.sum())
    if _n_pos >= 30 and (len(coll_y) - _n_pos) >= 30:
        _cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        _auc_scores = cross_val_score(_clf, coll_df, coll_y, cv=_cv, scoring="roc_auc")
        _auc = round(float(_auc_scores.mean()), 3)

        _clf.fit(coll_df, coll_y)
        _proba = _clf.predict_proba(coll_df)[:, 1]
        cart["_collscore"] = pd.Series(_proba, index=cart.index).rank(pct=True) * 100
        # banda 0 = A (maior propensão) ... 3 = D (menor propensão)
        cart["_collband"] = (3 - pd.qcut(cart["_collscore"], 4, labels=False, duplicates="drop")).astype(int)

        _feat_names = _num_cols + list(
            _clf.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(_cat_cols)
        )
        _coefs = _clf.named_steps["lr"].coef_[0]
        _top_feats = sorted(zip(_feat_names, _coefs), key=lambda x: -abs(x[1]))[:8]

        _band_labels = [
            "A — Collection Score Alto", "B — Collection Score Médio-Alto",
            "C — Collection Score Médio-Baixo", "D — Collection Score Baixo",
        ]
        # Composição das bandas só sobre quem ainda faz sentido priorizar: fora de
        # acordo (já resolvido) e fora de "Sem atraso" (saldo=0, nada a cobrar) —
        # é a mesma população que a aba nova vai listar por padrão.
        _elig = cart[(cart["_is_acordo"] == 0) & (cart["_saldo"] > 0)]
        _band_counts = _elig["_collband"].value_counts().reindex(range(4), fill_value=0)

        coll_meta = {
            "auc": _auc,
            "n_treino": int(len(coll_y)),
            "n_pos_treino": _n_pos,
            "target_desc": "cliente com acordo formal ativo (Situação=Ativo, Dias=0, Saldo>0)",
            "features": _num_cols + _cat_cols,
            "top_features": [{"nome": n, "peso": round(float(c), 3)} for n, c in _top_feats],
            "band_labels": _band_labels,
            "band_counts": [int(_band_counts.get(i, 0)) for i in range(4)],
            "n_elegiveis": int(len(_elig)),
        }
        print(f"    → AUC (5-fold CV): {_auc} | treino: {len(coll_y):,} clientes ({_n_pos:,} em acordo)")
    else:
        print("    ⚠ Poucos casos de acordo na carteira deste mês — Propensão a Acordo não calculada")
        cart["_collscore"] = 0.0
        cart["_collband"]  = 3
except ImportError:
    print("    ⚠ scikit-learn não instalado — Propensão a Acordo não calculada (pip install scikit-learn)")
    cart["_collscore"] = 0.0
    cart["_collband"]  = 3

# ================================================================
#  Propensão de Pagamento (30 dias) — novo em 21/08/2026
#  ------------------------------------------------------------
#  Diferente do Collection Score acima (que usa acordo ativo como proxy),
#  este modelo usa HISTÓRICO REAL de pagamento — arquivo(s) opcional(is)
#  "Recuperação AAAA.csv" (um por ano, ex: Recuperação 2025.csv +
#  Recuperação 2026.csv) — para prever a probabilidade de o cliente pagar
#  algo nos próximos 30 dias. Metodologia por DATA DE CORTE, sem vazamento:
#    • Features (estilo RFM): calculadas usando só pagamentos ANTERIORES
#      ao corte — recência, tenure, frequência, valor médio/total, % via
#      acordo, atraso médio, pagamentos nos últimos 90/180 dias.
#    • Rótulo: 1 se o CPF pagou algo nos 30 dias seguintes ao corte.
#    • Validação fora do tempo: treina num corte mais antigo, testa num
#      corte independente mais recente (nunca visto) — é o AUC reportado.
#    • Modelo de produção: retreinado no corte mais recente possível
#      (hoje − 30d) e aplicado sobre o histórico completo até hoje para
#      prever os próximos 30 dias a partir de agora.
#  Validado em estudo standalone de 21/08/2026 (AUC out-of-time = 0,81,
#  decil mais alto paga 54,5% das vezes vs. 1,6% no mais baixo) — ver
#  claude/05_Acionamentos_carteira_Z-ON_card.md, Seção 7.
#  Arquivo(s) OPCIONAL(is): se ausente(s) ou insuficiente(s), a marcação
#  fica "sem histórico" pra todo mundo, sem bloquear o resto da geração
#  (mesmo padrão de tolerância do Collection Score sem scikit-learn / da
#  planilha de RH ausente para Colaboradores).
#  RODA EM PARALELO ao Collection Score — não o substitui (decisão do
#  usuário, 21/08/2026).
# ================================================================
print("  Calculando Propensão de Pagamento (30d)...")
prop_meta = None
cart["_propscore"] = 0.0
cart["_propband"]  = -1   # -1 = sem histórico de pagamento (não escorável)

recup_paths = [p for p in sorted(SCRIPT_DIR.glob("*.csv")) if "recupera" in p.name.lower()]
if recup_paths:
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import roc_auc_score

        PROP_COLS = ["Cliente","Tipo","Contrato","Parcela","Assessoria","Data","Valor","Pct",
                     "Liquidacao","Recebido","Dias","Vencimento","CPF"]
        _pag_dfs = []
        for p in recup_paths:
            _d = pd.read_csv(p, encoding="latin-1", sep=None, engine="python")
            if _d.shape[1] >= len(PROP_COLS):
                _d = _d.iloc[:, :len(PROP_COLS)]
                _d.columns = PROP_COLS
                _pag_dfs.append(_d)
            else:
                print(f"    ⚠ {p.name} não tem o formato esperado ({len(PROP_COLS)} colunas) — ignorado")

        if not _pag_dfs:
            raise ValueError("nenhum arquivo de Recuperação com formato reconhecido")

        pag = pd.concat(_pag_dfs, ignore_index=True)
        pag["_cpf_norm"] = pag["CPF"].apply(norm_cpf)
        pag["_receb_n"]  = pag["Recebido"].apply(safe_float)
        pag["_liq_dt"]   = pd.to_datetime(pag["Liquidacao"], format="%d/%m/%Y", errors="coerce")
        pag["_is_ac_pag"] = (pag["Tipo"] == "Acordo").astype(int)
        pag = pag[(pag["_cpf_norm"] != "") & pag["_liq_dt"].notna() & (pag["_receb_n"] > 0)]

        HOJE_DT = datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        PROP_HORIZON = 30
        PROP_FEATS = ["recencia_dias","tenure_dias","freq_pagtos","valor_medio","valor_total",
                      "valor_std","dias_atraso_medio","pct_acordo","n_assessorias","n_contratos",
                      "n_pagtos_90d","n_pagtos_180d"]

        def _prop_build_feats(ref_date):
            h = pag[pag["_liq_dt"] < ref_date]
            if h.empty:
                return pd.DataFrame(columns=["_cpf_norm"] + PROP_FEATS)
            g = h.groupby("_cpf_norm")
            last_pag, first_pag = g["_liq_dt"].max(), g["_liq_dt"].min()
            f = pd.DataFrame({
                "recencia_dias":     (ref_date - last_pag).dt.days,
                "tenure_dias":       (ref_date - first_pag).dt.days,
                "freq_pagtos":       g.size(),
                "valor_medio":       g["_receb_n"].mean(),
                "valor_total":       g["_receb_n"].sum(),
                "valor_std":         g["_receb_n"].std().fillna(0),
                "dias_atraso_medio": g["Dias"].mean(),
                "pct_acordo":        g["_is_ac_pag"].mean(),
                "n_assessorias":     g["Assessoria"].nunique(),
                "n_contratos":       g["Contrato"].nunique(),
            })
            for win, name in [(90, "n_pagtos_90d"), (180, "n_pagtos_180d")]:
                hw = h[h["_liq_dt"] >= ref_date - timedelta(days=win)]
                f[name] = hw.groupby("_cpf_norm").size()
                f[name] = f[name].fillna(0)
            return f.reset_index()

        def _prop_label(start, end):
            lw = pag[(pag["_liq_dt"] >= start) & (pag["_liq_dt"] < end)]
            return set(lw["_cpf_norm"])

        T = HOJE_DT - timedelta(days=PROP_HORIZON)
        feat_train = _prop_build_feats(T)
        feat_train["y"] = feat_train["_cpf_norm"].isin(_prop_label(T, HOJE_DT)).astype(int)
        _n_pos = int(feat_train["y"].sum())

        if len(feat_train) >= 200 and _n_pos >= 30 and (len(feat_train) - _n_pos) >= 30:
            # Validação fora do tempo: treina num corte mais antigo, testa num corte
            # independente mais recente que o modelo nunca viu.
            T_tr_oot = HOJE_DT - timedelta(days=150)
            T_te_oot = HOJE_DT - timedelta(days=60)
            f_tr_oot = _prop_build_feats(T_tr_oot)
            f_tr_oot["y"] = f_tr_oot["_cpf_norm"].isin(_prop_label(T_tr_oot, T_tr_oot + timedelta(days=PROP_HORIZON))).astype(int)
            f_te_oot = _prop_build_feats(T_te_oot)
            f_te_oot["y"] = f_te_oot["_cpf_norm"].isin(_prop_label(T_te_oot, T_te_oot + timedelta(days=PROP_HORIZON))).astype(int)

            _auc_oot = None
            if len(f_tr_oot) >= 200 and len(f_te_oot) >= 200:
                _m_oot = HistGradientBoostingClassifier(max_depth=4, max_iter=150, learning_rate=0.08, random_state=42)
                _m_oot.fit(f_tr_oot[PROP_FEATS], f_tr_oot["y"])
                _p_oot = _m_oot.predict_proba(f_te_oot[PROP_FEATS])[:, 1]
                _auc_oot = round(float(roc_auc_score(f_te_oot["y"], _p_oot)), 3)

            _model = HistGradientBoostingClassifier(max_depth=4, max_iter=150, learning_rate=0.08, random_state=42)
            _model.fit(feat_train[PROP_FEATS], feat_train["y"])

            feat_live = _prop_build_feats(HOJE_DT)
            if len(feat_live):
                _scores = pd.Series(_model.predict_proba(feat_live[PROP_FEATS])[:, 1] * 100, index=feat_live["_cpf_norm"])
            else:
                _scores = pd.Series(dtype=float)
            _mapped = cart["_cpf_norm"].map(_scores)   # NaN pra quem não tem histórico
            _tem_hist = _mapped.notna()
            cart.loc[_tem_hist, "_propscore"] = _mapped[_tem_hist].astype(float)
            if _tem_hist.any():
                cart.loc[_tem_hist, "_propband"] = (
                    3 - pd.qcut(cart.loc[_tem_hist, "_propscore"], 4, labels=False, duplicates="drop")
                ).astype(int)

            prop_meta = {
                "auc_oot": _auc_oot,
                "horizon_dias": PROP_HORIZON,
                "cutoff_treino": T.strftime("%Y-%m-%d"),
                "oot_cutoff_treino": T_tr_oot.strftime("%Y-%m-%d"),
                "oot_cutoff_teste": T_te_oot.strftime("%Y-%m-%d"),
                "n_treino": int(len(feat_train)),
                "n_pos_treino": _n_pos,
                "n_pagamentos_historico": int(len(pag)),
                "n_cpfs_historico": int(pag["_cpf_norm"].nunique()),
                "n_escoravel": int(_tem_hist.sum()),
                "pct_escoravel": round(float(_tem_hist.mean()) * 100, 1) if len(cart) else 0,
                "band_labels": ["A — Propensão Alta", "B — Propensão Média-Alta",
                                "C — Propensão Média-Baixa", "D — Propensão Baixa"],
            }
            print(f"    → AUC out-of-time: {_auc_oot} | treino: {len(feat_train):,} CPFs "
                  f"({_n_pos:,} pagaram nos 30d seguintes ao corte) | escoráveis na carteira: "
                  f"{int(_tem_hist.sum()):,} ({prop_meta['pct_escoravel']}%)")
        else:
            print(f"    ⚠ Histórico de pagamento insuficiente (treino={len(feat_train)}, "
                  f"positivos={_n_pos}) — Propensão de Pagamento não calculada")
    except ImportError:
        print("    ⚠ scikit-learn não instalado — Propensão de Pagamento não calculada")
    except Exception as e:
        print(f"    ⚠ Falha ao calcular Propensão de Pagamento ({e}) — marcação fica zerada")
else:
    print("  (nenhum arquivo 'Recuperação AAAA.csv' encontrado na pasta — nome precisa conter "
          "\"recupera\"; Propensão de Pagamento não calculada, não bloqueia a geração dos outros JSONs)")

# ================================================================
#  Esperado x Realizado — Collection Score (novo em 24/08/2026)
#  ------------------------------------------------------------
#  Objetivo: dar um significado concreto a cada banda (A-D) do Collection
#  Score, medindo DUAS coisas separadas (decisão do usuário, 24/08/2026):
#    • Conversão em acordo  — o cliente formalizou um pagamento tipo
#      "Acordo" dentro da janela
#    • Pagamento efetivo    — o cliente pagou QUALQUER coisa (acordo ou
#      não) dentro da janela
#  "Esperado" é transversal (hoje): % já em is_acordo agora + propensão
#  média de pagamento (modelo de Propensão de Pagamento), por banda.
#  "Realizado" é longitudinal: acompanha coortes de clientes ao longo do
#  tempo — toda rodada registra a banda de cada CPF na data de hoje
#  (pendente), e quando uma coorte completa ER_HORIZON dias desde que foi
#  registrada, verifica no HISTÓRICO DE PAGAMENTOS (mesmo `pag` da
#  Propensão de Pagamento acima) se houve pagamento/acordo dentro dessa
#  janela fixa de ER_HORIZON dias — não no status "hoje" da Carteira, que
#  ia inflar a conversão se o script rodar tarde (mais de 30d depois).
#  Isso significa que o "realizado" só existe pra coortes atribuídas há
#  pelo menos ER_HORIZON dias — como a banda só existe desde 20/08/2026
#  (recalibrada em 21/08/2026), a primeira leitura real só fica disponível
#  ~30 dias depois da primeira vez que este bloco rodar. Até lá, fica
#  "pendente" (ver `esperado_realizado.n_pendentes_imaturas` no JSON).
#  Depende de `pag` (Recuperação AAAA.csv) estar presente NA RODADA em que
#  a coorte completa a janela — se não estiver, a coorte fica pendente até
#  uma rodada futura que já tenha o arquivo (mesma tolerância opcional já
#  usada pela Propensão de Pagamento).
#  Estado persistido em `collection_band_history.json` — mesmo padrão do
#  `index.json` (baixar do GitHub antes de rodar, subir de volta depois).
# ================================================================
print("  Calculando Esperado x Realizado (Collection Score)...")
ER_HORIZON = 30
BAND_LABELS_SHORT = ["A", "B", "C", "D"]

# --- Esperado (transversal, hoje) ---
band_esperado = []
for _b in range(4):
    _sub = cart[cart["_collband"] == _b]
    _n = len(_sub)
    _pct_acordo_hoje = round(float(_sub["_is_acordo"].mean()) * 100, 2) if _n else 0.0
    _sub_escoravel = _sub[_sub["_propband"] != -1]
    _pct_pagto_esperado = round(float(_sub_escoravel["_propscore"].mean()), 1) if len(_sub_escoravel) else None
    band_esperado.append({
        "banda": BAND_LABELS_SHORT[_b],
        "n_clientes": int(_n),
        "pct_ja_em_acordo_hoje": _pct_acordo_hoje,
        "pct_pagamento_esperado": _pct_pagto_esperado,
        "n_escoravel_pagamento": int(len(_sub_escoravel)),
    })

# --- Realizado (coortes que já maturaram ER_HORIZON dias) ---
er_path = SCRIPT_DIR / "collection_band_history.json"
if er_path.exists():
    with open(er_path, "r", encoding="utf-8") as f:
        er_hist = json.load(f)
else:
    er_hist = {"pendentes": [], "resolvidos": []}
print(f"    collection_band_history.json existente: {len(er_hist.get('pendentes', []))} pendente(s), "
      f"{len(er_hist.get('resolvidos', []))} lote(s) já resolvido(s)")

# Registra a coorte deste mês (substitui se este MES_ID já tinha sido registrado antes)
er_hist["pendentes"] = [p for p in er_hist.get("pendentes", []) if p.get("mes_ref") != MES_ID]
hoje_iso = HOJE_DT.strftime("%Y-%m-%d") if "HOJE_DT" in globals() else datetime.now(BRT).strftime("%Y-%m-%d")
for _, _rr in cart[["_cpf_norm", "_collband"]].iterrows():
    if not _rr["_cpf_norm"]:
        continue
    er_hist["pendentes"].append({
        "cpf": _rr["_cpf_norm"],
        "mes_ref": MES_ID,
        "data_ref": hoje_iso,
        "banda": int(_rr["_collband"]),
    })

_hoje_dt_check = datetime.strptime(hoje_iso, "%Y-%m-%d")
_pag_disponivel = "pag" in globals() and isinstance(pag, pd.DataFrame) and len(pag) > 0
_pendentes_restantes = []
_resolvidos_novos = defaultdict(lambda: {"n_coorte": 0, "n_acordo": 0, "n_pagou": 0})
_qtd_resolvidas_agora = 0
for _p in er_hist["pendentes"]:
    _data_ref_dt = datetime.strptime(_p["data_ref"], "%Y-%m-%d")
    _dias_passados = (_hoje_dt_check - _data_ref_dt).days
    if _dias_passados < ER_HORIZON or not _pag_disponivel:
        _pendentes_restantes.append(_p)
        continue
    _janela = pag[(pag["_cpf_norm"] == _p["cpf"]) &
                  (pag["_liq_dt"] >= _data_ref_dt) &
                  (pag["_liq_dt"] < _data_ref_dt + timedelta(days=ER_HORIZON))]
    _pagou = len(_janela) > 0
    _fez_acordo = bool((_janela["_is_ac_pag"] == 1).any()) if len(_janela) else False
    _key = (_p["mes_ref"], _p["banda"])
    _resolvidos_novos[_key]["n_coorte"] += 1
    if _pagou:
        _resolvidos_novos[_key]["n_pagou"] += 1
    if _fez_acordo:
        _resolvidos_novos[_key]["n_acordo"] += 1
    _qtd_resolvidas_agora += 1

for (_mes_ref, _banda), _agg in _resolvidos_novos.items():
    _existente = next((r for r in er_hist["resolvidos"]
                        if r["mes_ref"] == _mes_ref and r["banda"] == _banda), None)
    if _existente:
        _existente["n_coorte"] += _agg["n_coorte"]
        _existente["n_acordo"] += _agg["n_acordo"]
        _existente["n_pagou"]  += _agg["n_pagou"]
    else:
        er_hist["resolvidos"].append({
            "mes_ref": _mes_ref, "banda": _banda, "horizonte_dias": ER_HORIZON,
            "n_coorte": _agg["n_coorte"], "n_acordo": _agg["n_acordo"], "n_pagou": _agg["n_pagou"],
        })

er_hist["pendentes"] = _pendentes_restantes
if _qtd_resolvidas_agora:
    print(f"    → {_qtd_resolvidas_agora:,} clientes de coortes maduras (≥{ER_HORIZON}d) resolvidos nesta rodada")
elif not _pag_disponivel:
    print(f"    ⚠ Sem Recuperação AAAA.csv nesta rodada — coortes maduras (se houver) ficam pendentes "
          f"até uma rodada futura que tenha o arquivo")
else:
    print(f"    (nenhuma coorte atingiu {ER_HORIZON} dias ainda — banda só existe desde 20/08/2026, "
          f"primeira leitura real prevista a partir de meados de setembro/2026)")

band_realizado = []
for _b in range(4):
    _regs = [r for r in er_hist["resolvidos"] if r["banda"] == _b]
    _n_coorte = sum(r["n_coorte"] for r in _regs)
    _n_acordo = sum(r["n_acordo"] for r in _regs)
    _n_pagou  = sum(r["n_pagou"] for r in _regs)
    band_realizado.append({
        "banda": BAND_LABELS_SHORT[_b],
        "horizonte_dias": ER_HORIZON,
        "n_coorte_madura": _n_coorte,
        "pct_conversao_acordo": round(_n_acordo / _n_coorte * 100, 2) if _n_coorte else None,
        "pct_pagamento_efetivo": round(_n_pagou / _n_coorte * 100, 2) if _n_coorte else None,
    })

n_pendentes_imaturas = len(er_hist["pendentes"])

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
    # Novas dimensões da Carteira (20/08/2026)
    "sexo_labels":        SEXO_LABELS,
    "faixa_etaria_labels": IDADE_LABELS,
    "catprof_list":       catprof_list,
    "renda_labels":       RENDA_LABELS,
    "score_labels":       SCORE_LABELS,
    # KPIs globais (espalhados no nível raiz)
    **bloco_global,
    # Acordos — para o dashboard poder excluí-los das métricas de cobertura
    "n_acordos": n_acordos,
    "fa_acordo_idx": FA_ACORDO_IDX,
    # Sem atraso (saldo zerado — quitados/em dia) — sempre visível em quantidade,
    # nunca distorce valor (saldo=0)
    "n_sem_atraso": n_sem_atraso,
    "fa_sem_atraso_idx": FA_SEM_ATRASO_IDX,
    # Colaborador (funcionário do grupo) — novo em 21/08/2026
    "filial_list":    filial_list,
    "cargo_list":     cargo_list,
    "n_funcionarios": n_funcionarios,
    "saldo_funcionarios": saldo_funcionarios,
}
if by_assessoria:
    mes_json["by_assessoria"] = by_assessoria
if coll_meta:
    mes_json["collection_score_meta"] = coll_meta
if prop_meta:
    mes_json["propensao_meta"] = prop_meta
# Esperado x Realizado — novo em 24/08/2026, ver Seção 7 do doc do projeto
mes_json["esperado_realizado"] = {
    "horizonte_dias": ER_HORIZON,
    "modelo_collection_score_valido": bool(coll_meta is not None),
    "n_pendentes_imaturas": n_pendentes_imaturas,
    "esperado": band_esperado,
    "realizado": band_realizado,
}


# ================================================================
#  Montar YYYY-MM-analitico.json
#  Array plano — formato lido diretamente por ANALITICO.filter(...)
#  [CPF, Nome, Tipo, Dias, fa_idx, Saldo, fv_idx,
#   ag_idx, uf_idx, Cidade, QtdAcion, UltimoStatus, StatusFreq, as_idx, is_acordo,
#   QtdTel, QtdAcionAssessoriaAtual,
#   sexo_idx, faixa_etaria_idx, categoria_prof_idx, faixa_renda_idx, score_idx,
#   collection_score, collection_band,
#   is_funcionario, filial_idx, cargo_idx,
#   propensao_score, propensao_band]
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
        int(r["_qtd_own"]),                 # 16 qtd_own  (acionamentos pela assessoria ATUAL do cliente)
        int(r["_sexo_idx"]),                # 17 sexo_idx (novo em 20/08/2026)
        int(r["_idade_idx"]),               # 18 faixa_etaria_idx
        int(r["_catprof_idx"]),             # 19 categoria_prof_idx
        int(r["_renda_idx"]),               # 20 faixa_renda_idx
        int(r["_score_idx"]),               # 21 score_idx
        round(float(r["_collscore"]), 1),   # 22 collection_score (percentil 0-100, novo em 20/08/2026)
        int(r["_collband"]),                # 23 collection_band (0=A alta propensão ... 3=D baixa propensão)
        int(r["_is_funcionario"]),          # 24 is_funcionario (novo em 21/08/2026)
        int(r["_filial_idx"]),              # 25 filial_idx (-1 se não é funcionário)
        int(r["_cargo_idx"]),               # 26 cargo_idx (-1 se não é funcionário)
        round(float(r["_propscore"]), 1),   # 27 propensao_score (probabilidade %, 0-100, novo em 21/08/2026)
        int(r["_propband"]),                # 28 propensao_band (0=A alta ... 3=D baixa, -1=sem histórico)
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

with open(er_path, "w", encoding="utf-8") as f:
    json.dump(er_hist, f, ensure_ascii=False, indent=2)
print(f"  ✓ collection_band_history.json{' ':9} {er_path.stat().st_size / 1024:>6.0f} KB  "
      f"({len(er_hist['pendentes'])} pendente(s), {len(er_hist['resolvidos'])} lote(s) resolvido(s))")

print(f"""
{'='*62}
  ✅  Concluído!

  Suba estes 4 arquivos na pasta data/ do GitHub:
    • {mes_path.name}
    • {analitico_path.name}
    • index.json
    • collection_band_history.json   (novo em 24/08/2026 — Esperado x
      Realizado do Collection Score; baixar a versão atual do GitHub e
      colocar nesta pasta ANTES de rodar o script no próximo mês, senão
      o histórico de coortes pendentes é perdido — mesmo cuidado já
      existente com o index.json)

  GitHub Pages atualiza em ~1 minuto após o commit.
{'='*62}
""")
