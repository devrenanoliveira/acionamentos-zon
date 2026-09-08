# -*- coding: utf-8 -*-
"""
Bloco de FRAUDE — coincidência de cadastro entre CPFs diferentes.

Importado por gerar_jsons_acionamentos.py. Fica em arquivo separado porque é
a única parte do pipeline que trabalha com dado de contato (e-mail, endereço),
e mantê-la isolada deixa explícito o que ela lê e o que ela devolve.

O QUE ISTO É: contagem de coincidências. Um "sinal" é uma chave normalizada
(telefone, e-mail ou endereço) que aparece em 2+ CPFs distintos. O tier é
quantos sinais batem ao mesmo tempo — 3=ALTA, 2=MEDIA, 1=BAIXA. Não há modelo,
não há score: qualquer linha pode ser conferida na mão.

O QUE ISTO NÃO É: prova de fraude. República, asilo, família numerosa e loja
que cadastra o próprio e-mail produzem exatamente a mesma assinatura. Por isso
todo texto de UI fala em "coincidência de cadastro a verificar", nunca em
"fraudador" — e por isso o bloco `emails_revisar` existe.
"""
import re
import unicodedata
from collections import defaultdict

# E-mails de preenchimento ("não tenho e-mail"). Sem este filtro, os ~187 CPFs
# que dividem naotenho@gmail.com virariam um cluster gigante e falso.
PLACEHOLDER_RE = re.compile(
    r"^(nao|n\.?ao|sem|nt|ni|no)[\w.]*"
    r"(tem|tenho|possu[ie]|informado|email|e-mail|mail)?[\w.]*@"
    r"|^(sem\.?email|email|teste|test|abc|xxx|aaa|naoinformado)@",
    re.I)
END_GENERICO_RE = re.compile(r"zona rural|sem endere|nao informado|^-?\s*$", re.I)

# E-mail que aparece em N+ CPFs e não caiu no regex acima entra na lista de
# revisão manual — pode ser cadastro de loja/atendente inflando os números.
LIMIAR_REVISAO = 8

TIERS = ("ALTA", "MEDIA", "BAIXA")


