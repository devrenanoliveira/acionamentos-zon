"""
atualizar_dashboard.py
======================
Script de atualização do Dashboard de Acionamentos.

Fontes de dados (CSVs locais no repositório):
  source/
    2026-07/
      Carteira.csv        # Dados da carteira (um cliente por linha)
      Acionamentos.csv    # Log de acionamentos (um contato por linha)
    2026-08/
      Carteira.csv
      Acionamentos.csv
    ...

Colunas esperadas em Carteira.csv:
  CPF/CNPJ, Nome, Tipo Pessoa, Agrupador, Dias, Saldo Atual, UF, Cidade
  [Assessoria]  ← opcional; obrigatória a partir de ago/2026

Colunas esperadas em Acionamentos.csv:
  Ação, CPF/CNPJ, Data, Motivo Contato, Tipo Motivo
  [Assessoria]  ← opcional; obrigatória a partir de ago/2026

Ação: "Ação Digital" → digital  |  "CONTATO TELEFÔNICO" → telefônico

Como executar localmente (teste antes do deploy):
  export MES_ID="2026-07"
  export MES_LABEL="Julho 2026"
  export MES_PERIODO="01–27 jul/2026"
  python atualizar_dashboard.py --local

Para subir ao GitHub automaticamente (via Actions), basta fazer commit
dos CSVs em source/YYYY-MM/ e disparar o workflow.
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timezone, timedelta, date

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════

MES_LABEL   = os.environ.get("MES_LABEL", "")    # ex: "Agosto 2026"
MES_PERIODO = os.environ.get("MES_PERIODO", "")   # ex: "01–31 ago/2026"
MES_ID      = os.environ.get("MES_ID", "")        # ex: "2026-08"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME    = os.environ.get("GITHUB_REPOSITORY", "")

BRT = timezone(timedelta(hours=-3))

# Pasta raiz dos arquivos-fonte (relativa ao repositório)
SOURCE_ROOT = "source"

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
    "Nao Localizado":    "#DC2626",
    "Não localizado":    "#DC2626",
    "Atendeu/desligou":  "#EA580C",
    "Atendeu e desligou":"#EA580C",
    "Não atendeu":       "#D97706",
    "Nao atendeu":       "#D97706",
    "Promessa de pgto":  "#059669",
    "Promessa de Pagamento": "#059669",
    "Recado":            "#7C3AED",
    "Sem cond. fin.":    "#64748B",
    "Sem Condições Financeiras": "#64748B",
    "Reagendado":        "#1D4ED8",
    "Sem int. pagar":    "#991B1B",
    "Sem Interesse em Pagar": "#991B1B",
    "Desempregado":      "#D97706",
    "Alega Pagamento":   "#059669",
    "Desconhece Dívida": "#9A3412",
    "Desconhece Divida": "#9A3412",
    "Falecido":          "#94A3B8",
    "Ação Digital":      "#1D4ED8",
    "Acao Digital":      "#1D4ED8",
}

# Mapeamento de texto de motivo/situação → código de 2 letras
MOTIVO_PARA_CODIGO = {
    "não localizado":             "NL",
    "nao localizado":             "NL",
    "não atendeu":                "NA",
    "nao atendeu":                "NA",
    "atendeu/desligou":           "AD",
    "atendeu e desligou":         "AD",
    "cliente atendeu e desligou": "AD",
    "promessa de pagamento":      "PP",
    "promessa de pgto":           "PP",
    "recado":                     "RC",
    "sem condições financeiras":  "SF",
    "sem cond. fin.":             "SF",
    "sem condicoes financeiras":  "SF",
    "reagendado":                 "RE",
    "sem interesse em pagar":     "SI",
    "sem int. pagar":             "SI",
    "alega pagamento":            "AP",
    "desempregado":               "DE",
    "desconhece dívida":          "DD",
    "desconhece divida":          "DD",
    "falecido":                   "FA",
    "sms":                        "SM",
    "whatsapp":                   "SM",
    "envio de sms":               "SM",
    "envio de sms/whatsapp":      "SM",
    "ação digital":               "SM",
    "acao digital":               "SM",
    "digital":                    "SM",
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
# UTILIDADES
# ═══════════════════════════════════════════════════════════════

def limpar_valor_br(v):
    """Converte 'R$ 1.234,56' ou '1234.56' → 1234.56"""
    if pd.isna(v): return 0.0
    s = str(v).strip().replace("R$","").replace(" ","")
    # Formato brasileiro: 1.234,56
    if "," in s and "." in s:
        s = s.replace(".","").replace(",",".")
    elif "," in s:
        s = s.replace(",",".")
    try:
        return float(s)
    except:
        return 0.0

def normalizar_cpf(v):
    if pd.isna(v): return ""
    return str(v).strip().replace(".","").replace("-","").replace("/","").strip()

def normalizar_cols(df):
    """Normaliza nomes de colunas: lowercase + sem acentos básicos."""
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ","_")
        .str.replace("/","_")
        .str.replace("ç","c")
        .str.replace("ã","a")
        .str.replace("â","a")
        .str.replace("á","a")
        .str.replace("à","a")
        .str.replace("é","e")
        .str.replace("ê","e")
        .str.replace("í","i")
        .str.replace("ó","o")
        .str.replace("ô","o")
        .str.replace("ú","u")
    )
    return df

def motivo_para_codigo(texto):
    """Converte texto de motivo para código de 2 letras."""
    if pd.isna(texto) or str(texto).strip() in ("", "-"): return "-"
    t = str(texto).strip().lower()
    # Verificar se já é um código de 2 letras
    t2 = str(texto).strip().upper()
    if t2 in STATUS_LABEL:
        return t2
    return MOTIVO_PARA_CODIGO.get(t, t2[:2] if len(t2) >= 2 else "-")


# ═══════════════════════════════════════════════════════════════
# LEITURA DOS CSVs
# ═══════════════════════════════════════════════════════════════

def ler_carteira(pasta):
    """Lê Carteira.csv e retorna DataFrame normalizado."""
    caminho = os.path.join(pasta, "Carteira.csv")
    print(f"  Lendo {caminho}...")
    df = pd.read_csv(caminho, low_memory=False)
    df = normalizar_cols(df)
    print(f"    {len(df):,} linhas · colunas: {list(df.columns)}")

    # Mapeamento flexível de colunas
    alias = {
        "cpf_cnpj": "cpf", "cnpj": "cpf",
        "nome": "nome",
        "tipo_pessoa": "tipo",
        "agrupador": "agrupador",
        "dias": "dias",
        "dias_atraso": "dias",
        "maior_atraso": "dias",
        "saldo_atual": "saldo",
        "saldo_contabil": "saldo",
        "saldo_em_atraso": "saldo",
        "saldo_total_em_atraso": "saldo",
        "uf": "uf",
        "cidade": "cidade",
        "assessoria": "assessoria",
    }
    df = df.rename(columns={c: alias[c] for c in df.columns if c in alias})

    # Garantir colunas mínimas
    for col, default in [("tipo","F"),("agrupador",""),("uf",""),("cidade",""),("assessoria","Geral")]:
        if col not in df.columns:
            df[col] = default

    # Limpeza
    df["cpf"]       = df["cpf"].apply(normalizar_cpf).str.zfill(11)
    df["nome"]      = df["nome"].fillna("").astype(str).str.strip().str.upper()
    df["tipo"]      = df["tipo"].fillna("F").astype(str).str.strip().str.upper()
    # Normalizar tipo: "FÍSICA", "FISICA" → F; "JURÍDICA", "JURIDICA" → J
    df["tipo"]      = df["tipo"].map(lambda t: "J" if t.startswith("J") else "F")
    df["agrupador"] = df["agrupador"].fillna("").astype(str).str.strip()
    df["uf"]        = df["uf"].fillna("").astype(str).str.upper().str.strip()
    df["cidade"]    = df["cidade"].fillna("").astype(str).str.upper().str.strip()
    df["assessoria"]= df["assessoria"].fillna("Geral").astype(str).str.strip()
    df["saldo"]     = df["saldo"].apply(limpar_valor_br) if "saldo" in df.columns else 0.0
    df["dias"]      = pd.to_numeric(df.get("dias", 0), errors="coerce").fillna(0).astype(int)

    return df


def ler_acionamentos(pasta):
    """Lê Acionamentos.csv e retorna DataFrame normalizado."""
    caminho = os.path.join(pasta, "Acionamentos.csv")
    print(f"  Lendo {caminho}...")
    df = pd.read_csv(caminho, low_memory=False)
    df = normalizar_cols(df)
    print(f"    {len(df):,} linhas · colunas: {list(df.columns)}")

    alias = {
        "cpf_cnpj": "cpf", "cnpj": "cpf",
        "acao": "acao", "tipo_acao": "acao",
        "data": "data",
        "horario": "horario",
        "motivo_contato": "motivo_contato",
        "tipo_motivo": "tipo_motivo",
        "situacao": "situacao",
        "assessoria": "assessoria",
        "responsavel": "responsavel",
        "cliente": "cliente",
    }
    df = df.rename(columns={c: alias[c] for c in df.columns if c in alias})

    for col, default in [("acao",""),("data",""),("horario",""),
                          ("motivo_contato",""),("tipo_motivo",""),
                          ("situacao",""),("assessoria","Geral")]:
        if col not in df.columns:
            df[col] = default

    df["cpf"]           = df["cpf"].apply(normalizar_cpf).str.zfill(11)
    df["acao"]          = df["acao"].fillna("").astype(str).str.strip()
    df["data"]          = df["data"].fillna("").astype(str).str.strip()
    df["horario"]       = df["horario"].fillna("").astype(str).str.strip()
    df["motivo_contato"]= df["motivo_contato"].fillna("").astype(str).str.strip()
    df["tipo_motivo"]   = df["tipo_motivo"].fillna("").astype(str).str.strip()
    df["assessoria"]    = df["assessoria"].fillna("Geral").astype(str).str.strip()

    # Classificar ação
    df["is_digital"] = df["acao"].str.contains("digital", case=False, na=False)
    df["is_tel"]     = df["acao"].str.contains("tel", case=False, na=False) | \
                       df["acao"].str.contains("contato", case=False, na=False)

    return df


def mesclar_dados(df_carteira, df_acion):
    """
    Junta Carteira com Acionamentos para gerar o DataFrame de análise por cliente.
    Calcula: QtdAcion, UltimoStatus, StatusFrequente para cada CPF.
    """
    # Quantidade de acionamentos por CPF
    qtd = df_acion.groupby("cpf").size().rename("qtd_acion")

    # Último status: ordenar por data+horario e pegar o último
    df_sorted = df_acion.copy()
    df_sorted["_ordem"] = df_sorted["data"].astype(str) + " " + df_sorted["horario"].astype(str)
    df_sorted = df_sorted.sort_values("_ordem")

    # Determinar campo de status: prioridade: motivo_contato > tipo_motivo > situacao
    def get_status_field(row):
        for field in ["motivo_contato", "tipo_motivo", "situacao"]:
            val = row.get(field, "")
            if val and str(val).strip() not in ("", "-", "nan"):
                return str(val).strip()
        return "-"

    df_sorted["_status_raw"] = df_sorted.apply(get_status_field, axis=1)
    df_sorted["_status_cod"] = df_sorted["_status_raw"].map(motivo_para_codigo)

    # Digital acionamentos → status = SM
    df_sorted.loc[df_sorted["is_digital"] & (df_sorted["_status_cod"] == "-"), "_status_cod"] = "SM"

    ultimo = df_sorted.groupby("cpf")["_status_cod"].last()
    frequente = df_sorted.groupby("cpf")["_status_cod"].agg(
        lambda x: x.mode()[0] if len(x) > 0 else "-"
    )

    # Merge com carteira
    df = df_carteira.copy()
    df = df.join(qtd, on="cpf", how="left")
    df = df.join(ultimo.rename("ultimo_status"), on="cpf", how="left")
    df = df.join(frequente.rename("status_frequente"), on="cpf", how="left")

    df["qtd_acion"]       = df["qtd_acion"].fillna(0).astype(int)
    df["ultimo_status"]   = df["ultimo_status"].fillna("-").astype(str)
    df["status_frequente"]= df["status_frequente"].fillna("-").astype(str)

    # Índices derivados
    df["fa"] = df["dias"].apply(faixa_atraso)
    df["fv"] = df["saldo"].apply(faixa_valor)

    ag_list = sorted(df["agrupador"].unique().tolist())
    uf_list = sorted(df["uf"].unique().tolist())
    as_list = sorted(df["assessoria"].unique().tolist())

    ag_map = {a: i for i, a in enumerate(ag_list)}
    uf_map = {u: i for i, u in enumerate(uf_list)}
    as_map = {a: i for i, a in enumerate(as_list)}

    df["ag_idx"] = df["agrupador"].map(ag_map)
    df["uf_idx"] = df["uf"].map(uf_map)
    df["as_idx"] = df["assessoria"].map(as_map)

    return df, ag_list, uf_list, as_list


def calcular_volume(df_acion):
    """
    Calcula volume diário de acionamentos por canal.
    Retorna lista de {dia, digital, tel, fds}.
    """
    if df_acion["data"].empty or df_acion["data"].str.strip().eq("").all():
        return []

    # Tentar parsear a data (aceita DD/MM/YYYY ou YYYY-MM-DD)
    def parse_data(s):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(str(s).strip(), fmt).date()
            except:
                pass
        return None

    df = df_acion.copy()
    df["_data"] = df["data"].apply(parse_data)
    df = df.dropna(subset=["_data"])

    if df.empty:
        return []

    grouped = df.groupby("_data").agg(
        digital=("is_digital", "sum"),
        tel=("is_tel", "sum")
    ).reset_index()
    grouped = grouped.sort_values("_data")

    vol = []
    for _, row in grouped.iterrows():
        d = row["_data"]
        vol.append({
            "dia": d.strftime("%d/%m"),
            "digital": int(row["digital"]),
            "tel": int(row["tel"]),
            "fds": d.weekday() >= 5  # 5=sáb, 6=dom
        })
    return vol


def calcular_motivos(df_acion):
    """
    Calcula distribuição dos motivos nos acionamentos telefônicos.
    Usa tipo_motivo se disponível, senão motivo_contato.
    Retorna lista de {name, value, color}.
    """
    df_tel = df_acion[df_acion["is_tel"]].copy()
    if df_tel.empty:
        return []

    # Usar tipo_motivo se tiver valores, senão motivo_contato
    col = "tipo_motivo" if df_tel["tipo_motivo"].str.strip().ne("").any() else "motivo_contato"
    counts = df_tel[col].str.strip().value_counts()

    motivos = []
    for nome, qtd in counts.items():
        if not nome or nome == "" or nome.lower() == "nan":
            continue
        cor = MOTIVOS_COLORS.get(nome, "#94A3B8")
        motivos.append({"name": str(nome), "value": int(qtd), "color": cor})
    return motivos


# ═══════════════════════════════════════════════════════════════
# CÁLCULO DAS AGREGAÇÕES
# ═══════════════════════════════════════════════════════════════

def calcular_atraso(df):
    rows = []
    for i, label in enumerate(FA_LABELS):
        sub   = df[df["fa"] == i]
        total = len(sub)
        acion = int((sub["qtd_acion"] > 0).sum())
        nao   = total - acion
        pct   = round(acion / total * 100, 1) if total > 0 else 0.0
        rows.append({"id":i,"label":label,"total":int(total),"acion":acion,"nao":int(nao),"pct":pct})
    return rows

def calcular_valor(df):
    rows = []
    for i, label in enumerate(FV_LABELS):
        sub   = df[df["fv"] == i]
        total = len(sub)
        if total == 0: continue
        acion = int((sub["qtd_acion"] > 0).sum())
        nao   = total - acion
        pct   = round(acion / total * 100, 1)
        rows.append({"id":i,"label":label,"total":int(total),"acion":acion,"nao":int(nao),"pct":pct})
    return rows

def calcular_matrix(df):
    matrix = []
    for ai in range(len(FA_LABELS)):
        row = []
        for vi in range(len(FV_LABELS)):
            sub   = df[(df["fa"]==ai) & (df["fv"]==vi)]
            total = len(sub)
            nao   = int((sub["qtd_acion"]==0).sum())
            row.append([nao, int(total)])
        matrix.append(row)
    return matrix

def calcular_freq(df):
    buckets = [(0,"0","Sem contato"),(1,"1","1 contato"),(2,"2","2 contatos"),
               (3,"3","3 contatos"),(4,"4","4 contatos"),(5,"5","5 contatos"),(-1,"6+","6+ contatos")]
    rows = []
    for val, n, label in buckets:
        v = int((df["qtd_acion"]>=6).sum()) if val == -1 else int((df["qtd_acion"]==val).sum())
        rows.append({"n":n,"label":label,"v":v})
    return rows

def agregar_metricas(df, df_acion):
    """Agrega métricas para um subconjunto de dados (global ou por assessoria)."""
    total   = len(df)
    acionados    = int((df["qtd_acion"] > 0).sum())
    sem_acion    = total - acionados
    com_promessa = int(((df["ultimo_status"]=="PP") | (df["status_frequente"]=="PP")).sum())
    vol     = calcular_volume(df_acion)
    total_digital = sum(v["digital"] for v in vol)
    total_tel     = sum(v["tel"] for v in vol)
    total_acion   = total_digital + total_tel
    atraso  = calcular_atraso(df)
    max_nao = max((r["nao"] for r in atraso if r["nao"] > 0), default=1)
    motivos = calcular_motivos(df_acion)

    return {
        "total_clientes":    total,
        "acionados":         acionados,
        "sem_acionamento":   sem_acion,
        "com_promessa":      com_promessa,
        "total_acionamentos": total_acion,
        "total_tel":         total_tel,
        "max_nao":           max_nao,
        "atraso":            atraso,
        "valor":             calcular_valor(df),
        "matrix":            calcular_matrix(df),
        "freq":              calcular_freq(df),
        "motivos":           motivos,
        "volume":            vol,
    }


# ═══════════════════════════════════════════════════════════════
# MONTAR JSON FINAL
# ═══════════════════════════════════════════════════════════════

def montar_summary(df, df_acion, ag_list, uf_list, as_list, mes_id, mes_label, mes_periodo):
    now = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")

    # Métricas globais
    global_m = agregar_metricas(df, df_acion)

    # Métricas por assessoria
    by_assessoria = {}
    if len(as_list) > 1:  # só se houver mais de uma assessoria
        for i, ass in enumerate(as_list):
            df_as     = df[df["assessoria"] == ass]
            df_ac_as  = df_acion[df_acion["assessoria"] == ass]
            by_assessoria[str(i)] = agregar_metricas(df_as, df_ac_as)

    summary = {
        "periodo":        mes_periodo,
        "mes_label":      mes_label,
        "fa_labels":      FA_LABELS,
        "fv_labels":      FV_LABELS,
        "ag_list":        ag_list,
        "uf_list":        uf_list,
        "assessoria_list": as_list,
        "by_assessoria":  by_assessoria,
        "status_label":   STATUS_LABEL,
        "atualizado_em":  now,
    }
    summary.update(global_m)  # inclui todas as métricas globais no nível raiz
    return summary


def montar_analitico(df):
    """
    Converte DataFrame para array de arrays compactos.
    Estrutura: [CPF, Nome, Tipo, Dias, fa_idx, Saldo, fv_idx, ag_idx, uf_idx, Cidade, QtdAcion, UltimoStatus, StatusFrequente, as_idx]
    """
    records = []
    for _, r in df.iterrows():
        records.append([
            str(r["cpf"]),
            str(r["nome"]),
            str(r["tipo"]),
            int(r["dias"]),
            int(r["fa"]),
            round(float(r["saldo"]), 2),
            int(r["fv"]),
            int(r["ag_idx"]),
            int(r["uf_idx"]),
            str(r["cidade"]),
            int(r["qtd_acion"]),
            str(r["ultimo_status"]),
            str(r["status_frequente"]),
            int(r["as_idx"]),
        ])
    return records


# ═══════════════════════════════════════════════════════════════
# GRAVAÇÃO — LOCAL ou GITHUB
# ═══════════════════════════════════════════════════════════════

def salvar_local(summary, analitico, mes_id):
    os.makedirs("data", exist_ok=True)

    path_sum = f"data/{mes_id}.json"
    path_an  = f"data/{mes_id}-analitico.json"

    with open(path_sum, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
    print(f"  {path_sum} salvo ({os.path.getsize(path_sum)//1024} KB)")

    with open(path_an, "w", encoding="utf-8") as f:
        json.dump(analitico, f, ensure_ascii=False)
    print(f"  {path_an} salvo ({os.path.getsize(path_an)//1024//1024} MB aprox.)")

    # Atualizar index.json
    index_path = "data/index.json"
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
    else:
        idx = {"meses": []}

    existing_ids = [m["id"] for m in idx["meses"]]
    if mes_id not in existing_ids:
        idx["meses"].insert(0, {
            "id":     mes_id,
            "label":  summary["mes_label"],
            "periodo": summary["periodo"]
        })
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        print(f"  data/index.json atualizado")
    else:
        print(f"  data/index.json: mês {mes_id} já estava no índice")


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

    summary_str   = json.dumps(summary, ensure_ascii=False)
    analitico_str = json.dumps(analitico, ensure_ascii=False)

    upsert(f"data/{mes_id}.json",           summary_str,   f"Atualização {mes_id} — {now_str}")
    upsert(f"data/{mes_id}-analitico.json", analitico_str, f"Analítico {mes_id} — {now_str}")

    try:
        idx_file = repo.get_contents("data/index.json")
        idx = json.loads(idx_file.decoded_content.decode("utf-8"))
    except:
        idx = {"meses": []}

    existing_ids = [m["id"] for m in idx["meses"]]
    if mes_id not in existing_ids:
        idx["meses"].insert(0, {
            "id":     mes_id,
            "label":  summary["mes_label"],
            "periodo": summary["periodo"]
        })
        upsert("data/index.json",
               json.dumps(idx, ensure_ascii=False, indent=2),
               f"Índice: adiciona {mes_id}")
    print("  index.json OK")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    local_mode = "--local" in sys.argv

    print("=" * 60)
    print("Dashboard Acionamentos — Atualização automática")
    print(f"Modo: {'LOCAL' if local_mode else 'GITHUB'}")
    print(f"Mês: {MES_ID} | {MES_LABEL}")
    print("=" * 60)

    # Validações
    if not MES_ID:
        print("ERRO: variável MES_ID não definida (ex: 2026-08)")
        sys.exit(1)
    if not MES_LABEL:
        print("ERRO: variável MES_LABEL não definida (ex: Agosto 2026)")
        sys.exit(1)
    if not MES_PERIODO:
        print("ERRO: variável MES_PERIODO não definida (ex: 01–31 ago/2026)")
        sys.exit(1)

    pasta = os.path.join(SOURCE_ROOT, MES_ID)
    if not os.path.isdir(pasta):
        print(f"ERRO: pasta '{pasta}' não encontrada.")
        print(f"  Crie a pasta e coloque Carteira.csv e Acionamentos.csv dentro dela.")
        sys.exit(1)
    for f in ["Carteira.csv", "Acionamentos.csv"]:
        if not os.path.exists(os.path.join(pasta, f)):
            print(f"ERRO: arquivo '{pasta}/{f}' não encontrado.")
            sys.exit(1)

    print(f"\n[1/4] Lendo CSVs de '{pasta}'...")
    df_carteira = ler_carteira(pasta)
    df_acion    = ler_acionamentos(pasta)

    print(f"\n[2/4] Mesclando e calculando agregações...")
    df, ag_list, uf_list, as_list = mesclar_dados(df_carteira, df_acion)
    print(f"  Clientes: {len(df):,}")
    print(f"  Agrupadores: {len(ag_list)}")
    print(f"  UFs: {len(uf_list)}")
    print(f"  Assessorias: {as_list}")

    summary   = montar_summary(df, df_acion, ag_list, uf_list, as_list, MES_ID, MES_LABEL, MES_PERIODO)
    analitico = montar_analitico(df)

    total = summary["total_clientes"]
    acion = summary["acionados"]
    print(f"  Total clientes: {total:,}")
    print(f"  Acionados: {acion:,} ({acion/total*100:.1f}%)")
    print(f"  Sem acionamento: {summary['sem_acionamento']:,}")
    if summary.get("by_assessoria"):
        for i, ass in enumerate(as_list):
            ba = summary["by_assessoria"].get(str(i), {})
            print(f"  [{ass}] {ba.get('total_clientes',0):,} clientes, {ba.get('acionados',0):,} acionados")

    # Validação mínima
    if total == 0:
        print("ERRO: zero clientes — abortando para não publicar JSON vazio.")
        sys.exit(1)
    if acion / total < 0.5:
        print("AVISO: menos de 50% dos clientes acionados — verifique os dados.")

    print(f"\n[3/4] Salvando arquivos...")
    if local_mode:
        salvar_local(summary, analitico, MES_ID)
    else:
        salvar_github(summary, analitico, MES_ID)

    print(f"\n[4/4] Concluído! Atualizado em {summary['atualizado_em']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
