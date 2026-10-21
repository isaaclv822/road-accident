"""Résumé automatique d'un département : le code calcule et compare, le LLM rédige.

C'est le code du notebook 05 (version 2 de la fiche), regroupé dans un module pour le dashboard.
"""
import re

import ollama

from assistant import sql   # même connexion en lecture seule que l'assistant

MODELE = "qwen2.5-coder:7b"
PCT_TUES = "ROUND(100.0 * SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) / COUNT(*), 2)"


def fr(x, decimales=0):
    """Formate un nombre à la française : 1627 -> '1 627', 3.55 -> '3,55'."""
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


# --------------------------------------------------------------------------- 1. le code calcule
def stats_departement(dep):
    stats = {"dep": dep}
    kpi = sql(f"""
        SELECT COUNT(DISTINCT a.Num_Acc) AS nb_accidents, COUNT(*) AS nb_usagers,
               SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) AS nb_tues,
               {PCT_TUES} AS pct_tues
        FROM usagers AS u JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
        WHERE a.dep = ?
    """, (dep,)).iloc[0]
    stats.update(kpi.to_dict())
    stats["pct_tues_france"] = sql(f"SELECT {PCT_TUES} AS pct FROM usagers AS u").iloc[0]["pct"]
    pic = sql("""
        SELECT heure, COUNT(*) AS nb FROM accidents
        WHERE dep = ? GROUP BY heure ORDER BY nb DESC LIMIT 1
    """, (dep,)).iloc[0]
    stats["heure_pic"] = int(pic["heure"])
    for colonne in ["periode", "agglomeration"]:
        df = sql(f"""
            SELECT a.{colonne} AS categorie, {PCT_TUES} AS pct
            FROM usagers AS u JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
            WHERE a.dep = ? GROUP BY a.{colonne}
        """, (dep,))
        stats[colonne] = dict(zip(df["categorie"], df["pct"]))
    return stats


# --------------------------------------------------------------------------- 2. le code compare
def position(valeur, reference):
    if valeur > reference * 1.1:
        return "supérieure à"
    if valeur < reference * 0.9:
        return "inférieure à"
    return "proche de"


def rapport(a, b):
    if a >= b * 1.1:
        return f"{fr(a / b, 1)} fois plus"
    if a <= b * 0.9:
        return "moins"
    return "autant"


def fiche(stats):
    pct, pct_fr = stats["pct_tues"], stats["pct_tues_france"]
    lignes = [
        f"Département {stats['dep']}, année 2024.",
        f"{fr(stats['nb_accidents'])} accidents, impliquant {fr(stats['nb_usagers'])} personnes, "
        f"dont {fr(stats['nb_tues'])} ont été tuées.",
        f"Part des personnes impliquées qui ont été tuées : {fr(pct, 2)} %, "
        f"{position(pct, pct_fr)} la moyenne française ({fr(pct_fr, 2)} %).",
        f"L'heure qui compte le plus d'accidents est {stats['heure_pic']} h.",
    ]
    p = stats["periode"]
    if p.get("Nuit") and p.get("Jour"):
        lignes.append(f"Parmi les personnes impliquées dans un accident de nuit, {fr(p['Nuit'], 2)} % ont été tuées, "
                      f"contre {fr(p['Jour'], 2)} % le jour : les accidents de nuit sont "
                      f"{rapport(p['Nuit'], p['Jour'])} meurtriers que ceux de jour.")
    a = stats["agglomeration"]
    hors, en = a.get("Hors agglomération"), a.get("En agglomération")
    if hors and en:
        lignes.append(f"Parmi les personnes impliquées hors agglomération, {fr(hors, 2)} % ont été tuées, "
                      f"contre {fr(en, 2)} % en agglomération : les accidents hors agglomération sont "
                      f"{rapport(hors, en)} meurtriers.")
    return "\n".join("- " + ligne for ligne in lignes)


# --------------------------------------------------------------------------- 3. le LLM rédige
SYSTEME = """Tu es analyste en sécurité routière. À partir de la fiche de données fournie,
rédige un paragraphe de 4 à 5 phrases en français, clair et factuel, destiné au grand public.

Règles strictes :
- Utilise UNIQUEMENT les chiffres de la fiche, recopiés exactement. N'invente aucun chiffre et ne fais aucun calcul.
- Désigne le département uniquement par son numéro (exemple : « le département 69 »).
- Ne fais AUCUNE comparaison toi-même : reprends exactement celles de la fiche (« inférieure à », « 3,9 fois plus »…).
- Ne change pas le sens des pourcentages : reprends les formulations de la fiche.
- N'avance aucune explication ou cause qui ne figure pas dans la fiche."""


def resumer(dep, modele=MODELE):
    """Renvoie (fiche de faits, texte rédigé par le LLM)."""
    faits = fiche(stats_departement(dep))
    reponse = ollama.chat(
        model=modele,
        messages=[{"role": "system", "content": SYSTEME},
                  {"role": "user", "content": "Fiche de données :\n" + faits}],
        options={"temperature": 0, "seed": 42},
    )
    return faits, reponse["message"]["content"]


# --------------------------------------------------------------------------- 4. le garde-fou
def nombres(texte):
    trouves = re.findall(r"\d+(?:[   ]\d{3})*(?:[.,]\d+)?", texte)
    return {re.sub(r"[   ]", "", t).replace(".", ",") for t in trouves}


def nombres_inventes(faits, texte):
    """Nombres présents dans le texte mais absents de la fiche (probablement inventés)."""
    return sorted(nombres(texte) - nombres(faits))
