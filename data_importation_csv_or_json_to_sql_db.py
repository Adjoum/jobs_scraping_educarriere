import json
import csv
import datetime
import pandas as pd
import os
import sys
from dateutil import parser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ajoutez le chemin du dossier api au path pour pouvoir importer les modèles
sys.path.append(os.path.join(os.path.dirname(__file__), "api"))

# Importer les modèles depuis api/models.py
from api.models import Base, JobOffer, get_engine, create_tables

# Ajouter au début de votre script d'importation, avant l'importation
'''def clear_database(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Supprimer toutes les offres d'emploi
        session.query(JobOffer).delete()
        session.commit()
        print("Base de données vidée avec succès.")
    except Exception as e:
        session.rollback()
        print(f"Erreur lors du vidage de la base de données: {str(e)}")
    finally:
        session.close()'''

'''def parse_date(date_str):
    """Convertit une chaîne de date en objet date"""
    if not date_str or date_str == "":
        return None
    try:
        return parser.parse(date_str).date()
    except:
        return None'''

def parse_date(date_str):
    if not date_str or date_str == "":
        return None
    try:
        return datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
    except Exception as e:
        print(f"Erreur lors de la conversion de la date '{date_str}': {str(e)}")
        return None

def import_from_json(json_file, engine):
    """Importe les données depuis un fichier JSON"""
    print(f"Importation depuis {json_file}...")

    # Créer une session
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Charger les données JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            jobs_data = json.load(f)

        # Compter le nombre d'offres à importer
        print(f"Fichier chargé. {len(jobs_data)} offres trouvées.")

        # Garder une trace des offres importées et ignorées
        imported_count = 0
        skipped_count = 0

        # Traiter chaque offre
        for job_data in jobs_data:
            # Vérifier si l'offre existe déjà par son offer_id
            offer_id = job_data.get('id') or job_data.get('offer_id')

            if not offer_id:
                print(f"Offre sans ID trouvée: {job_data.get('title', 'Sans titre')}. Génération d'un ID unique.")
                # Générer un ID basé sur le titre et l'entreprise
                title = job_data.get('title', '')
                entreprise = job_data.get('entreprise', '')
                offer_id = f"gen_{hash(title + entreprise) % 10000000}"

            existing = session.query(JobOffer).filter_by(offer_id=offer_id).first()

            if existing:
                skipped_count += 1
                continue

            # Préparer les dates
            date_edition = parse_date(job_data.get('date_edition'))
            date_limite = parse_date(job_data.get('date_limite'))
            date_publication = parse_date(job_data.get('date_publication'))

            # Créer l'objet JobOffer
            job_offer = JobOffer(
                offer_id=offer_id,
                type=job_data.get('type', ''),
                title=job_data.get('title', ''),
                url=job_data.get('url', ''),
                code=job_data.get('code', ''),
                date_edition=date_edition,
                date_limite=date_limite,
                metier=job_data.get('metier', ''),
                niveau=job_data.get('niveau', ''),
                experience=job_data.get('experience', ''),
                lieu=job_data.get('lieu', ''),
                date_publication=date_publication,
                entreprise=job_data.get('entreprise', ''),
                description_poste=job_data.get('description_poste', ''),
                profil_poste=job_data.get('profil_poste', ''),
                dossier_candidature=job_data.get('dossier_candidature', ''),
                email_candidature=job_data.get('email_candidature', ''),
                description_complete=job_data.get('description_complete', ''),
                date_added=datetime.datetime.now().date()
            )

            # Ajouter l'offre à la session
            session.add(job_offer)
            imported_count += 1

            # Valider les changements tous les 100 éléments
            if imported_count % 100 == 0:
                session.commit()
                print(f"  {imported_count} offres importées...")

        # Valider les derniers changements
        session.commit()
        print(
            f"Importation terminée: {imported_count} offres importées, {skipped_count} offres ignorées (déjà existantes)")

    except Exception as e:
        session.rollback()
        print(f"Erreur lors de l'importation: {str(e)}")
    finally:
        session.close()


