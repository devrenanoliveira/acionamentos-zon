# Carteira de Cobrança | Acionamentos por Assessoria

Dashboard de acompanhamento de cobertura de acionamentos da carteira Z-ON Card, com histórico mensal navegável, filtro por assessoria (Fácil Resultado, PG+, Decisão) e um modelo de priorização (Collection Score), publicado via GitHub Pages.

**URL:** https://devrenanoliveira.github.io/acionamentos-zon/

## Abas do dashboard

| Aba | Conteúdo |
|---|---|
| **Carteira** (padrão) | Composição da carteira em 10 sub-abas: Faixas de Atraso, Faixas de Valor, Segmentos, Gênero, Faixa Etária, Categoria Profissão, Faixa de Renda, Score Fatura, Carteira Interna e 🏢 Colaboradores — todas com composição + cobertura de acionamento e toggle 🔢 Quantidade / 💰 Valor (R$) |
| **Visão Geral** | KPIs gerais, cobertura (donut), frequência de acionamentos, motivos telefônicos |
| **Por Atraso** / **Por Valor** | Cobertura e breakdown por faixa, com drill cruzado entre as duas |
| **Matriz** | Cruzamento atraso × valor (não acionados / acionados / % cobertura), com cards de resumo e insight automático apontando o cruzamento prioritário |
| **Volume** | Volume diário por canal (digital/telefônico), filtrável por Tipo de Ação e Canal/Motivo |
| **Analítico** | Tabela individual por cliente, carregada sob demanda, com exportação Excel |
| **🎯 Collection Score** | Aba de destaque com duas sub-abas — **📋 Lista Priorizada** (modelo estatístico de priorização) e **📊 Esperado x Realizado** (calibração vs. validação por coorte, com toggle Collection Score/Propensão de Pagamento) — ver seção dedicada abaixo |

## Estrutura do projeto

```
acionamentos-zon/
├── index.html                      # Dashboard (não edite os dados aqui)
├── gerar_jsons_acionamentos.py     # Script Python de referência/prototipagem — ver "Como é atualizado" abaixo
├── atualizar_dashboard.py          # Script antigo, não é o método ativo
├── requirements.txt
├── data/
│   ├── index.json                       # Lista acumulativa de meses disponíveis
│   ├── collection_band_history.json     # Coortes do Collection Score (pendentes/resolvidas) — ver seção Collection Score
│   ├── propensao_band_history.json      # Coortes da Propensão de Pagamento (pendentes/resolvidas) — mesma mecânica
│   ├── 2026-07.json                     # Dados agregados — Julho 2026
│   ├── 2026-07-analitico.json           # Dados individuais por cliente — Julho 2026
│   ├── 2026-08.json
│   ├── 2026-08-analitico.json
│   └── ...                              # Um par por mês, nunca sobrescrito
└── .github/workflows/
    └── atualizar.yml               # Existe no repo, mas NÃO é o método ativo (ver abaixo)
```

> Não existem mais pastas `source/YYYY-MM/` com CSVs dentro do repositório. Os CSVs (30–95 MB cada) nunca sobem para o GitHub — só os JSONs processados (~7–8 MB no total).

---

## Como o dashboard é atualizado (processo manual, não automático)

Diferente do que o workflow `.github/workflows/atualizar.yml` sugere, a atualização **não roda sozinha no dia 28**. E, ao contrário do que uma versão anterior deste README chegou a afirmar, o **Motor Único** (`motor_zon.py` — projeto separado, fora deste repositório, que gera o `data.json` do dashboard irmão de KPIs) **não participa da geração deste dashboard**: leitura direta do script confirmou que não existe nenhuma linha de código de Acionamentos/Collection Score nele. Todo o dado publicado aqui — carteira, cobertura, Collection Score, Propensão de Pagamento, Esperado x Realizado, Colaboradores — vem 100% do `gerar_jsons_acionamentos.py` deste repositório, rodado localmente e commitado direto.

Na prática, o fluxo de uma atualização é:

