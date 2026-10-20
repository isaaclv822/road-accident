import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Chemin de la base, calculé à partir de l'emplacement de ce fichier (fonctionne d'où qu'on lance)
DB = Path(__file__).parent / "data" / "accidents.db"
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
COULEUR = "#2a78d6"

st.set_page_config(page_title="Accidents de la route 2024", page_icon="🚗", layout="wide")


# Outils
@st.cache_resource  # la connexion est créée une seule fois, puis réutilisée
def connexion():
    return sqlite3.connect(DB, check_same_thread=False)


def sql(requete, params=()):
    """Exécute une requête SQL et renvoie un DataFrame (comme dans le notebook)."""
    return pd.read_sql(requete, connexion(), params=params)


def barres(df, x, y, titre, labels, **options):
    """Graphique en barres avec le même style partout (évite de répéter le code)."""
    fig = px.bar(df, x=x, y=y, title=titre, labels=labels,
                 color_discrete_sequence=[COULEUR], **options)
    # Axe X en catégories : sinon plotly lit "13", "75"... comme des nombres
    # et place les départements sur une échelle de 0 à 100
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")


def nombre(x):
    """54402 -> '54 402'"""
    return f"{int(x):,}".replace(",", " ")


# Filtre
deps = sql("SELECT DISTINCT dep FROM accidents ORDER BY dep")["dep"].tolist()
dep = st.sidebar.selectbox("Département", ["Tous"] + deps)
st.sidebar.caption("Source : ONISR, bases annuelles des accidents corporels 2024 (data.gouv.fr)")

# Le filtre s'ajoute à chaque requête. Le « ? » est remplacé par la valeur de 'params' :
# on n'insère JAMAIS directement une valeur choisie par l'utilisateur dans le texte SQL
# (sinon risque d'injection SQL).
if dep == "Tous":
    where, params = "", ()
else:
    where, params = "WHERE a.dep = ?", (dep,)

# Titre + chiffres clés
st.title("🚗 Accidents de la route en France — 2024")
st.caption("Département sélectionné : " + dep)

kpi = sql(f"""
    SELECT COUNT(DISTINCT a.Num_Acc) AS nb_accidents,
           COUNT(*) AS nb_usagers,
           SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) AS nb_tues
    FROM usagers AS u
    JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
    {where}
""", params).iloc[0]   # .iloc[0] : la première (et unique) ligne du résultat

c1, c2, c3, c4 = st.columns(4)
c1.metric("Accidents", nombre(kpi["nb_accidents"]))
c2.metric("Personnes impliquées", nombre(kpi["nb_usagers"]))
c3.metric("Personnes tuées", nombre(kpi["nb_tues"]))
c4.metric("Part de tués", f"{100 * kpi['nb_tues'] / kpi['nb_usagers']:.2f} %")

# Q1 : quand ?
st.header("Quand ?")
gauche, droite = st.columns(2)
with gauche:
    par_heure = sql(f"""
        SELECT heure, COUNT(*) AS nb_accidents
        FROM accidents AS a {where}
        GROUP BY heure ORDER BY heure
    """, params)
    barres(par_heure, "heure", "nb_accidents", "Accidents selon l'heure",
           {"heure": "Heure", "nb_accidents": "Accidents"})
with droite:
    par_jour = sql(f"""
        SELECT jour_semaine, COUNT(*) AS nb_accidents
        FROM accidents AS a {where}
        GROUP BY jour_semaine
    """, params)
    barres(par_jour, "jour_semaine", "nb_accidents", "Accidents selon le jour",
           {"jour_semaine": "", "nb_accidents": "Accidents"},
           category_orders={"jour_semaine": JOURS})

