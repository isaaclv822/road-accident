"""Point d'entrée du dashboard : déclare les pages et le menu de navigation.

Lancer depuis la racine du projet :  streamlit run app.py
"""
import streamlit as st

page = st.navigation([
    st.Page("tableau_de_bord.py", title="Tableau de bord", icon="📊", default=True),
    st.Page("assistant_ia.py", title="Assistant IA", icon="🤖"),
])
page.run()
