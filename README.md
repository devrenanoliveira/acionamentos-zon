# Carteira de Cobrança | Acionamentos por Assessoria

Dashboard de acompanhamento de cobertura de acionamentos da carteira Z-ON Card, com histórico mensal navegável e filtro por assessoria (Fácil Resultado, PG+, Decisão), publicado via GitHub Pages.

**URL:** https://devrenanoliveira.github.io/acionamentos-zon/

## Estrutura do projeto

```
acionamentos-zon/
├── index.html                      # Dashboard (não edite os dados aqui)
├── gerar_jsons_acionamentos.py     # Script Python que gera os 3 JSONs a partir dos CSVs
├── atualizar_dashboard.py          # Script de referência (não é o método ativo)
├── requirements.txt
├── data/
│   ├── index.json                  # Lista acumulativa de meses disponíveis
│   ├── 2026-07.json                # Dados agregados — Julho 2026
│   ├── 2026-07-analitico.json      # Dados individuais por cliente — Julho 2026
│   ├── 2026-08.json
│   ├── 2026-08-analitico.json
│   └── ...                         # Um par por mês, nunca sobrescrito
└── .github/workflows/
    └── atualizar.yml               # Existe no repo, mas NÃO é o método ativo (ver abaixo)
```

> Não existem mais pastas `source/YYYY-MM/` com CSVs dentro do repositório. Os CSVs (30–95 MB cada) nunca sobem para o GitHub — só os 3 JSONs processados (~7–8 MB no total).

---

## Como o dashboard é atualizado (processo manual, não automático)

Diferente do que o workflow `.github/workflows/atualizar.yml` sugere, a atualização **não roda sozinha no dia 28**. O fluxo real é:

1. Exportar do sistema Z-ON dois CSVs do período: `Carteira.csv` e `Acionamentos.csv` (os dois são sempre obrigatórios)
2. Processar os CSVs com `gerar_jsons_acionamentos.py` (feito localmente/via Claude, não pelo GitHub Actions) — o script lê o `index.json` atual (para preservar o histórico de meses já publicados) e gera:
   - `YYYY-MM.json` (~9–12 KB) — totais, faixas de atraso/valor, matriz, frequência, volume diário, motivos, breakdown por assessoria
   - `YYYY-MM-analitico.json` (~7–8 MB) — um registro compacto por cliente
   - `index.json` atualizado — acrescenta o mês novo à lista, mantendo os anteriores
3. Subir os 3 arquivos manualmente em `data/` pela interface web do GitHub (**Add file → Upload files**) — GitHub Pages atualiza em ~1 minuto após o commit

Este ciclo pode se repetir **mais de uma vez no mesmo mês** (ex: reexportar a carteira de agosto no meio do mês para refletir a carteira mais recente) — o `YYYY-MM.json` do mês é simplesmente sobrescrito a cada nova exportação; não há um "fechamento" único por mês.

> ⚠️ **Nome do arquivo HTML:** sempre `index.html` (nunca `index_acionamentos.html`) — é o nome que o GitHub Pages espera servir na raiz do repositório.

---

## Estrutura dos CSVs de origem

Os dois CSVs vêm direto da exportação do sistema, com encoding `utf-8-sig`. O script detecta as colunas automaticamente pelo nome (aceita variações de acentuação).

### Carteira.csv (um cliente por linha)

Colunas usadas: `Código`, `CPF/CNPJ`, `Nome`, `Tipo Pessoa` (F/J), `Agrupador`, `Dias`, `Saldo Atual`, `Saldo em Atraso`, `Saldo Contábil`, `Saldo Total em Atraso`, `Situação`, `UF`, `Cidade`, `Score Fatura`, **`Assessorias`** (plural — sempre presente desde ago/2026, quando a carteira passou a ter mais de uma assessoria).

**Regra de saldo composto** (usada em todo o dashboard, inclusive na visão em R$ da aba Carteira): usa `Saldo Contábil` quando > 0; se estiver zerado, cai para `Saldo Total em Atraso` → `Saldo em Atraso` → `Saldo Atual`, nessa ordem.

**Clientes com todos os saldos zerados** não são mais excluídos da carteira (mudança de 11/08/2026) — entram numa faixa própria "Sem atraso" (índice 10), sempre visível, sem distorcer valor (saldo=0) mas contando certo em quantidade/acionamentos.

### Acionamentos.csv (um acionamento por linha)

Colunas usadas: `Ação` ("Ação Digital" ou contém "TEL"/"CONTATO" para telefônico), `Cliente`, `Data`, **`Motivo Contato`** (motivo real do contato — fonte prioritária dos filtros de Canal/Motivo e do gráfico de motivos), `Situação`, `Dias atraso`, `CPF/CNPJ`, **`Assessoria`** (singular — quem executou o contato).

> ⚠️ A coluna correta para os filtros é **"Motivo Contato"**, não "Tipo Motivo" (colunas parecidas, mas "Tipo Motivo" só tem valores genéricos como "Útil"/"Não Útil" — usada por engano em versões anteriores do script).

---

## Faixas de atraso (régua B–J + índices especiais)