def import_from_csv(csv_file, engine):
    """Importe les données depuis un fichier CSV"""
    print(f"Importation depuis {csv_file}...")

    # Créer une session
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Charger les données CSV avec Pandas
        df = pd.read_csv(csv_file, encoding='utf-8-sig')

        # Compter le nombre d'offres à importer
        print(f"Fichier chargé. {len(df)} offres trouvées.")

        # Garder une trace des offres importées et ignorées
        imported_count = 0
        skipped_count = 0

        # Traiter chaque offre
        for _, row in df.iterrows():
            # Convertir la ligne en dictionnaire
            job_data = row.to_dict()

            # Vérifier si l'offre existe déjà par son offer_id
            offer_id = str(job_data.get('id') or job_data.get('offer_id') or '')

            if not offer_id or offer_id == 'nan':
                print(f"Offre sans ID trouvée: {job_data.get('title', 'Sans titre')}. Génération d'un ID unique.")
                # Générer un ID basé sur le titre et l'entreprise
                title = str(job_data.get('title', ''))
                entreprise = str(job_data.get('entreprise', ''))
                offer_id = f"gen_{hash(title + entreprise) % 10000000}"

            existing = session.query(JobOffer).filter_by(offer_id=offer_id).first()

            if existing:
                skipped_count += 1
                continue

            # Préparer les dates
            date_edition = parse_date(job_data.get('date_edition'))
            date_limite = parse_date(job_data.get('date_limite'))
            date_publication = parse_date(job_data.get('date_publication'))

            # Nettoyer les valeurs NaN
            for key, value in job_data.items():
                if pd.isna(value):
                    job_data[key] = ""

            # Créer l'objet JobOffer
            job_offer = JobOffer(
                offer_id=offer_id,
                type=job_data.get('type', ''),
                title=job_data.get('title', ''),
                url=job_data.get('url', ''),
                code=job_data.get('code', ''),
                date_edition=date_edition,
                date_limite=date_limite,
                metier=job_data.get('metier', ''),
                niveau=job_data.get('niveau', ''),
                experience=job_data.get('experience', ''),
                lieu=job_data.get('lieu', ''),
                date_publication=date_publication,
                entreprise=job_data.get('entreprise', ''),
                description_poste=job_data.get('description_poste', ''),
                profil_poste=job_data.get('profil_poste', ''),
                dossier_candidature=job_data.get('dossier_candidature', ''),
                email_candidature=job_data.get('email_candidature', ''),
                description_complete=job_data.get('description_complete', ''),
                date_added=datetime.datetime.now().date()
            )

            # Ajouter l'offre à la session
            session.add(job_offer)
            imported_count += 1

            # Valider les changements tous les 100 éléments
            if imported_count % 100 == 0:
                session.commit()
                print(f"  {imported_count} offres importées...")

        # Valider les derniers changements
        session.commit()
        print(
            f"Importation terminée: {imported_count} offres importées, {skipped_count} offres ignorées (déjà existantes)")

    except Exception as e:
        session.rollback()
        print(f"Erreur lors de l'importation: {str(e)}")
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    # Configurer le parseur d'arguments
    parser = argparse.ArgumentParser(
        description="Importer des données dans la base de données SQL depuis des fichiers JSON ou CSV")
    parser.add_argument("--file", required=True, help="Chemin vers le fichier JSON ou CSV à importer")
    parser.add_argument("--db", default="sqlite:///educarriere_jobs.db",
                        help="URL de connexion à la base de données (défaut: sqlite:///educarriere_jobs.db)")

    # Analyser les arguments
    args = parser.parse_args()

    # Configurer la base de données
    engine = get_engine(args.db)

    # Puis appeler cette fonction avant d'importer
    #clear_database(engine)

    create_tables(engine)

    # Importer les données
    if args.file.lower().endswith('.json'):
        import_from_json(args.file, engine)
    elif args.file.lower().endswith('.csv'):
        import_from_csv(args.file, engine)
    else:
        print(f"Format de fichier non supporté: {args.file}")
        print("Seuls les fichiers JSON et CSV sont supportés.")