1. Exportar do sistema Z-ON os CSVs do período: Carteira e Acionamentos são sempre obrigatórios; `Recuperação AAAA.csv` (histórico multi-ano de pagamentos) é opcional, necessário só para a Propensão de Pagamento calcular; uma planilha `.xlsx` com "colaborador" no nome é opcional, para a marcação de Colaboradores. Desde 25/08/2026 os dois CSVs obrigatórios **não precisam mais ser renomeados** — o sistema devolve ambos como `RELATORIO_<id>.csv` e o script identifica qual é qual pelo cabeçalho (colunas exclusivas de cada relatório), não pelo nome do arquivo.
2. Processar os CSVs (localmente/via Claude, não pelo GitHub Actions) — o script lê o `index.json`, o `collection_band_history.json` e o `propensao_band_history.json` atuais (para preservar o histórico de meses e de coortes já publicados) e gera:
   - `YYYY-MM.json` (~9–70 KB) — totais, faixas de atraso/valor, matriz, frequência, volume diário, motivos, breakdown por assessoria, metadados do Collection Score/Propensão/Esperado x Realizado (dos dois modelos)
   - `YYYY-MM-analitico.json` (~7–10 MB) — um registro compacto por cliente
   - `index.json` atualizado — acrescenta o mês novo à lista, mantendo os anteriores
   - `collection_band_history.json` atualizado — acrescenta/resolve coortes do Collection Score (ver seção abaixo)
   - `propensao_band_history.json` atualizado — mesma mecânica, coortes da Propensão de Pagamento
3. Subir os arquivos manualmente em `data/` pela interface web do GitHub (**Add file → Upload files**) — GitHub Pages atualiza em ~1 minuto após o commit

Este ciclo pode se repetir **mais de uma vez no mesmo mês** (ex: reexportar a carteira de agosto no meio do mês para refletir a carteira mais recente) — o `YYYY-MM.json` do mês é simplesmente sobrescrito a cada nova exportação; não há um "fechamento" único por mês.

> ⚠️ **Nome do arquivo HTML:** sempre `index.html` (nunca `index_acionamentos.html`) — é o nome que o GitHub Pages espera servir na raiz do repositório.
>
> ⚠️ **Antes de rodar `gerar_jsons_acionamentos.py`**, sempre baixar o `index.json`, o `collection_band_history.json` **e** o `propensao_band_history.json` atuais do GitHub para a pasta de trabalho — sem eles, o histórico de meses e as coortes de Collection Score/Propensão pendentes de maturação são perdidos.

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

Um campo relacionado, `qtd_own` (analítico), existe porque o filtro "Sem acionamento" do Analítico usava a quantidade global de acionamentos do cliente mesmo com uma assessoria filtrada — divergindo da Matriz sempre que o cliente migrou de assessoria. `qtd_own` conta só o que a assessoria atual do cliente executou; é o que os filtros por-assessoria devem usar.

---

## Collection Score, Propensão de Pagamento e Esperado x Realizado

A aba **🎯 Collection Score** reúne três funcionalidades baseadas em modelos estatísticos (não em contagem direta dos CSVs, como o resto do dashboard):

### Collection Score (sub-aba 📋 Lista Priorizada)

Lista de clientes priorizados por um modelo de regressão logística treinado a cada rodada sobre a própria carteira do mês, prevendo `is_acordo` (cliente com acordo formal ativo) como proxy. Gera um score em percentil (0–100) e uma banda A–D (A = maior propensão).

- **Não é o Score Fatura oficial** e pode até divergir dele — nos dados observados, o Score Fatura médio de quem está em acordo é mais baixo que o de quem não está (perfis de maior risco são mais empurrados para renegociação formal). Um aviso fixo nesse sentido aparece na aba.
- Features: idade, Score Fatura, renda, saldo (log), categoria profissão, sexo, agrupador (Carteira Interna), UF. **Deliberadamente sem** `Dias`/`Situação`/quantidade de acionamentos — os dois primeiros tornariam o modelo tautológico (são a própria definição do alvo); a quantidade de acionamentos foi testada, aumentava bastante o poder preditivo do modelo mas concentrava quase toda a carteira sem nenhum contato numa única banda, duplicando um filtro que já existe na tabela — removida deliberadamente.
- Só treina com amostra mínima (≥30 casos positivos e negativos); abaixo disso, ou sem `scikit-learn` instalado, a aba fica com aviso "mês sem dado calculado".

### Propensão de Pagamento (30 dias)

Modelo separado (não substitui o Collection Score, roda em paralelo), baseado em **histórico real de pagamento** — não em status de carteira. Precisa de um ou mais arquivos `Recuperação AAAA.csv` (histórico multi-ano de pagamentos por CPF) na mesma pasta do script; sem eles, essa métrica simplesmente não aparece (ausência por falta de arquivo, não por período de espera). Gera um score e banda A–D próprios, exibidos lado a lado com o Collection Score, incluindo um card cruzando quem é banda A nos dois modelos ao mesmo tempo.

### Esperado x Realizado (sub-aba 📊)