| Índice | Label | Critério | Faixa oficial |
|---|---|---|---|
| 0–8 | 1–30d, 31–65d, 66–90d, 91–120d, 121–150d, 151–180d, 181–360d, 361–720d, >720d | dias em atraso | B a J |
| 9 | Acordo | `Situação="Ativo" AND Dias=0 AND Saldo>0` | fora da régua |
| 10 | Sem atraso | `Saldo=0` (quitados recentemente ou em dia, sem acordo formal) | fora da régua |

As faixas 9 e 10 nunca entram na soma de "Pré-Prejuízo (B–G)"/"Loss (H–J)" da aba Carteira, mas aparecem como linha própria em todas as visões (Atraso, Matriz, Carteira). A faixa 9 (Acordo) some das outras abas quando o toggle **🤝 Acordos** está desligado (padrão); a faixa 10 (Sem atraso) não tem toggle — aparece sempre.

---

## Atribuição por assessoria (`by_assessoria`)

Quando há mais de uma assessoria na carteira (caso atual: Fácil, PG+, Decisão), o dashboard mostra um breakdown por assessoria. **Importante:** esse breakdown reflete **quem executou o contato** (coluna `Assessoria` do Acionamentos.csv) cruzado com quem está na carteira daquela assessoria **hoje** — não o CPF isolado.

Isso significa que a soma dos blocos por assessoria não bate exatamente com o total global quando há clientes migrados de uma assessoria para outra no meio do período (o histórico de contato antigo continua marcado com quem fez o contato, não com o dono atual do cliente). É um comportamento esperado, não um bug — já foi tentado trocar essa lógica para filtro só por CPF e revertido, por inflar artificialmente a cobertura de assessorias que receberam clientes migrados.

---

## Filtros e toggles do dashboard

| Filtro/Toggle | Onde | Efeito |
|---|---|---|
| **Período** (mês) | Cabeçalho | Troca todos os dados para o mês selecionado |
| **Assessoria** | Cabeçalho | Filtra todas as abas para uma assessoria — só aparece com 2+ assessorias nos dados |
| **Tipo de Ação / Canal-Motivo** | Barra de filtros (oculta na aba Carteira) | Filtra Analítico e Matriz por linha; Volume só pelo Tipo de Ação; Geral/Atraso/Valor mostram aviso (dados consolidados) |
| **🤝 Acordos** (global) | Barra de filtros | Desligado por padrão — exclui clientes em acordo das métricas de cobertura, em todas as abas exceto Carteira |
| **🤝 Acordo** (local, Analítico) | Aba Analítico | Isola só os clientes em acordo — tem prioridade sobre o toggle global |
| **🔢 Quantidade / 💰 Valor (R$)** | Aba Carteira | Alterna KPIs/gráficos/tabela entre contagem de clientes e soma de saldo |

---

## Layout e visual

Segue o padrão visual dos outros dashboards Z-ON: header navy (`#0F2461`), tab nav (`#1a3680`) com indicador dourado (`#F59E0B`) na aba ativa, modo escuro com persistência via `localStorage`, sem frameworks (HTML/CSS/JS puro + Chart.js via CDN).

**Cabeçalho fixo + rolagem independente (desde 13/08/2026):** header, abas, barra de filtros e a linha "Período · N clientes · Atualizado em: dd/mm/aaaa HH:MM" ficam permanentemente visíveis no topo — só o conteúdo de cada aba rola, dentro de uma área própria (`#scroll-area`). Isso evita que gráficos/cards fiquem cortados ou sobrepostos pela barra de filtros ao rolar a página.

---

## Teste local

`fetch()` é bloqueado pelo navegador em `file://` — nunca abra o `index.html` clicando duas vezes. Para testar antes de subir:

```bash
python3 gerar_jsons_acionamentos.py   # gera os 3 JSONs na pasta atual, a partir dos CSVs locais
mkdir -p data && cp 2026-*.json index.json data/
python3 -m http.server 8000
# acesse http://localhost:8000
```

---

## Problemas comuns

| Problema | Causa provável | Solução |
|---|---|---|
| Dashboard em branco / dados antigos | Cache do navegador ou do GitHub Pages | Ctrl+F5 (hard refresh); aguardar ~1 min após o commit |
| `index.json` perdeu um mês antigo | Script rodou sem o `index.json` existente do GitHub na pasta | Sempre baixar (ou buscar via `raw.githubusercontent.com`) o `index.json` atual antes de rodar o script |
| Script encerra com erro | Falta `Carteira.csv` ou `Acionamentos.csv` na pasta | Os dois são obrigatórios — confirmar que ambos estão na mesma pasta do script |
| Filtro de assessoria não aparece | Só uma assessoria nos dados daquele mês | Normal — aparece automaticamente com 2+ assessorias |
| Números de `by_assessoria` não batem com o total global | Clientes migraram de assessoria no meio do período | Comportamento esperado — ver seção "Atribuição por assessoria" acima |
| `SyntaxError: Failed to execute 'close'...` no preview do Claude | Sem os JSONs locais em `data/`, o fetch cai num 404 | Funciona normalmente publicado no GitHub Pages |

---

*README atualizado em 14/08/2026 para refletir o fluxo real do projeto (processamento manual via Claude + upload de 3 JSONs, sem workflow automático ativo).*
