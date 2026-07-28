# Dashboard de Acionamentos — Assessoria

Dashboard de acompanhamento de acionamentos com histórico mensal, publicado via GitHub Pages.

## Estrutura do projeto

```
dashboard-acionamentos/
├── index.html                      # Dashboard (não edite os dados aqui)
├── atualizar_dashboard.py          # Script de atualização mensal
├── requirements.txt
├── source/
│   ├── 2026-07/
│   │   ├── Carteira.csv            # Carteira de julho
│   │   └── Acionamentos.csv        # Acionamentos de julho
│   ├── 2026-08/
│   │   ├── Carteira.csv
│   │   └── Acionamentos.csv
│   └── ...                         # Próximos meses
├── data/
│   ├── index.json                  # Lista de meses disponíveis
│   ├── 2026-07.json                # Dados resumidos — Julho 2026
│   ├── 2026-07-analitico.json      # Dados individuais — Julho 2026
│   └── ...
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

> Não são necessários secrets: os CSVs ficam diretamente no repositório.

---

## Estrutura dos CSVs

### Carteira.csv (um cliente por linha)

| CPF/CNPJ | Nome | Tipo Pessoa | Agrupador | Dias | Saldo Atual | UF | Cidade | Assessoria |
|----------|------|------------|-----------|-----:|------------:|----|---------|-----------:|
| 12345678901 | JOÃO SILVA | F | Z ON AZUL PF | 45 | 1500,00 | PR | CURITIBA | ZON |

- **Tipo Pessoa**: F (física) ou J (jurídica) — aceita "FÍSICA", "FISICA", etc.
- **Saldo**: formato brasileiro (1.234,56) ou americano (1234.56)
- **Assessoria**: nome da assessoria responsável pelo cliente *(obrigatória a partir de ago/2026; opcional para meses anteriores — usa "Geral" se ausente)*

### Acionamentos.csv (um acionamento por linha)

| Ação | CPF/CNPJ | Data | Motivo Contato | Tipo Motivo | Assessoria |
|------|----------|------|---------------|------------|-----------|
| CONTATO TELEFÔNICO | 12345678901 | 01/07/2026 | Não Localizado | Não Localizado | ZON |
| Ação Digital | 12345678901 | 02/07/2026 | | SMS | ZON |

- **Ação**: "Ação Digital" ou "CONTATO TELEFÔNICO"
- **Motivo Contato**: resultado da ligação (Não Localizado, Promessa de Pagamento, etc.)
- **Tipo Motivo**: categoria do motivo (usado no gráfico de motivos)
- **Assessoria**: assessoria que realizou o acionamento *(opcional; se ausente, usa "Geral")*

---

## Fluxo de atualização mensal

### Passo 1 — Preparar os arquivos

No primeiro dia útil do novo mês:
1. Crie uma pasta no repositório: `source/2026-08/` (substitua pelo mês correto)
2. Coloque dentro dela:
   - `Carteira.csv` — carteira fechada com os dados do mês
   - `Acionamentos.csv` — todos os acionamentos do mês
3. Se você usa assessorias, certifique-se de que a coluna **Assessoria** está presente em ambos os arquivos

### Passo 2 — Fazer upload para o GitHub

Use o **GitHub Desktop** (recomendado para arquivos grandes) ou arraste os arquivos pela interface web do GitHub.

> ⚠️ A interface web do GitHub aceita arquivos até 25 MB. Para arquivos maiores (Acionamentos.csv costuma ter ~50 MB), use o **GitHub Desktop**.

### Passo 3 — Disparar o workflow

**Automático:** o workflow roda todo dia 28 do mês às 8h BRT.

**Manual (quando quiser):**
1. No GitHub → aba **Actions** → **Atualizar Dashboard Automaticamente**
2. Clique em **Run workflow**
3. Preencha:
   - **Mês**: `2026-08`
   - **Nome**: `Agosto 2026`
   - **Período**: `01–31 ago/2026`
4. Clique em **Run workflow** → aguarde ~2 minutos

O dashboard é atualizado automaticamente após o workflow concluir.

---

## Filtros do dashboard

| Filtro | Localização | Efeito |
|--------|-------------|--------|
| **Período** (mês) | Cabeçalho superior direito | Troca todos os dados para o mês selecionado |
| **Assessoria** | Cabeçalho superior (ao lado do período) | Filtra todas as abas para a assessoria selecionada — só aparece quando há mais de uma assessoria nos dados |
| Faixa de atraso, valor, tipo, UF, agrupador, quantidade | Aba Analítico | Filtra a tabela individual de contratos |

---

## Teste local (antes do primeiro deploy)

```bash
pip install -r requirements.txt

# Coloque os CSVs em source/2026-07/
mkdir -p source/2026-07
cp /caminho/Carteira.csv source/2026-07/
cp /caminho/Acionamentos.csv source/2026-07/

export MES_ID="2026-07"
export MES_LABEL="Julho 2026"
export MES_PERIODO="01–27 jul/2026"

python atualizar_dashboard.py --local
```

Os arquivos serão gravados em `data/`. Abra o dashboard com:

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
| Workflow falha com "pasta não encontrada" | CSVs não foram enviados | Faça upload de Carteira.csv e Acionamentos.csv em `source/YYYY-MM/` |
| Arquivo muito grande para upload web | Acionamentos.csv > 25 MB | Use o GitHub Desktop |
| Filtro de assessoria não aparece | Só uma assessoria nos dados | Normal — o filtro aparece quando há ≥ 2 assessorias |
| Workflow falha com "sem permissão de escrita" | Token sem permissão | Settings → Actions → Read and write permissions |
