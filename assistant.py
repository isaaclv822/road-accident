"""Assistant text-to-SQL : répond en français à une question sur la base des accidents.

C'est le code du notebook 06, regroupé dans un module pour être réutilisé
par l'évaluation (notebook 07) et par le dashboard (app.py).

    question -> LLM -> requête SQL -> contrôle de sécurité -> base SQLite -> résultat
"""
import re
import sqlite3
from pathlib import Path

import ollama
import pandas as pd

DB = Path(__file__).parent / "data" / "accidents.db"
MODELE = "qwen2.5-coder:7b"

# --------------------------------------------------------------------------- base de données
_connexion = None


def connexion():
    """Connexion en LECTURE SEULE, créée une seule fois puis réutilisée."""
    global _connexion                 # on modifie la variable définie hors de la fonction
    if _connexion is None:
        # as_uri() transforme le chemin en "file:///C:/..." (gère les espaces du chemin Windows)
        _connexion = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    return _connexion


def sql(requete, params=()):
    return pd.read_sql(requete, connexion(), params=params)


# --------------------------------------------------------------------------- contexte pour le LLM
def decrire_base():
    """Description des tables, des colonnes et des valeurs possibles des colonnes texte."""
    lignes = []
    for table in ["accidents", "usagers"]:
        lignes.append(f"Table {table} :")
        for _, col in sql(f"PRAGMA table_info({table})").iterrows():
            nom, type_sql = col["name"], col["type"]
            description = f"  - {nom} ({type_sql})"
            if type_sql == "TEXT":
                valeurs = sql(f"SELECT DISTINCT {nom} FROM {table} WHERE {nom} IS NOT NULL LIMIT 13")[nom]
                if len(valeurs) <= 12:
                    description += " valeurs possibles : " + ", ".join(f"'{v}'" for v in valeurs)
            lignes.append(description)
    return "\n".join(lignes)


def prompt_systeme():
    return f"""Tu es un expert SQL. Tu traduis des questions en français en UNE requête SQLite.

Description de la base (accidents de la route en France, année 2024) :
{decrire_base()}

Informations utiles :
- Une ligne de "accidents" = un accident ; une ligne de "usagers" = une personne impliquée.
- Les deux tables sont liées par Num_Acc.
- "dep" est le code du département, en TEXTE : '75', '13', '2A', '974'...
- "com" est le code INSEE de la commune (ex. '75111'), jamais un nom : ne l'utilise pas avec un nom de ville.
- La base ne contient AUCUN nom de lieu. Convertis un lieu donné par son nom en code de département :
  Paris = '75' (la ville et le département sont identiques), Gironde = '33', Rhône = '69', Nord = '59', etc.
- "heure" va de 0 à 23. "age" est en années.

Règles :
- Réponds UNIQUEMENT avec la requête SQL, sans explication et sans commentaire.
- Une seule requête, qui commence par SELECT.
- Utilise exactement les valeurs listées ci-dessus (attention aux majuscules et aux accents).
- Donne des noms clairs aux colonnes calculées avec AS.

Exemples :
Question : Combien d'accidents ont eu lieu en 2024 ?
SQL : SELECT COUNT(*) AS nb_accidents FROM accidents

Question : Combien de personnes ont été tuées dans le département 13 ?
SQL : SELECT COUNT(*) AS nb_tues FROM usagers AS u JOIN accidents AS a ON u.Num_Acc = a.Num_Acc WHERE u.gravite = 'Tué' AND a.dep = '13'

Question : Quelle est la part de tués selon la météo ?
SQL : SELECT a.meteo, ROUND(100.0 * SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_tues FROM usagers AS u JOIN accidents AS a ON u.Num_Acc = a.Num_Acc GROUP BY a.meteo ORDER BY pct_tues DESC
"""


# --------------------------------------------------------------------------- génération et sécurité
def nettoyer(texte):
    """Retire les éventuelles balises ```sql ... ``` et le point-virgule final."""
    texte = re.sub(r"```(?:sql)?", "", texte)
    return texte.strip().rstrip(";").strip()


def generer_sql(question, modele=MODELE):
    reponse = ollama.chat(
        model=modele,
        messages=[
            {"role": "system", "content": prompt_systeme()},
            {"role": "user", "content": question},
        ],
        options={"temperature": 0, "seed": 42},
    )
    return nettoyer(reponse["message"]["content"])


INTERDITS = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM)\b"


def verifier_securite(requete):
    """Renvoie None si la requête est acceptable, sinon le motif du refus."""
    if ";" in requete:
        return "Une seule requête est autorisée."
    if not re.match(r"^\s*(SELECT|WITH)\b", requete, re.IGNORECASE):
        return "Seules les requêtes de lecture (SELECT) sont autorisées."
    if re.search(INTERDITS, requete, re.IGNORECASE):
        return "La requête contient une instruction interdite."
    return None


# --------------------------------------------------------------------------- point d'entrée
def repondre(question, modele=MODELE):
    """Renvoie un dictionnaire : question, sql, statut ('ok', 'refus' ou 'erreur'), resultat, message."""
    requete = generer_sql(question, modele)
    reponse = {"question": question, "sql": requete, "statut": "ok", "resultat": None, "message": ""}

    refus = verifier_securite(requete)
    if refus:
        reponse.update(statut="refus", message=refus)
        return reponse

    try:
        reponse["resultat"] = sql(requete)
    except Exception as erreur:
        reponse.update(statut="erreur", message=str(erreur))
    return reponse
