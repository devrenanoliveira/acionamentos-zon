"""
atualizar_dashboard.py
======================
Script de atualização do Dashboard de Acionamentos.

Fontes de dados (Google Sheets publicado):
  - Aba "Analitico"  → dados individuais por cliente (66k+ linhas)
  - Aba "Volume"     → volume diário por canal (digital + telefônico)
  - Aba "Motivos"    → resultado das ligações telefônicas

Como publicar o Google Sheets como CSV:
  1. Abra o arquivo → Arquivo → Compartilhar → Publicar na web
  2. Escolha a aba → formato CSV → Publicar
  3. Copie o link e cole abaixo nas variáveis SHEET_*_URL

Colunas esperadas em cada aba:
  Analitico: CPF, Nome, Tipo, Dias, Saldo, Agrupador, UF, Cidade, QtdAcion, UltimoStatus, StatusFrequente
  Volume:    Dia, Digital, Telefônico, FDS
  Motivos:   Resultado, Quantidade, Cor

Como executar manualmente:
  pip install pandas requests PyGithub
  export GITHUB_TOKEN=seu_token
  export REPO_NAME=seu_usuario/dashboard-acionamentos
  python atualizar_dashboard.py

Para teste local (sem subir para o GitHub):
  python atualizar_dashboard.py --local
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from io import StringIO

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO — edite estas variáveis
# ═══════════════════════════════════════════════════════════════

# Links de publicação do Google Sheets (CSV)
SHEET_ANALITICO_URL = os.environ.get("SHEET_ANALITICO_URL", "")
SHEET_VOLUME_URL    = os.environ.get("SHEET_VOLUME_URL", "")
SHEET_MOTIVOS_URL   = os.environ.get("SHEET_MOTIVOS_URL", "")

# Período do mês (preencha manualmente ou derive do dado)
MES_LABEL   = os.environ.get("MES_LABEL", "")    # ex: "Agosto 2026"
MES_PERIODO = os.environ.get("MES_PERIODO", "")   # ex: "01–31 ago/2026"
MES_ID      = os.environ.get("MES_ID", "")        # ex: "2026-08"  (YYYY-MM)

# Credenciais GitHub (injetadas automaticamente pelo Actions via GITHUB_TOKEN)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME    = os.environ.get("GITHUB_REPOSITORY", "")  # ex: "usuario/dashboard-acionamentos"

# Fuso horário Brasília
BRT = timezone(timedelta(hours=-3))

# ═══════════════════════════════════════════════════════════════
# FAIXAS
# ═══════════════════════════════════════════════════════════════

FA_LABELS = [
    "1–30 dias","31–60 dias","61–90 dias","91–120 dias",
    "121–150 dias","151–180 dias","181–360 dias","361–720 dias",">720 dias"
]
FV_LABELS = [
    "R$0–100","R$100–300","R$300–500","R$500–1k",
    "R$1k–5k","R$5k–10k","R$10k–50k","Acima R$50k"
]

def faixa_atraso(dias):
    if   dias <=  30: return 0
    elif dias <=  60: return 1
    elif dias <=  90: return 2
    elif dias <= 120: return 3
    elif dias <= 150: return 4
    elif dias <= 180: return 5
    elif dias <= 360: return 6
    elif dias <= 720: return 7
    else:             return 8

def faixa_valor(saldo):
    if   saldo <   100: return 0
    elif saldo <   300: return 1
    elif saldo <   500: return 2
    elif saldo <  1000: return 3
    elif saldo <  5000: return 4
    elif saldo < 10000: return 5
    elif saldo < 50000: return 6
    else:               return 7

MOTIVOS_COLORS = {
    "Não Localizado":    "#DC2626",
    "Atendeu/desligou":  "#EA580C",
    "Não atendeu":       "#D97706",
    "Promessa de pgto":  "#059669",
    "Recado":            "#7C3AED",
    "Sem cond. fin.":    "#64748B",
    "Reagendado":        "#1D4ED8",
    "Sem int. pagar":    "#991B1B",
    "Desempregado":      "#D97706",
    "Alega Pagamento":   "#059669",
    "Desconhece Dívida": "#9A3412",
    "Falecido":          "#94A3B8",
}

STATUS_LABEL = {
    "NL": "Não Localizado",
    "NA": "Nao atendeu",
    "AD": "Cliente atendeu e desligou",
    "PP": "Promessa de Pagamento",
    "RC": "Recado",
    "SF": "Sem Condições Financeiras",
    "RE": "Reagendado",
    "SI": "Sem interesse em Pagar",
    "AP": "Alega Pagamento",
    "DE": "Desempregado",
    "DD": "Desconhece Dívida",
    "FA": "Falecido",
    "SM": "Envio de SMS/Whatsapp",
    "-":  "—"
}


# ═══════════════════════════════════════════════════════════════
# LEITURA DE DADOS
# ═══════════════════════════════════════════════════════════════

def limpar_valor_br(v):
    """Converte 'R$ 1.234,56' → 1234.56"""
    if pd.isna(v): return 0.0
    s = str(v).strip().replace("R$","").replace(" ","").replace(".","").replace(",",".")
    try:
        return float(s)
    except:
        return 0.0

def ler_csv_url(url, nome):
    print(f"  Lendo {nome}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    print(f"    {len(df)} linhas, colunas: {list(df.columns)}")
    return df


def ler_analitico(url):
    df = ler_csv_url(url, "Analitico")
    # Colunas esperadas (ajuste os nomes conforme seu sheet):
    # CPF, Nome, Tipo, Dias, Saldo, Agrupador, UF, Cidade, QtdAcion, UltimoStatus, StatusFrequente

    col_map = {
        # nome no sheet    →  nome padrão
        "cpf":              "CPF",
        "cnpj":             "CPF",
        "cpf/cnpj":         "CPF",
        "nome":             "Nome",
        "tipo":             "Tipo",
        "dias":             "Dias",
        "dias_atraso":      "Dias",
        "diasatraso":       "Dias",
        "saldo":            "Saldo",
        "saldo_contabil":   "Saldo",
        "saldo_atraso":     "Saldo",
        "agrupador":        "Agrupador",
        "uf":               "UF",
        "cidade":           "Cidade",
        "qtd_acion":        "QtdAcion",
        "qtdacion":         "QtdAcion",
        "quantidade_acionamentos": "QtdAcion",
        "ultimo_status":    "UltimoStatus",
        "ultimostatus":     "UltimoStatus",
        "status_frequente": "StatusFrequente",
        "statusfrequente":  "StatusFrequente",
    }
    df.columns = [col_map.get(c.lower().replace(" ","_"), c) for c in df.columns]

    # Limpeza
    df["CPF"]      = df["CPF"].astype(str).str.strip().str.replace(r"[.\-/]","",regex=True).str.zfill(11)
    df["Tipo"]     = df.get("Tipo", pd.Series(["F"]*len(df))).fillna("F").astype(str).str.upper().str.strip()
    df["Dias"]     = pd.to_numeric(df["Dias"], errors="coerce").fillna(0).astype(int)
    df["Saldo"]    = df["Saldo"].apply(limpar_valor_br)
    df["Agrupador"]= df.get("Agrupador", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()
    df["UF"]       = df.get("UF", pd.Series([""] * len(df))).fillna("").astype(str).str.upper().str.strip()
    df["Cidade"]   = df.get("Cidade", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.upper()
    df["QtdAcion"] = pd.to_numeric(df.get("QtdAcion", pd.Series([0]*len(df))), errors="coerce").fillna(0).astype(int)
    df["UltimoStatus"]    = df.get("UltimoStatus", pd.Series(["-"]*len(df))).fillna("-").astype(str).str.strip()
    df["StatusFrequente"] = df.get("StatusFrequente", pd.Series(["-"]*len(df))).fillna("-").astype(str).str.strip()

    # Derivados
    df["fa"] = df["Dias"].apply(faixa_atraso)
    df["fv"] = df["Saldo"].apply(faixa_valor)

    # Índices de agrupador e UF
    ag_list = sorted(df["Agrupador"].unique().tolist())
    uf_list = sorted(df["UF"].unique().tolist())
    ag_map  = {a:i for i,a in enumerate(ag_list)}
    uf_map  = {u:i for i,u in enumerate(uf_list)}
    df["ag_idx"] = df["Agrupador"].map(ag_map)
    df["uf_idx"] = df["UF"].map(uf_map)

    return df, ag_list, uf_list


def ler_volume(url):
    df = ler_csv_url(url, "Volume")
    col_map = {
        "dia":         "Dia",
        "data":        "Dia",
        "digital":     "Digital",
        "tel":         "Tel",
        "telefonico":  "Tel",
        "telefônico":  "Tel",
        "fds":         "FDS",
        "final_semana":"FDS",
        "fim_semana":  "FDS",
    }
    df.columns = [col_map.get(c.lower().strip().replace(" ","_").replace("ô","o"), c) for c in df.columns]
    df["Digital"] = pd.to_numeric(df.get("Digital",0), errors="coerce").fillna(0).astype(int)
    df["Tel"]     = pd.to_numeric(df.get("Tel",0), errors="coerce").fillna(0).astype(int)
    df["FDS"]     = df.get("FDS", False).astype(bool)
    return df


def ler_motivos(url):
    df = ler_csv_url(url, "Motivos")
    col_map = {
        "resultado":  "Resultado",
        "motivo":     "Resultado",
        "quantidade": "Quantidade",
        "qtd":        "Quantidade",
        "cor":        "Cor",
        "color":      "Cor",
    }
    df.columns = [col_map.get(c.lower().strip(), c) for c in df.columns]
    df["Quantidade"] = pd.to_numeric(df["Quantidade"], errors="coerce").fillna(0).astype(int)
    if "Cor" not in df.columns:
        df["Cor"] = df["Resultado"].map(MOTIVOS_COLORS).fillna("#94A3B8")
    return df


# ═══════════════════════════════════════════════════════════════
# CÁLCULO DAS AGREGAÇÕES
# ═══════════════════════════════════════════════════════════════

def calcular_atraso(df):
    """D_ATRASO: por faixa de atraso"""
    rows = []
    for i, label in enumerate(FA_LABELS):
        sub = df[df["fa"] == i]
        total = len(sub)
        acion = (sub["QtdAcion"] > 0).sum()
        nao   = total - acion
        pct   = round(acion / total * 100, 1) if total > 0 else 0.0
        rows.append({"id":i,"label":label,"total":int(total),"acion":int(acion),"nao":int(nao),"pct":pct})
    return rows

def calcular_valor(df):
    """D_VALOR: por faixa de valor"""
    rows = []
    for i, label in enumerate(FV_LABELS):
        sub = df[df["fv"] == i]
        total = len(sub)
        if total == 0: continue
        acion = (sub["QtdAcion"] > 0).sum()
        nao   = total - acion
        pct   = round(acion / total * 100, 1)
        rows.append({"id":i,"label":label,"total":int(total),"acion":int(acion),"nao":int(nao),"pct":pct})
    return rows

def calcular_matrix(df):
    """MATRIX[atraso_i][valor_j] = [nao, total]"""
    matrix = []
    for ai in range(len(FA_LABELS)):
        row = []
        for vi in range(len(FV_LABELS)):
            sub   = df[(df["fa"]==ai) & (df["fv"]==vi)]
            total = len(sub)
            nao   = int((sub["QtdAcion"]==0).sum())
            row.append([nao, int(total)])
        matrix.append(row)
    return matrix

def calcular_freq(df):
    """D_FREQ: distribuição de quantidade de acionamentos"""
    buckets = [(0,"0","Sem contato"),(1,"1","1 contato"),(2,"2","2 contatos"),
               (3,"3","3 contatos"),(4,"4","4 contatos"),(5,"5","5 contatos"),(-1,"6+","6+ contatos")]
    rows = []
    for val, n, label in buckets:
        if val == -1:
            v = int((df["QtdAcion"]>=6).sum())
        else:
            v = int((df["QtdAcion"]==val).sum())
        rows.append({"n":n,"label":label,"v":v})
    return rows


# ═══════════════════════════════════════════════════════════════
# MONTAR JSON FINAL
# ═══════════════════════════════════════════════════════════════

def montar_summary(df, df_volume, df_motivos, ag_list, uf_list, mes_id, mes_label, mes_periodo):
    now = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    total = len(df)
    acionados     = int((df["QtdAcion"]>0).sum())
    sem_acion     = total - acionados
    com_promessa  = int((df["UltimoStatus"]=="PP").sum() | (df["StatusFrequente"]=="PP").sum())
    total_tel     = int(df_volume["Tel"].sum())
    total_digital = int(df_volume["Digital"].sum())
    total_acion   = total_tel + total_digital
    max_nao_val   = max((row["nao"] for row in calcular_atraso(df) if row["nao"]>0), default=1)

    volume_list = [
        {"dia": str(row["Dia"]), "digital":int(row["Digital"]), "tel":int(row["Tel"]), "fds":bool(row["FDS"])}
        for _, row in df_volume.iterrows()
    ]
    motivos_list = [
        {"name": str(row["Resultado"]), "value":int(row["Quantidade"]),
         "color": MOTIVOS_COLORS.get(str(row["Resultado"]).strip(), row.get("Cor","#94A3B8"))}
        for _, row in df_motivos.iterrows()
    ]

    return {
        "periodo":          mes_periodo,
        "mes_label":        mes_label,
        "total_clientes":   total,
        "acionados":        acionados,
        "sem_acionamento":  sem_acion,
        "com_promessa":     com_promessa,
        "total_acionamentos": total_acion,
        "total_tel":        total_tel,
        "max_nao":          max_nao_val,
        "atraso":           calcular_atraso(df),
        "valor":            calcular_valor(df),
        "matrix":           calcular_matrix(df),
        "freq":             calcular_freq(df),
        "motivos":          motivos_list,
        "volume":           volume_list,
        "fa_labels":        FA_LABELS,
        "fv_labels":        FV_LABELS,
        "ag_list":          ag_list,
        "uf_list":          uf_list,
        "status_label":     STATUS_LABEL,
        "atualizado_em":    now,
    }

def montar_analitico(df):
    """Converte DataFrame para array de arrays (mesma estrutura do original)."""
    records = []
    for _, r in df.iterrows():
        records.append([
            str(r["CPF"]),
            str(r["Nome"]),
            str(r["Tipo"]),
            int(r["Dias"]),
            int(r["fa"]),
            round(float(r["Saldo"]),2),
            int(r["fv"]),
            int(r["ag_idx"]),
            int(r["uf_idx"]),
            str(r["Cidade"]),
            int(r["QtdAcion"]),
            str(r["UltimoStatus"]),
            str(r["StatusFrequente"]),
        ])
    return records


# ═══════════════════════════════════════════════════════════════
# GRAVAÇÃO — LOCAL ou GITHUB
# ═══════════════════════════════════════════════════════════════

def salvar_local(summary, analitico, mes_id):
    os.makedirs("data", exist_ok=True)
    with open(f"data/{mes_id}.json","w",encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
    print(f"  data/{mes_id}.json salvo ({len(json.dumps(summary, ensure_ascii=False))//1024} KB)")

    with open(f"data/{mes_id}-analitico.json","w",encoding="utf-8") as f:
        json.dump(analitico, f, ensure_ascii=False)
    print(f"  data/{mes_id}-analitico.json salvo ({len(json.dumps(analitico, ensure_ascii=False))//1024//1024} MB)")

    # Atualizar index.json
    index_path = "data/index.json"
    if os.path.exists(index_path):
        with open(index_path,"r",encoding="utf-8") as f:
            idx = json.load(f)
    else:
        idx = {"meses":[]}
    # Verificar se o mês já está no índice
    existing_ids = [m["id"] for m in idx["meses"]]
    if mes_id not in existing_ids:
        idx["meses"].insert(0, {"id":mes_id,"label":summary["mes_label"],"periodo":summary["periodo"]})
    with open(index_path,"w",encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    print(f"  data/index.json atualizado")


def salvar_github(summary, analitico, mes_id):
    """Commita os JSONs diretamente no repositório via API do GitHub."""
    from github import Github, GithubException
    g    = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    now_str = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")

    def upsert(path, content_str, msg):
        content_bytes = content_str.encode("utf-8")
        try:
            existing = repo.get_contents(path)
            repo.update_file(path, msg, content_bytes, existing.sha)
            print(f"  Atualizado: {path}")
        except GithubException:
            repo.create_file(path, msg, content_bytes)
            print(f"  Criado: {path}")

    summary_str  = json.dumps(summary, ensure_ascii=False)
    analitico_str = json.dumps(analitico, ensure_ascii=False)
    upsert(f"data/{mes_id}.json",            summary_str,   f"Atualização {mes_id} — {now_str}")
    upsert(f"data/{mes_id}-analitico.json",  analitico_str, f"Analítico {mes_id} — {now_str}")

    # Atualizar index.json
    try:
        idx_file = repo.get_contents("data/index.json")
        idx = json.loads(idx_file.decoded_content.decode("utf-8"))
    except:
        idx = {"meses":[]}
    existing_ids = [m["id"] for m in idx["meses"]]
    if mes_id not in existing_ids:
        idx["meses"].insert(0, {"id":mes_id,"label":summary["mes_label"],"periodo":summary["periodo"]})
        upsert("data/index.json", json.dumps(idx, ensure_ascii=False, indent=2), f"Índice: adiciona {mes_id}")
    print("  index.json OK")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    local_mode = "--local" in sys.argv

    print("=" * 60)
    print(f"Dashboard Acionamentos — Atualização automática")
    print(f"Modo: {'LOCAL' if local_mode else 'GITHUB'}")
    print(f"Mês: {MES_ID} | {MES_LABEL}")
    print("=" * 60)

    # Validações básicas
    if not MES_ID:
        print("ERRO: variável MES_ID não definida (ex: 2026-08)")
        sys.exit(1)
    if not MES_LABEL:
        print("ERRO: variável MES_LABEL não definida (ex: Agosto 2026)")
        sys.exit(1)
    if not MES_PERIODO:
        print("ERRO: variável MES_PERIODO não definida (ex: 01–31 ago/2026)")
        sys.exit(1)
    if not SHEET_ANALITICO_URL or not SHEET_VOLUME_URL or not SHEET_MOTIVOS_URL:
        print("ERRO: variáveis SHEET_*_URL não definidas")
        print("Configure os secrets no GitHub ou variáveis de ambiente locais.")
        sys.exit(1)

    print("\n[1/4] Lendo planilhas do Google Sheets...")
    df_an,   ag_list, uf_list = ler_analitico(SHEET_ANALITICO_URL)
    df_vol   = ler_volume(SHEET_VOLUME_URL)
    df_mot   = ler_motivos(SHEET_MOTIVOS_URL)

    print(f"\n[2/4] Calculando agregações ({len(df_an):,} registros)...")
    summary   = montar_summary(df_an, df_vol, df_mot, ag_list, uf_list, MES_ID, MES_LABEL, MES_PERIODO)
    analitico = montar_analitico(df_an)
    print(f"  Total clientes: {summary['total_clientes']:,}")
    print(f"  Acionados: {summary['acionados']:,} ({summary['acionados']/summary['total_clientes']*100:.1f}%)")
    print(f"  Sem acionamento: {summary['sem_acionamento']:,}")

    # Validação mínima antes de commitar
    if summary["total_clientes"] == 0:
        print("ERRO: zero clientes — abortando para não publicar JSON vazio.")
        sys.exit(1)
    if summary["acionados"] / summary["total_clientes"] < 0.5:
        print("AVISO: menos de 50% dos clientes acionados — verifique os dados antes de continuar.")

    print("\n[3/4] Salvando arquivos...")
    if local_mode:
        salvar_local(summary, analitico, MES_ID)
    else:
        salvar_github(summary, analitico, MES_ID)

    print(f"\n[4/4] Concluído! Atualizado em {summary['atualizado_em']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
