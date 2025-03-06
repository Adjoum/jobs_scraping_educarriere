import streamlit as st
import requests
import pandas as pd
import datetime
from datetime import timedelta
import plotly.express as px

# Configuration de l'application
st.set_page_config(
    page_title="Recherche d'emploi - Educarriere",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URL de l'API (à modifier selon votre environnement)
API_URL = "https://jobs-scraping-educarriere.onrender.com" #http://localhost:8000" for local


# Fonction pour récupérer les données de l'API
def fetch_jobs(query_params=None):
    """Récupère les offres d'emploi depuis l'API avec filtres optionnels"""
    try:
        response = requests.get(f"{API_URL}/jobs/", params=query_params)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Erreur lors de la récupération des données: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Erreur de connexion à l'API: {str(e)}")
        return []


def get_job_details(job_id):
    """Récupère les détails d'une offre d'emploi spécifique"""
    try:
        response = requests.get(f"{API_URL}/jobs/{job_id}")
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Erreur lors de la récupération des détails: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Erreur de connexion à l'API: {str(e)}")
        return None


# Fonction pour formater des dates
def format_date(date_str):
    if not date_str:
        return "Non spécifiée"
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str


# Titre de l'application
st.title("🔍 Recherche d'emploi pour étudiants")
st.write("Trouvez les offres d'emploi et de stage qui correspondent à votre profil")

# Création des filtres dans la barre latérale
st.sidebar.header("Filtres de recherche")

# Champ de recherche par mots-clés
query = st.sidebar.text_input("Mots-clés", placeholder="Ex: développeur, marketing...")

# Filtres additionnels
col1, col2 = st.sidebar.columns(2)
with col1:
    type_offre = st.selectbox(
        "Type d'offre",
        options=["Tous", "Emploi", "Stage", "Consultance"],
        index=0
    )

with col2:
    lieu = st.text_input("Lieu", placeholder="Ex: Abidjan")

niveau = st.sidebar.multiselect(
    "Niveau d'études",
    options=["BAC", "BAC+2", "BAC+3", "BAC+4", "BAC+5", "Doctorat"],
    default=[]
)

metier = st.sidebar.text_input("Secteur/Métier", placeholder="Ex: Informatique, Finance...")

# Bouton de recherche
search_button = st.sidebar.button("🔍 Rechercher", use_container_width=True)

# Préparation des paramètres de requête
query_params = {}
if query:
    query_params["q"] = query
if type_offre != "Tous":
    query_params["type"] = type_offre
if lieu:
    query_params["lieu"] = lieu
if niveau:
    query_params["niveau"] = ",".join(niveau)
if metier:
    query_params["metier"] = metier

# Affichage des statistiques en haut de la page
st.sidebar.markdown("---")
st.sidebar.header("À propos")
st.sidebar.info(
    """
    Cette application vous permet de rechercher parmi les offres d'emploi et de stage 
    récupérées quotidiennement sur Educarriere.ci.

    Les données sont mises à jour chaque jour à minuit.
    """
)

# Exécution de la recherche au chargement ou après clic sur le bouton
if "first_load" not in st.session_state:
    st.session_state.first_load = True
    # Charger quelques offres par défaut au premier chargement
    jobs = fetch_jobs({"limit": 10})
elif search_button:
    jobs = fetch_jobs(query_params)
    if not jobs:
        st.warning("Aucune offre ne correspond à vos critères de recherche.")
else:
    # Réutiliser les résultats précédents si on ne fait pas de nouvelle recherche
    if "jobs" in st.session_state:
        jobs = st.session_state.jobs
    else:
        jobs = fetch_jobs({"limit": 10})

# Sauvegarder les résultats dans la session
st.session_state.jobs = jobs

# Afficher le nombre de résultats
if jobs:
    st.write(f"**{len(jobs)} offres** trouvées")

    # Créer un dataframe pour l'affichage
    df = pd.DataFrame(jobs)

    # Sélection des colonnes à afficher
    display_cols = ["id", "type", "title", "entreprise", "lieu", "niveau", "experience"]
    df_display = df[display_cols].copy() if all(col in df.columns for col in display_cols) else df

    # Formater et renommer les colonnes pour l'affichage
    if not df_display.empty:
        df_display.columns = ["ID", "Type", "Titre", "Entreprise", "Lieu", "Niveau requis", "Expérience"]

    # Afficher le tableau avec les résultats
    st.dataframe(
        df_display,
        column_config={
            "Titre": st.column_config.TextColumn("Titre", width="large"),
        },
        hide_index=True,
        use_container_width=True
    )

    # Sélectionner une offre pour voir les détails
    selected_job_id = st.selectbox("Sélectionnez une offre pour voir les détails:", df["id"].tolist(),
                                   format_func=lambda x: df[df["id"] == x]["title"].iloc[0])

    if selected_job_id:
        # Récupérer les détails complets de l'offre sélectionnée
        job_details = get_job_details(selected_job_id)

        if job_details:
            # Afficher les détails dans deux colonnes
            col1, col2 = st.columns([3, 1])

            with col1:
                st.header(job_details["title"])
                st.subheader(job_details["entreprise"])

                # Afficher les métadonnées
                meta_cols = st.columns(4)
                with meta_cols[0]:
                    st.metric("Type", job_details["type"])
                with meta_cols[1]:
                    st.metric("Lieu", job_details["lieu"] or "Non spécifié")
                with meta_cols[2]:
                    st.metric("Niveau requis", job_details["niveau"] or "Non spécifié")
                with meta_cols[3]:
                    st.metric("Expérience", job_details["experience"] or "Non spécifiée")

                # Onglets pour les différentes sections
                tab1, tab2, tab3 = st.tabs(["📋 Description", "👤 Profil recherché", "📬 Candidature"])

                with tab1:
                    st.markdown("### Description du poste")
                    if "description_poste" in job_details and job_details["description_poste"]:
                        st.write(job_details["description_poste"])
                    else:
                        st.info("Aucune description détaillée disponible.")

                with tab2:
                    st.markdown("### Profil recherché")
                    if "profil_poste" in job_details and job_details["profil_poste"]:
                        st.write(job_details["profil_poste"])
                    else:
                        st.info("Aucune information sur le profil recherché.")

                with tab3:
                    st.markdown("### Comment postuler")
                    if "dossier_candidature" in job_details and job_details["dossier_candidature"]:
                        st.write(job_details["dossier_candidature"])

                        if "email_candidature" in job_details and job_details["email_candidature"]:
                            st.markdown(f"**Email de contact:** {job_details['email_candidature']}")
                    else:
                        st.info("Aucune information sur la candidature.")

            with col2:
                # Afficher un encadré avec des informations clés
                st.markdown("### Informations clés")

                st.info(f"""
                **Date limite:** {format_date(job_details.get('date_limite', ''))}

                **Date de publication:** {format_date(job_details.get('date_publication', ''))}

                **URL de l'offre:**
                [Voir l'offre originale]({job_details.get('url', '#')})
                """)

                # Bouton pour postuler
                if job_details.get('url'):
                    st.link_button("Postuler maintenant", job_details['url'], use_container_width=True)

# Afficher des visualisations ou statistiques
if jobs and len(jobs) > 1:
    st.markdown("---")
    st.header("Analyse des offres")

    chart_cols = st.columns(2)

    with chart_cols[0]:
        # Distribution par type d'offre
        type_counts = pd.DataFrame(jobs).groupby('type').size().reset_index(name='count')
        if not type_counts.empty:
            fig = px.pie(type_counts, values='count', names='type', title="Répartition par type d'offre")
            st.plotly_chart(fig, use_container_width=True)

    with chart_cols[1]:
        # Distribution par lieu
        if 'lieu' in pd.DataFrame(jobs).columns:
            lieu_counts = pd.DataFrame(jobs).groupby('lieu').size().reset_index(name='count')
            lieu_counts = lieu_counts.sort_values('count', ascending=False).head(5)
            if not lieu_counts.empty:
                fig = px.bar(lieu_counts, x='lieu', y='count', title="Top 5 des lieux")
                st.plotly_chart(fig, use_container_width=True)