Mede se as bandas dos modelos realmente convertem — hoje disponível para os **dois** modelos, alternável por um toggle dentro da sub-aba (🎯 Collection Score / 💰 Propensão de Pagamento): "Esperado" é calibração instantânea a cada rodada (% já em acordo hoje, mais uma segunda leitura por banda — pro Collection Score, a propensão média de pagamento do modelo de Propensão; pra Propensão, o próprio propscore médio da banda); "Realizado" acompanha coortes de clientes ao longo de 30 dias a partir da data em que a banda foi atribuída, medindo Conversão em acordo e Pagamento efetivo separadamente, usando o histórico real de pagamentos (mesma fonte da Propensão de Pagamento). Persistido em `data/collection_band_history.json` (Collection Score) e `data/propensao_band_history.json` (Propensão) — arquivos irmãos, mesma estrutura `{"pendentes": [...], "resolvidos": [...]}`.

O segundo modelo (25/08/2026) fecha uma lacuna: antes só o Collection Score tinha esse loop de calibração viva contra o que de fato aconteceu — a Propensão só tinha o AUC out-of-time (treino/teste de bancada), sem validação contra coortes reais ao longo do tempo. Clientes sem histórico de pagamento (`_propband == -1`) não entram no bloco da Propensão — não pertencem a nenhuma banda.

⚠️ **Os dois arquivos `*_band_history.json` precisam ser baixados do GitHub antes de cada rodada e resubidos depois**, com a mesma lógica do `index.json` — sem isso, o rastreamento de coortes pendentes de maturação é perdido. O primeiro dado real de "Realizado" só existe depois que uma coorte completa os 30 dias corridos desde sua criação (mesmo prazo para os dois modelos).

---

## Colaboradores (marcação opcional, cruzamento com RH)

Quando uma planilha `.xlsx` com "colaborador" no nome está presente na pasta de trabalho, o dashboard marca quais clientes da carteira também são colaboradores do grupo (Filial/Cargo), disponível como filtro na aba Analítico e como sub-aba própria em Carteira. O cruzamento usa **só o CPF** — salário e data de nascimento da planilha de RH nunca são lidos nem expostos no dashboard (que é público, sem autenticação). Sem a planilha, a marcação fica desativada sem quebrar o resto da geração.

---

## Filtros e toggles do dashboard

| Filtro/Toggle | Onde | Efeito |
|---|---|---|
| **Período** (mês) | Cabeçalho | Troca todos os dados para o mês selecionado |
| **Assessoria** | Cabeçalho | Filtra todas as abas para uma assessoria — só aparece com 2+ assessorias nos dados |
| **Tipo de Ação / Canal-Motivo** | Barra de filtros (oculta na aba Carteira) | Filtra Analítico e Matriz por linha; Volume só pelo Tipo de Ação; Geral/Atraso/Valor mostram aviso (dados consolidados) |
| **🤝 Acordos** (global) | Barra de filtros | Desligado por padrão — exclui clientes em acordo das métricas de cobertura, em todas as abas incluindo Carteira (corrigido em 26/08/2026 — a aba Carteira tinha uma implementação própria de "Faixas de Atraso/Valor/Segmentos" que não respeitava o toggle; ver CLAUDE.md). Ressalva: o saldo em R$ *por faixa de valor* dentro de "Faixas de Valor" ainda inclui Acordo (só o card "Total carteira" está exato) até o Python calcular um `valor_sem_acordo` |
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
python3 gerar_jsons_acionamentos.py   # gera os JSONs na pasta atual, a partir dos CSVs locais
mkdir -p data && cp 2026-*.json index.json collection_band_history.json propensao_band_history.json data/
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
| `propensao_meta` ausente no JSON | `Recuperação AAAA.csv` (histórico multi-ano) não estava na pasta do script naquela rodada | Copiar os arquivos `Recuperação AAAA.csv` para a pasta antes de rodar — não é um período de espera, é ausência de arquivo |
| Sub-aba "Esperado x Realizado" mostra tudo "aguardando maturação" (em qualquer um dos dois toggles) | Nenhuma coorte do modelo (Collection Score ou Propensão) ainda completou 30 dias desde que a banda foi atribuída | Esperado — o "Realizado" só popula depois de ~30 dias corridos da primeira rodada em que a coorte apareceu |
| Sub-aba "🏢 Colaboradores" não aparece | Nenhuma planilha `.xlsx` com "colaborador" no nome estava na pasta do script | Opcional — só aparece quando o mês tem dado de RH |
| `SyntaxError: Failed to execute 'close'...` no preview do Claude | Sem os JSONs locais em `data/`, o fetch cai num 404 | Funciona normalmente publicado no GitHub Pages |

---

*README atualizado em 25/08/2026 — corrige uma afirmação anterior de que o Motor Único participava da geração deste dashboard (não participa; confirmado por leitura direta do script), estende o Esperado x Realizado para também cobrir a Propensão de Pagamento (antes só o Collection Score tinha essa calibração viva) e mantém a descrição das funcionalidades de Collection Score/Propensão de Pagamento/Colaboradores (processamento manual, sem workflow automático ativo).*
