"""Page « Assistant IA » du dashboard (déclarée dans app.py)."""
import ollama
import streamlit as st

import assistant
import resume

st.set_page_config(page_title="Assistant IA", page_icon="🤖", layout="wide")
st.title("🤖 Assistant IA")


# ----------------------------------------------------------------------------- Ollama est-il là ?
@st.cache_data(ttl=60)   # on ne revérifie qu'une fois par minute
def ollama_disponible():
    try:
        ollama.list()        # échoue si le serveur Ollama ne tourne pas
        return True
    except Exception:
        return False


if not ollama_disponible():
    st.info(
        "L'assistant fonctionne **en local** avec [Ollama](https://ollama.com) et le modèle "
        f"`{assistant.MODELE}` : il n'est pas disponible dans la version en ligne. "
        "Une vidéo de démonstration est disponible dans le README du projet."
    )
    st.stop()

onglet_questions, onglet_resume = st.tabs(["💬 Poser une question", "📝 Résumé d'un département"])

# ----------------------------------------------------------------------------- 1. text-to-SQL
EXEMPLES = [
    "Combien de piétons ont été tués la nuit ?",
    "Quels sont les 5 départements avec le plus de tués ?",
    "Quelle est la part de tués chez les 65 ans et plus ?",
    "Combien d'accidents ont eu lieu en Gironde par temps de pluie ?",
]


def afficher(reponse):
    """Affiche une réponse de l'assistant selon son statut."""
    if reponse["statut"] == "refus":
        st.error(f"🛑 Requête refusée : {reponse['message']}")
    elif reponse["statut"] == "erreur":
        st.warning("💥 La requête générée est invalide. Essaie de reformuler la question.")
    else:
        resultat = reponse["resultat"]
        if resultat.shape == (1, 1):                     # une seule valeur : on l'affiche en grand
            valeur = resultat.iloc[0, 0]
            if isinstance(valeur, float):
                valeur = round(valeur, 2)
            st.metric(resultat.columns[0], valeur)
        else:
            st.dataframe(resultat, hide_index=True)
    # Transparence : on montre toujours la requête exécutée, pour pouvoir la vérifier
    with st.expander("Voir la requête SQL"):
        st.code(reponse["sql"], language="sql")


with onglet_questions:
    st.caption(
        "Pose une question en français : le modèle la traduit en SQL, puis la base calcule la réponse. "
        "Les chiffres viennent toujours de la base, jamais du modèle. "
        "Fiabilité mesurée : 21 bonnes réponses sur 22 questions de test."
    )

    # st.session_state garde des données entre deux interactions (sinon tout est oublié à chaque clic)
    if "historique" not in st.session_state:
        st.session_state.historique = []

    st.write("Exemples :")
    colonnes = st.columns(2)                      # 2 colonnes : les exemples restent lisibles
    question = None
    for i, exemple in enumerate(EXEMPLES):
        if colonnes[i % 2].button(exemple, width="stretch"):   # i % 2 alterne entre 0 et 1
            question = exemple
    question = st.chat_input("Ta question sur les accidents de 2024…") or question

    if question:
        with st.spinner("Le modèle écrit la requête SQL…"):
            st.session_state.historique.append(assistant.repondre(question))

    # Affichage de l'historique, du plus récent au plus ancien
    for reponse in reversed(st.session_state.historique):
        with st.chat_message("user"):
            st.write(reponse["question"])
        with st.chat_message("assistant"):
            afficher(reponse)

# ----------------------------------------------------------------------------- 2. résumé
with onglet_resume:
    st.caption(
        "Le code calcule et compare les chiffres en SQL, puis le modèle les met en forme. "
        "Les nombres du texte sont vérifiés automatiquement."
    )
    deps = assistant.sql("SELECT DISTINCT dep FROM accidents ORDER BY dep")["dep"].tolist()
    dep = st.selectbox("Département", deps, index=deps.index("69") if "69" in deps else 0)

    if st.button("Générer le résumé", type="primary"):
        with st.spinner("Rédaction en cours…"):
            faits, texte = resume.resumer(dep)
        st.write(texte)
        inventes = resume.nombres_inventes(faits, texte)
        if inventes:
            st.warning(f"⚠️ Nombres absents des données, à vérifier : {', '.join(inventes)}")
        else:
            st.success("✅ Tous les nombres du texte proviennent des données.")
        with st.expander("Voir la fiche de faits (chiffres calculés en SQL)"):
            st.markdown(faits)