# Q2 : où ?
st.header("Où ?")
if dep == "Tous":
    # France entière : 50 000 points seraient illisibles. On regroupe par département
    # (GROUP BY) et on affiche UNE bulle par département, placée à la position moyenne
    # de ses accidents : taille = nombre d'accidents, couleur = part de tués.
    par_dep = sql("""
        SELECT a.dep,
               COUNT(DISTINCT a.Num_Acc) AS nb_accidents,
               ROUND(100.0 * SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_tues,
               AVG(a.lat) AS lat,
               AVG(a.long) AS long
        FROM usagers AS u
        JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
        GROUP BY a.dep
    """)
    # On garde la métropole, sinon les outre-mer rendent la carte illisible
    par_dep = par_dep[par_dep["lat"].between(41, 52) & par_dep["long"].between(-5.5, 10)]
    fig = px.scatter_map(
        par_dep, lat="lat", lon="long",
        size="nb_accidents", color="pct_tues", size_max=35,
        color_continuous_scale="Reds",
        hover_name="dep",
        hover_data={"nb_accidents": True, "pct_tues": True, "lat": False, "long": False},
        labels={"nb_accidents": "Accidents", "pct_tues": "% de tués"},
        center={"lat": 46.6, "lon": 2.4}, zoom=4.6,
        map_style="carto-positron", height=600,
    )
    st.caption("Une bulle par département (métropole) : taille = nombre d'accidents, "
               "couleur = part des personnes impliquées qui ont été tuées.")
else:
    # Un seul département : quelques centaines ou milliers de points, lisibles un par un
    points = sql(f"SELECT lat, long FROM accidents AS a {where}", params)
    fig = px.scatter_map(
        points, lat="lat", lon="long", opacity=0.5,
        center={"lat": points["lat"].median(), "lon": points["long"].median()}, zoom=8,
        map_style="carto-positron", height=600,
    )
    fig.update_traces(marker={"size": 6, "color": COULEUR})
    st.caption("Un point = un accident.")

fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
st.plotly_chart(fig, width="stretch")

if dep == "Tous":
    top_dep = sql("""
        SELECT dep, COUNT(*) AS nb_accidents
        FROM accidents GROUP BY dep
        ORDER BY nb_accidents DESC LIMIT 10
    """)
    barres(top_dep, "dep", "nb_accidents", "Les 10 départements avec le plus d'accidents",
           {"dep": "Département", "nb_accidents": "Accidents"})

# Q3-Q5 : gravité
st.header("Qu'est-ce qui rend un accident plus grave ?")
st.caption("Part des personnes impliquées qui ont été tuées.")


def part_tues_par(colonne):
    # Ici la colonne vient de NOTRE code (pas de l'utilisateur) : l'insérer dans le texte est sans risque
    return sql(f"""
        SELECT a.{colonne} AS categorie,
               ROUND(100.0 * SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_tues
        FROM usagers AS u
        JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
        {where}
        GROUP BY a.{colonne}
        ORDER BY pct_tues DESC
    """, params)


gauche, droite = st.columns(2)
with gauche:
    barres(part_tues_par("periode"), "categorie", "pct_tues", "Selon la période",
           {"categorie": "", "pct_tues": "% de tués"}, text="pct_tues")
with droite:
    barres(part_tues_par("agglomeration"), "categorie", "pct_tues", "Selon le lieu",
           {"categorie": "", "pct_tues": "% de tués"}, text="pct_tues")

# Q4 : qui ?
st.header("Qui ?")
par_age = sql(f"""
    SELECT
        CASE
            WHEN u.age < 18 THEN '0-17'
            WHEN u.age < 25 THEN '18-24'
            WHEN u.age < 45 THEN '25-44'
            WHEN u.age < 65 THEN '45-64'
            ELSE '65+'
        END AS tranche_age,
        ROUND(100.0 * SUM(CASE WHEN u.gravite = 'Tué' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_tues
    FROM usagers AS u
    JOIN accidents AS a ON u.Num_Acc = a.Num_Acc
    {where} {"AND" if where else "WHERE"} u.age IS NOT NULL
    GROUP BY tranche_age ORDER BY tranche_age
""", params)
barres(par_age, "tranche_age", "pct_tues", "Part de tués selon l'âge",
       {"tranche_age": "Âge", "pct_tues": "% de tués"}, text="pct_tues")
