import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import re
import random
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Date, MetaData, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

# Ajouter le chemin du dossier api au path pour pouvoir importer les modèles
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "api"))

# Importer les modèles depuis api/models.py
from api.models import Base, JobOffer, get_engine, get_session_maker, create_tables

# Configuration SQLAlchemy
DATABASE_URL = "sqlite:///educarriere_jobs.db"

engine = get_engine(DATABASE_URL)
Session = get_session_maker(engine)
create_tables(engine)

class EducarriereScraper:
    def __init__(self, api_key, output_dir='educarriere_data'):
        self.api_key = api_key
        self.base_url = 'https://emploi.educarriere.ci'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Définir tous les champs possibles pour s'assurer qu'ils sont inclus dans le CSV
        self.all_possible_fields = [
            'type', 'title', 'url', 'id', 'code', 'date_edition', 'date_limite',
            'metier', 'niveau', 'experience', 'lieu', 'date_publication',
            'entreprise', 'description_poste', 'profil_poste', 'dossier_candidature',
            'email_candidature', 'description_complete'
        ]
        # Créer le dossier de sortie
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        # Dossier pour les données progressives
        self.progress_dir = os.path.join(self.output_dir, 'progress')
        os.makedirs(self.progress_dir, exist_ok=True)
        # Dossier pour les logs
        self.logs_dir = os.path.join(self.output_dir, 'logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        # Horodatage pour identifier cette session de scraping
        self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Fichier de log pour cette session
        self.log_file = os.path.join(self.logs_dir, f'scraping_log_{self.session_timestamp}.txt')
        # Charger les offres existantes
        self.existing_jobs = self.load_existing_jobs()
        self.existing_job_ids = set(job.get('id', '') for job in self.existing_jobs if job.get('id'))
        self.log(
            f"Offres existantes chargées: {len(self.existing_jobs)} offres, {len(self.existing_job_ids)} IDs uniques")

    def log(self, message):
        """Écrire un message dans le fichier de log et l'afficher"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')

    def load_existing_jobs(self):
        """Charger les offres d'emploi existantes"""
        latest_json = os.path.join(self.output_dir, 'educarriere_jobs_latest.json')
        if os.path.exists(latest_json):
            try:
                with open(latest_json, 'r', encoding='utf-8') as f:
                    existing_jobs = json.load(f)
                self.log(f"Fichier des offres existantes chargé: {latest_json}")
                return existing_jobs
            except Exception as e:
                self.log(f"Erreur lors du chargement des offres existantes: {str(e)}")

        self.log("Aucun fichier d'offres existantes trouvé ou erreur de chargement. Démarrage avec une liste vide.")
        return []

    def scrape_job_listings(self, page=1, max_retries=3):
        """Scrape les offres d'emploi de la page spécifiée avec gestion des tentatives"""
        # Vérifier le format d'URL correct pour la pagination
        if page == 1:
            url = f"{self.base_url}/emploi/page/emploi/1"
        else:
            url = f"{self.base_url}/emploi/page/emploi/{page}"

        self.log(f"URL de scraping: {url}")

        retry_count = 0
        while retry_count < max_retries:
            try:
                self.log(f"Scraping de la page {page} (tentative {retry_count + 1}/{max_retries})...")

                # Paramètres pour ScraperAPI avec temps de rendu plus long
                payload = {
                    'api_key': self.api_key,
                    'url': url,
                    'render': 'true',
                    'render_js': 'true',  # S'assurer que JavaScript est rendu
                    'wait_for': '3000'  # Attendre 3 secondes pour le chargement du JS
                }

                response = requests.get('https://api.scraperapi.com/', params=payload)
                response.raise_for_status()

                # Vérifier si la réponse est valide
                if not response.text:
                    self.log(f"Réponse vide pour la page {page}, nouvelle tentative...")
                    retry_count += 1
                    time.sleep(random.uniform(4, 7))  # Pause aléatoire
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Vérifier si la page existe (recherche d'un élément connu)
                if not soup.find('div', class_='container'):
                    self.log(f"Structure de page non reconnue pour la page {page}, nouvelle tentative...")
                    retry_count += 1
                    time.sleep(random.uniform(4, 7))
                    continue

                # Recherche de tous les conteneurs d'offres d'emploi
                job_offers = soup.find_all('div', class_='col-md-6 wow fadeInLeft')

                # Vérifier si des offres ont été trouvées
                if not job_offers:
                    self.log(f"Aucune offre trouvée sur la page {page} (tentative {retry_count + 1}/{max_retries})")

                    # Vérifier si c'est un problème de sélecteur ou de pagination
                    pagination = soup.find('div', class_='rt-pagination')
                    if pagination:
                        self.log("Pagination trouvée, la page existe mais le format pourrait être différent")

                    # Sauvegarder la page HTML pour analyse
                    debug_file = os.path.join(self.logs_dir, f'debug_page_{page}_{self.session_timestamp}.html')
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    self.log(f"Page HTML sauvegardée dans {debug_file} pour analyse")

                    retry_count += 1
                    time.sleep(random.uniform(4, 7))
                    continue

                jobs = []
                new_jobs = []

                for job_offer in job_offers:
                    # Initialiser le job avec tous les champs (vides)
                    job = {field: "" for field in self.all_possible_fields}

                    try:
                        # Vérifier si le div contient une offre valide
                        post_div = job_offer.find('div', class_='rt-post post-md style-8')
                        if not post_div:
                            continue

                        # Extraire le titre de l'offre
                        title_element = job_offer.find('h4', class_='post-title')
                        if title_element:
                            job['title'] = title_element.text.strip()

                            # Extraire le lien de l'offre
                            link_element = title_element.find('a')
                            if link_element and link_element.has_attr('href'):
                                job['url'] = link_element['href']
                                # Extraire l'ID de l'offre à partir de l'URL
                                match = re.search(r'offre-(\d+)-', job['url'])
                                if match:
                                    job['id'] = match.group(1)

                        # Extraire le type d'offre (Consultance, Emploi, etc.)
                        type_element = job_offer.find('a', class_='racing')
                        if type_element:
                            job['type'] = type_element.text.strip()

                        # Extraire les métadonnées (Code, Date d'édition, Date limite)
                        metadata = job_offer.find('span', class_='rt-meta')
                        if metadata:
                            # Chercher tous les li dans la métadonnée
                            for li in metadata.find_all('li'):
                                li_text = li.text.strip()
                                if 'Code:' in li_text:
                                    code_span = li.find('span', style='color:#FF0000;font-size: 10px;')
                                    if code_span:
                                        job['code'] = code_span.text.strip()
                                elif 'Date d\'édition:' in li_text:
                                    date_span = li.find('span', style='color:#FF0000;font-size: 10px;')
                                    if date_span:
                                        job['date_edition'] = date_span.text.strip()
                                elif 'Date limite:' in li_text:
                                    limit_span = li.find('span', style='color:#FF0000;font-size: 10px;')
                                    if limit_span:
                                        job['date_limite'] = limit_span.text.strip()

                    except Exception as e:
                        self.log(f"Erreur lors de l'extraction d'une offre: {str(e)}")
                        continue

                    # Vérifier si c'est une nouvelle offre
                    if job.get('id') and job['id'] not in self.existing_job_ids:
                        self.log(f"Nouvelle offre détectée: ID {job['id']} - {job['title']}")
                        new_jobs.append(job)
                    elif not job.get('id'):
                        self.log(f"Offre sans ID détectée (sera considérée comme nouvelle): {job['title']}")
                        new_jobs.append(job)
                    else:
                        self.log(f"Offre existante ignorée: ID {job['id']} - {job['title']}")

                    jobs.append(job)

                self.log(f"Page {page}: {len(jobs)} offres trouvées, dont {len(new_jobs)} nouvelles offres")
                return new_jobs  # Retourner uniquement les nouvelles offres

            except requests.exceptions.RequestException as e:
                self.log(f"Erreur de requête HTTP lors du scraping de la page {page}: {str(e)}")
                retry_count += 1
                time.sleep(random.uniform(5, 10))  # Pause plus longue après une erreur

            except Exception as e:
                self.log(f"Erreur lors du scraping de la page {page}: {str(e)}")
                retry_count += 1
                time.sleep(random.uniform(5, 10))

        self.log(f"Échec après {max_retries} tentatives pour la page {page}")
        return []

    def scrape_job_details(self, job_url, max_retries=3):
        """Scrape les détails d'une offre d'emploi spécifique avec gestion des tentatives"""
        retry_count = 0
        while retry_count < max_retries:
            try:
                self.log(f"Scraping des détails de {job_url} (tentative {retry_count + 1}/{max_retries})...")

                # Paramètres pour ScraperAPI avec temps de rendu plus long
                payload = {
                    'api_key': self.api_key,
                    'url': job_url,
                    'render': 'true',
                    'render_js': 'true',
                    'wait_for': '3000'
                }

                response = requests.get('https://api.scraperapi.com/', params=payload)
                response.raise_for_status()

                if not response.text:
                    self.log(f"Réponse vide pour {job_url}, nouvelle tentative...")
                    retry_count += 1
                    time.sleep(random.uniform(3, 6))
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Initialiser les détails avec des champs vides
                details = {field: "" for field in self.all_possible_fields if
                           field not in ['type', 'title', 'url', 'id', 'code', 'date_edition', 'date_limite']}

                # Titre de l'offre (pour vérification)
                title_element = soup.find("h2", class_="title")
                if title_element:
                    title = title_element.text.strip()
                    self.log(f"Titre de l'offre sur la page de détail: {title}")
                else:
                    self.log(f"Titre non trouvé pour {job_url}, nouvelle tentative...")
                    retry_count += 1
                    time.sleep(random.uniform(3, 6))
                    continue

                # Extraire les informations à partir de list-group
                details_ul = soup.find("ul", class_="list-group")
                if details_ul:
                    for item in details_ul.find_all("li", class_="list-group-item"):
                        text = item.text.strip()
                        if "Métier(s):" in text:
                            details['metier'] = text.replace("Métier(s):", "").strip()
                        elif "Niveau(x):" in text:
                            details['niveau'] = text.replace("Niveau(x):", "").strip()
                        elif "Expérience:" in text:
                            details['experience'] = text.replace("Expérience:", "").strip()
                        elif "Lieu:" in text:
                            details['lieu'] = text.replace("Lieu:", "").strip()
                        elif "Date de publication:" in text:
                            details['date_publication'] = text.replace("Date de publication:", "").strip()
                        elif "Date limite:" in text:
                            details['date_limite'] = text.replace("Date limite:", "").strip()

                # Extraire la description complète et les sections spécifiques
                post_body = soup.find("div", class_="post-body")
                if post_body:
                    # Extraire le contenu principal
                    content_div = post_body.find('div', class_='col-xl-9')
                    if content_div:
                        # Texte complet
                        details['description_complete'] = content_div.text.strip()

                        # Entreprise (généralement dans le premier paragraphe)
                        first_p = content_div.find('p')
                        if first_p:
                            details['entreprise'] = first_p.text.strip()

                        # Trouver les sections avec des titres soulignés
                        for p in content_div.find_all('p'):
                            strong_tag = p.find('span', style='text-decoration: underline;')
                            if strong_tag:
                                title_text = strong_tag.text.strip()
                                next_p = p.find_next('p')
                                if next_p:
                                    if 'Description du poste' in title_text:
                                        details['description_poste'] = next_p.text.strip()
                                    elif 'Profil du poste' in title_text:
                                        details['profil_poste'] = next_p.text.strip()
                                    elif 'Dossiers de candidature' in title_text:
                                        dossier_text = next_p.text.strip()
                                        details['dossier_candidature'] = dossier_text

                                        # Extraire les emails du texte de candidature
                                        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                                        emails = re.findall(email_pattern, dossier_text)
                                        if emails:
                                            details['email_candidature'] = emails[0]

                return details

            except requests.exceptions.RequestException as e:
                self.log(f"Erreur de requête HTTP lors du scraping des détails pour {job_url}: {str(e)}")
                retry_count += 1
                time.sleep(random.uniform(4, 8))

            except Exception as e:
                self.log(f"Erreur lors du scraping des détails pour {job_url}: {str(e)}")
                retry_count += 1
                time.sleep(random.uniform(4, 8))

        self.log(f"Échec après {max_retries} tentatives pour les détails de {job_url}")
        return {}

    def scrape_all_jobs_with_details(self, max_pages=3):
        """Scrape toutes les nouvelles offres d'emploi avec leurs détails page par page"""
        all_new_detailed_jobs = []

        for page in range(1, max_pages + 1):
            # Scraper les jobs de cette page (seulement les nouveaux)
            new_jobs = self.scrape_job_listings(page)
            if not new_jobs:
                self.log(f"Aucune nouvelle offre trouvée sur la page {page}. Continuer à la page suivante.")

                # Si nous n'avons trouvé aucune nouvelle offre sur 2 pages consécutives, arrêtons le scraping
                if page > 1 and len(all_new_detailed_jobs) == 0:
                    self.log("Aucune nouvelle offre trouvée sur deux pages consécutives. Arrêt du scraping.")
                    break

                continue

            detailed_new_jobs = []
            self.log(f"Page {page}: {len(new_jobs)} nouvelles offres trouvées, récupération des détails...")

            # Enrichir chaque nouvelle offre de cette page avec ses détails
            for i, job in enumerate(new_jobs):
                if 'url' in job and job['url']:
                    self.log(f"  Traitement de la nouvelle offre {i + 1}/{len(new_jobs)}: {job['title']}")
                    details = self.scrape_job_details(job['url'])
                    job.update(details)
                    detailed_new_jobs.append(job)

                    # Pause aléatoire pour éviter de surcharger le serveur
                    delay = random.uniform(3, 7)
                    self.log(f"  Pause de {delay:.2f} secondes...")
                    time.sleep(delay)
                else:
                    self.log(f"  Offre {i + 1}/{len(new_jobs)} sans URL, ignorée.")

            all_new_detailed_jobs.extend(detailed_new_jobs)
            self.log(f"Page {page} terminée: {len(detailed_new_jobs)} nouvelles offres détaillées récupérées.")

            # Sauvegarder progressivement au cas où le script s'arrête
            if detailed_new_jobs:
                page_csv = os.path.join(self.progress_dir, f'educarriere_new_page_{page}_{self.session_timestamp}.csv')
                page_json = os.path.join(self.progress_dir,
                                         f'educarriere_new_page_{page}_{self.session_timestamp}.json')

                self.save_to_csv(detailed_new_jobs, page_csv)
                self.save_to_json(detailed_new_jobs, page_json)
                self.log(f"Sauvegarde progressive des nouvelles offres de la page {page} effectuée")

            # Pause aléatoire avant de passer à la page suivante
            if page < max_pages:
                delay = random.uniform(8, 15)
                self.log(f"Pause de {delay:.2f} secondes avant de passer à la page suivante...")
                time.sleep(delay)

        return all_new_detailed_jobs

    def save_to_csv(self, jobs, filename):
        """Sauvegarder les offres d'emploi dans un fichier CSV avec tous les champs"""
        # S'assurer que tous les champs possibles sont présents dans chaque job
        for job in jobs:
            for field in self.all_possible_fields:
                if field not in job:
                    job[field] = ""

        # Créer un DataFrame avec l'ordre spécifique des colonnes
        df = pd.DataFrame(jobs, columns=self.all_possible_fields)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        self.log(f"Les offres ont été sauvegardées dans '{filename}' avec tous les champs")

    def save_to_json(self, jobs, filename):
        """Sauvegarder les offres d'emploi dans un fichier JSON"""
        # S'assurer que tous les champs possibles sont présents dans chaque job
        for job in jobs:
            for field in self.all_possible_fields:
                if field not in job:
                    job[field] = ""

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, ensure_ascii=False, indent=4)
        self.log(f"Les offres ont été sauvegardées dans '{filename}' avec tous les champs")

    def update_database(self, new_jobs):
        """Mettre à jour la base de données SQL avec les nouvelles offres"""
        if not new_jobs:
            self.log("Aucune nouvelle offre à ajouter à la base de données.")
            return

        self.log(f"Mise à jour de la base de données avec {len(new_jobs)} nouvelles offres...")

        # Créer une session SQLAlchemy
        session = Session()

        try:
            for job in new_jobs:
                # Convertir les dates
                date_edition = None
                date_limite = None
                date_publication = None

                if job.get('date_edition'):
                    try:
                        date_edition = datetime.strptime(job['date_edition'], "%d/%m/%Y").date()
                    except:
                        pass

                if job.get('date_limite'):
                    try:
                        date_limite = datetime.strptime(job['date_limite'], "%d/%m/%Y").date()
                    except:
                        pass

                if job.get('date_publication'):
                    try:
                        date_publication = datetime.strptime(job['date_publication'], "%d/%m/%Y").date()
                    except:
                        pass

                # Créer un nouvel objet JobOffer
                job_offer = JobOffer(
                    offer_id=job.get('id', ''),
                    type=job.get('type', ''),
                    title=job.get('title', ''),
                    url=job.get('url', ''),
                    code=job.get('code', ''),
                    date_edition=date_edition,
                    date_limite=date_limite,
                    metier=job.get('metier', ''),
                    niveau=job.get('niveau', ''),
                    experience=job.get('experience', ''),
                    lieu=job.get('lieu', ''),
                    date_publication=date_publication,
                    entreprise=job.get('entreprise', ''),
                    description_poste=job.get('description_poste', ''),
                    profil_poste=job.get('profil_poste', ''),
                    dossier_candidature=job.get('dossier_candidature', ''),
                    email_candidature=job.get('email_candidature', ''),
                    description_complete=job.get('description_complete', ''),
                    date_added=datetime.now().date()
                )

                # Ajouter à la session
                session.add(job_offer)

            # Valider les changements
            session.commit()
            self.log(f"Base de données mise à jour avec succès!")

        except Exception as e:
            session.rollback()
            self.log(f"Erreur lors de la mise à jour de la base de données: {str(e)}")
        finally:
            session.close()




engine = create_engine(DATABASE_URL)
Base = declarative_base()


class JobOffer(Base):
    __tablename__ = "job_offers"

    id = Column(Integer, primary_key=True)
    offer_id = Column(String, unique=True)  # ID d'origine du site
    type = Column(String)
    title = Column(String)
    url = Column(String)
    code = Column(String)
    date_edition = Column(Date)
    date_limite = Column(Date)
    metier = Column(String)
    niveau = Column(String)
    experience = Column(String)
    lieu = Column(String)
    date_publication = Column(Date)
    entreprise = Column(String)
    description_poste = Column(Text)
    profil_poste = Column(Text)
    dossier_candidature = Column(Text)
    email_candidature = Column(String)
    description_complete = Column(Text)
    date_added = Column(Date)


# Créer les tables s'elles n'existent pas
Base.metadata.create_all(engine)


# À l'intérieur de votre classe EducarriereScraper
def update_database(self, new_jobs):
    """Mettre à jour la base de données SQL avec les nouvelles offres"""
    if not new_jobs:
        self.log("Aucune nouvelle offre à ajouter à la base de données.")
        return

    self.log(f"Mise à jour de la base de données avec {len(new_jobs)} nouvelles offres...")

    # Créer une session SQLAlchemy
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        for job in new_jobs:
            # Convertir les dates
            date_edition = None
            date_limite = None
            date_publication = None

            if job.get('date_edition'):
                try:
                    date_edition = datetime.datetime.strptime(job['date_edition'], "%d/%m/%Y").date()
                except:
                    pass

            if job.get('date_limite'):
                try:
                    date_limite = datetime.datetime.strptime(job['date_limite'], "%d/%m/%Y").date()
                except:
                    pass

            if job.get('date_publication'):
                try:
                    date_publication = datetime.datetime.strptime(job['date_publication'], "%d/%m/%Y").date()
                except:
                    pass

            # Créer un nouvel objet JobOffer
            job_offer = JobOffer(
                offer_id=job.get('id', ''),
                type=job.get('type', ''),
                title=job.get('title', ''),
                url=job.get('url', ''),
                code=job.get('code', ''),
                date_edition=date_edition,
                date_limite=date_limite,
                metier=job.get('metier', ''),
                niveau=job.get('niveau', ''),
                experience=job.get('experience', ''),
                lieu=job.get('lieu', ''),
                date_publication=date_publication,
                entreprise=job.get('entreprise', ''),
                description_poste=job.get('description_poste', ''),
                profil_poste=job.get('profil_poste', ''),
                dossier_candidature=job.get('dossier_candidature', ''),
                email_candidature=job.get('email_candidature', ''),
                description_complete=job.get('description_complete', ''),
                date_added=datetime.datetime.now().date()
            )

            # Ajouter à la session
            session.add(job_offer)

        # Valider les changements
        session.commit()
        self.log(f"Base de données mise à jour avec succès!")

    except Exception as e:
        session.rollback()
        self.log(f"Erreur lors de la mise à jour de la base de données: {str(e)}")
    finally:
        session.close()


# Exécution principale
if __name__ == "__main__":
    # Récupérer la clé API depuis les variables d'environnement pour GitHub Actions
    api_key = os.environ.get('API_KEY', '28a1724f4b8f2f67f01533f615a622ca')

    scraper = EducarriereScraper(api_key)

    # Nombre de pages à scraper (ajustable)
    max_pages =1

    # Débuter le scraping
    scraper.log("Démarrage du scraping pour les nouvelles offres d'emploi uniquement...")
    new_detailed_jobs = scraper.scrape_all_jobs_with_details(max_pages=max_pages)

    # Mettre à jour la base de données avec les nouvelles offres
    scraper.update_database(new_detailed_jobs)

    # Log final
    scraper.log(f"Scraping terminé avec succès! {len(new_detailed_jobs)} nouvelles offres détaillées ajoutées.")