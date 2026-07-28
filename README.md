# Dashboard de Acionamentos — Assessoria

Dashboard de acompanhamento de acionamentos com histórico mensal, publicado via GitHub Pages.

## Estrutura do projeto

```
dashboard-acionamentos/
├── index.html                      # Dashboard (não edite os dados aqui)
├── atualizar_dashboard.py          # Script de atualização mensal
├── requirements.txt
├── data/
│   ├── index.json                  # Lista de meses disponíveis
│   ├── 2026-07.json                # Dados resumidos — Julho 2026
│   ├── 2026-07-analitico.json      # Dados individuais — Julho 2026
│   └── ...                         # Próximos meses surgem aqui automaticamente
└── .github/workflows/
    └── atualizar.yml               # Automação mensal
```

## Configuração inicial (faça uma vez)

### 1. Criar o repositório no GitHub

1. Crie um repositório público chamado `dashboard-acionamentos` (ou o nome que preferir)
2. Faça upload de todos estes arquivos (arraste para a interface do GitHub ou use `git push`)

### 2. Habilitar GitHub Pages

1. No repositório → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / pasta: **/ (root)**
4. Salve — em ~1 min o dashboard estará em `https://seu-usuario.github.io/dashboard-acionamentos`

### 3. Habilitar permissão de escrita para o Actions

1. No repositório → **Settings** → **Actions** → **General**
2. Em "Workflow permissions" → marque **Read and write permissions**
3. Salve

### 4. Configurar os Secrets (links do Google Sheets)

1. No repositório → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. Crie os três secrets abaixo:

| Secret               | Valor                                          |
|----------------------|------------------------------------------------|
| `SHEET_ANALITICO_URL`| URL CSV da aba com os dados individuais        |
| `SHEET_VOLUME_URL`   | URL CSV da aba com o volume diário             |
| `SHEET_MOTIVOS_URL`  | URL CSV da aba com o resultado das ligações    |

**Como obter o link CSV:**
1. No Google Sheets → Arquivo → Compartilhar → **Publicar na web**
2. Selecione a aba desejada → formato **Valores separados por vírgula (.csv)**
3. Clique em **Publicar** → copie o link gerado

### 5. Estrutura das abas do Google Sheets

**Aba "Analitico"** (uma linha por cliente):

| CPF | Nome | Tipo | Dias | Saldo | Agrupador | UF | Cidade | QtdAcion | UltimoStatus | StatusFrequente |
|-----|------|------|------|-------|-----------|----|---------|---------:|--------------|-----------------|
| 12345678901 | JOÃO SILVA | F | 45 | 1500,00 | Z ON AZUL PF | PR | CURITIBA | 3 | PP | SM |

- **Tipo**: F (pessoa física) ou J (pessoa jurídica)
- **Saldo**: aceita formato brasileiro (1.234,56) ou americano (1234.56)
- **UltimoStatus / StatusFrequente**: código de 2 letras (NL, NA, PP, SM, etc.)

**Aba "Volume"** (uma linha por dia do mês):

| Dia | Digital | Telefônico | FDS |
|-----|--------:|----------:|-----|
| 01/08 | 7500 | 820 | FALSE |
| 02/08 | 6800 | 910 | FALSE |
| 03/08 | 1200 | 50 | TRUE |

- **FDS**: TRUE para sábados e domingos, FALSE para dias úteis

**Aba "Motivos"** (uma linha por resultado de ligação):

| Resultado | Quantidade | Cor |
|-----------|----------:|-----|
| Não Localizado | 6145 | #DC2626 |
| Atendeu/desligou | 4822 | #EA580C |

- **Cor**: opcional, hex. Se omitido, usa a paleta padrão.

---

## Atualização mensal

### Automática (todo dia 28)

O workflow roda automaticamente todo dia 28 do mês às 8h (BRT). Se quiser mudar o dia, edite o cron em `.github/workflows/atualizar.yml`:

```yaml
- cron: '7 11 28 * *'   # 28 do mês às 11h UTC (8h BRT)
```

### Manual (quando você quiser)

1. No GitHub → aba **Actions** → **Atualizar Dashboard Automaticamente**
2. Clique em **Run workflow**
3. Preencha os campos:
   - **Mês** (ex: `2026-08`)
   - **Nome** (ex: `Agosto 2026`)
   - **Período** (ex: `01–31 ago/2026`)
4. Clique em **Run workflow** → aguarde ~2 minutos

O dashboard é atualizado automaticamente após o workflow concluir.

### Teste local (antes do primeiro deploy)

```bash
pip install -r requirements.txt

export SHEET_ANALITICO_URL="https://docs.google.com/spreadsheets/d/.../pub?..."
export SHEET_VOLUME_URL="https://docs.google.com/spreadsheets/d/.../pub?..."
export SHEET_MOTIVOS_URL="https://docs.google.com/spreadsheets/d/.../pub?..."
export MES_ID="2026-08"
export MES_LABEL="Agosto 2026"
export MES_PERIODO="01–31 ago/2026"

python atualizar_dashboard.py --local
```

Os arquivos serão gravados em `data/` localmente. Abra o dashboard com:

```bash
python -m http.server 8000
# acesse http://localhost:8000
```

> ⚠️ Não abra o `index.html` clicando duas vezes — o navegador bloqueia o `fetch()` no protocolo `file://`. Use sempre o servidor local ou o GitHub Pages.

---

## Histórico de meses

O seletor no canto superior direito do dashboard permite navegar entre meses. Cada mês novo adicionado pelo script aparece automaticamente na lista.

Se precisar adicionar um mês retroativamente, execute o script manual com os parâmetros do mês desejado.

---

## Problemas comuns

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| Dashboard em branco | Cache do navegador | Ctrl+F5 (hard refresh) |
| Dados não atualizam | Workflow não rodou | Verifique a aba Actions; rode manualmente |
| Erro "403" no Sheets | Link de publicação expirou | Re-publique a aba no Sheets |
| Aba Analítico não carrega | JSON muito grande ou CORS | Verifique o tamanho do arquivo em `data/` |
| Workflow falha | Token sem permissão | Settings → Actions → Read and write permissions |