def _strip_ac(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn")


def _keys_tel(v):
    out = set()
    for t in re.split(r"[;,]", str(v)):
        d = re.sub(r"\D", "", t)
        if d.startswith("55") and len(d) > 11:
            d = d[2:]
        if 10 <= len(d) <= 11:
            out.add(d)
    return out


def _keys_email(v):
    out, brutos = set(), set()
    for e in re.split(r"[;,]", str(v)):
        e = e.strip().lower()
        if "@" not in e or "." not in e.split("@")[-1]:
            continue
        brutos.add(e)
        if not PLACEHOLDER_RE.search(e):
            out.add(e)
    return out, brutos


def _key_end(endereco, cep):
    e = _strip_ac(endereco).strip().lower()
    e = re.sub(r"^-\s*", "", e)
    e = re.sub(r"[.,]", " ", e)
    e = re.sub(r"\s+", " ", e).strip()
    if not e or END_GENERICO_RE.search(e):
        return ""
    cep_num = re.sub(r"\D", "", str(cep))
    return e + "|" + cep_num


def calcular(cart, col_tel, col_email, col_end, col_cep, fa_labels, fv_labels, r2):
    """Recebe o DataFrame já normalizado e devolve (bloco_json, por_cpf).

    `por_cpf` é dict cpf -> (tier_idx, sinais, cluster_id) para o analítico;
    tier_idx: 0=ALTA 1=MEDIA 2=BAIXA, -1 = sem sinal.
    Se o CSV do mês não tem e-mail/endereço, devolve (None, {}) — meses antigos
    continuam gerando normalmente, sem a aba.
    """
    if not col_email and not col_end:
        return None, {}

    n = len(cart)
    cpfs = list(cart["_cpf"])
    saldos = [float(x) for x in cart["_saldo"]]
    dias = [int(x) for x in cart["_dias"]]
    fa = [int(x) for x in cart["_fa"]]
    fv = [int(x) for x in cart["_fv"]]
    cidades = [str(x).strip() for x in cart["_cidade"]]

    tel_v = list(cart[col_tel]) if col_tel else [""] * n
    mail_v = list(cart[col_email]) if col_email else [""] * n
    end_v = list(cart[col_end]) if col_end else [""] * n
    cep_v = list(cart[col_cep]) if col_cep else [""] * n

    idx_tel, idx_mail, idx_end = defaultdict(list), defaultdict(list), defaultdict(list)
    mail_por_linha, placeholders = [], defaultdict(set)
    for i in range(n):
        for k in _keys_tel(tel_v[i]):
            idx_tel[k].append(i)
        ks, brutos = _keys_email(mail_v[i])
        mail_por_linha.append(ks)
        for k in ks:
            idx_mail[k].append(i)
        for b in brutos - ks:
            placeholders[b].add(cpfs[i])
        ke = _key_end(end_v[i], cep_v[i])
        if ke:
            idx_end[ke].append(i)

    # ---- sinais ----
    sig = [set() for _ in range(n)]
    for tag, idx in (("T", idx_tel), ("E", idx_mail), ("A", idx_end)):
        for _, rows in idx.items():
            if len(rows) > 1:
                for i in rows:
                    sig[i].add(tag)

    # ---- clusters (union-find) ----
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idx in (idx_tel, idx_mail, idx_end):
        for _, rows in idx.items():
            if len(rows) > 1:
                r0 = find(rows[0])
                for j in rows[1:]:
                    rj = find(j)
                    if r0 != rj:
                        parent[rj] = r0

    raiz = [find(i) for i in range(n)]
    tam = defaultdict(int)
    for i in range(n):
        if sig[i]:
            tam[raiz[i]] += 1

    # só entra quem tem sinal E está num grupo de 2+ CPFs
    susp = [i for i in range(n) if sig[i] and tam[raiz[i]] >= 2]

    def tier_de(i):
        return {3: "ALTA", 2: "MEDIA", 1: "BAIXA"}[len(sig[i])]

    # ---- agregados ----
    tot = {t: {"qtd": 0, "saldo": 0.0} for t in TIERS}
    por_fa = {t: [{"qtd": 0, "saldo": 0.0} for _ in fa_labels] for t in TIERS}
    por_fv = {t: [{"qtd": 0, "saldo": 0.0} for _ in fv_labels] for t in TIERS}
    curto = {"qtd": 0, "saldo": 0.0}
    for i in susp:
        t = tier_de(i)
        tot[t]["qtd"] += 1
        tot[t]["saldo"] += saldos[i]
        por_fa[t][fa[i]]["qtd"] += 1
        por_fa[t][fa[i]]["saldo"] += saldos[i]
        por_fv[t][fv[i]]["qtd"] += 1
        por_fv[t][fv[i]]["saldo"] += saldos[i]
        if dias[i] <= 30:
            curto["qtd"] += 1
            curto["saldo"] += saldos[i]

    # ---- clusters para a tabela ----
    membros = defaultdict(list)
    for i in susp:
        membros[raiz[i]].append(i)

    clusters = []
    for cid, ms in membros.items():
        ks_t, ks_e, ks_a = set(), set(), set()
        for i in ms:
            ks_t |= _keys_tel(tel_v[i])
            ks_e |= mail_por_linha[i]
            ke = _key_end(end_v[i], cep_v[i])
            if ke:
                ks_a.add(ke)
        ct = sorted((k for k in ks_t if len(idx_tel.get(k, [])) > 1),
                    key=lambda k: -len(idx_tel[k]))
        ce = sorted((k for k in ks_e if len(idx_mail.get(k, [])) > 1),
                    key=lambda k: -len(idx_mail[k]))
        ca = sorted((k for k in ks_a if len(idx_end.get(k, [])) > 1),
                    key=lambda k: -len(idx_end[k]))
        tipos = "".join(x for x, c in (("T", ct), ("E", ce), ("A", ca)) if c)
        cs = sorted(set(cidades[i] for i in ms))
        clusters.append({
            "id": int(cid),
            "cpfs": len(ms),
            "saldo": r2(sum(saldos[i] for i in ms)),
            "tipos": tipos,
            "cidades": cs[:3],
            "n_cidades": len(cs),
            "atraso_medio": int(sum(dias[i] for i in ms) / len(ms)),
            "curto": sum(1 for i in ms if dias[i] <= 30),
            "email": (f"{ce[0]} ({len(idx_mail[ce[0]])})" if ce else ""),
            "endereco": (f"{ca[0].split('|')[0]} ({len(idx_end[ca[0]])})" if ca else ""),
            "telefone": (f"{ct[0]} ({len(idx_tel[ct[0]])})" if ct else ""),
            "prio": round(len(ms) * (1 + 0.5 * (len(tipos) - 1)), 1),
        })
    clusters.sort(key=lambda c: (-c["prio"], -c["saldo"]))

    # ---- e-mails a revisar / placeholders filtrados ----
    # `so_email` é o número que decide se um e-mail muito repetido é cadastro de
    # terceiro ou vínculo real: se as pessoas que o dividem não têm mais nada em
    # comum entre si, o e-mail foi só digitado igual; se dividem telefone ou
    # endereço também, existe ligação de verdade e o e-mail não é o motivo.
    # Não classificamos automaticamente por isso — só expomos o número.
    susp_set = set(susp)
    revisar = []
    for k, rows in idx_mail.items():
        u = set(cpfs[i] for i in rows)
        if len(u) >= LIMIAR_REVISAO:
            afet = [i for i in rows if i in susp_set]
            revisar.append({
                "email": k,
                "cpfs": len(u),
                "saldo": r2(sum(saldos[i] for i in rows)),
                "cidades": sorted(set(cidades[i] for i in rows))[:3],
                "n_cidades": len(set(cidades[i] for i in rows)),
                "sobrenomes": len(set(str(cart["_nome"].iloc[i]).split()[-1]
                                      for i in rows if str(cart["_nome"].iloc[i]).strip())),
                "em_alta_media": sum(1 for i in afet if len(sig[i]) >= 2),
                "so_email": sum(1 for i in afet if sig[i] == {"E"}),
                "com_outro_sinal": sum(1 for i in afet if len(sig[i]) > 1),
            })
    revisar.sort(key=lambda x: -x["cpfs"])

    filtrados = sorted(({"email": k, "cpfs": len(v)} for k, v in placeholders.items()),
                       key=lambda x: -x["cpfs"])[:20]

    # quanto do resultado depende de e-mail ainda não validado
    dep = set()
    for r in revisar:
        for i in idx_mail[r["email"]]:
            if i in set(susp):
                dep.add(i)
    # Separa quem depende SÓ do e-mail (sairia da lista se ele fosse descartado)
    # de quem apenas cairia de nível — a distinção que impede de tratar um
    # e-mail muito repetido como se invalidasse tudo que está ligado a ele.
    dep_so = {i for i in dep if sig[i] == {"E"}}
    dependente = {
        "qtd": len(dep),
        "saldo": r2(sum(saldos[i] for i in dep)),
        "so_email": len(dep_so),
        "so_email_saldo": r2(sum(saldos[i] for i in dep_so)),
        "sobreviveria": len(dep) - len(dep_so),
        "sobreviveria_saldo": r2(sum(saldos[i] for i in dep - dep_so)),
        "alta_media": sum(1 for i in dep if len(sig[i]) >= 2),
        "alta_media_saldo": r2(sum(saldos[i] for i in dep if len(sig[i]) >= 2)),
    }

    por_cpf = {}
    ordem = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}
    for i in susp:
        por_cpf[cpfs[i]] = (ordem[tier_de(i)], "".join(sorted(sig[i])), int(raiz[i]))

    def limpa(d):
        return {"qtd": d["qtd"], "saldo": r2(d["saldo"])}

    bloco = {
        "gerado_para": "coincidencia de cadastro entre CPFs diferentes",
        "sinais_disponiveis": "".join(x for x, c in
                                      (("T", col_tel), ("E", col_email), ("A", col_end)) if c),
        "limiar_revisao": LIMIAR_REVISAO,
        "total_suspeitos": len(susp),
        "total_saldo": r2(sum(saldos[i] for i in susp)),
        "total_clusters": len(clusters),
        "atraso_curto": limpa(curto),
        "tiers": {t: limpa(tot[t]) for t in TIERS},
        "por_faixa_atraso": {t: [limpa(x) for x in por_fa[t]] for t in TIERS},
        "por_faixa_valor": {t: [limpa(x) for x in por_fv[t]] for t in TIERS},
        "clusters": clusters[:60],
        "emails_revisar": revisar,
        "emails_filtrados": filtrados,
        "dependente_de_email_nao_validado": dependente,
    }
    return bloco, por_cpf
