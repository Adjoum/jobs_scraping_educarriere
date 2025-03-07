from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc
from typing import List, Optional
import datetime
from dateutil import parser
from contextlib import asynccontextmanager
import sys
import os

#sys.path.append(os.path.dirname(__file__))
# Importer les modèles depuis le fichier models.py
from api.models import (
    Base, JobOffer, JobOfferResponse, StatsResponse,
    get_engine, get_session_maker, create_tables, JobOfferCreate
)

# Configuration SQLAlchemy
DATABASE_URL = "sqlite:///educarriere_jobs.db"

engine = get_engine(DATABASE_URL)
SessionLocal = get_session_maker(engine)

# Créer les tables si elles n'existent pas
create_tables(engine)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code qui s'exécute au démarrage
    add_test_data()
    yield
    # Code qui s'exécute à l'arrêt (nettoyage)
    pass

# Créer l'application FastAPI avec le gestionnaire de cycle de vie
app = FastAPI(
    title="API Offres d'Emploi Educarriere",
    description="API pour rechercher et filtrer les offres d'emploi scrapées depuis Educarriere.ci",
    version="1.0.0",
    lifespan=lifespan
)
# Créer l'application FastAPI
'''app = FastAPI(
    title="API Offres d'Emploi Educarriere",
    description="API pour rechercher et filtrer les offres d'emploi scrapées depuis Educarriere.ci",
    version="1.0.0"
)'''

# Configurer CORS pour permettre l'accès depuis Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://huggingface.co/spaces/Adjoumani/searchjobin-ivorycost"],  # Or "*" (en local) À remplacer par l'URL de votre app Streamlit en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dépendance pour obtenir la session de BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API Educarriere Jobs", "docs": "/docs"}

# Point de terminaison pour récupérer les statistiques
@app.get("/stats/", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    try:
        # Nombre total d'offres
        total_jobs = db.query(func.count(JobOffer.id)).scalar()

        # Nombre d'offres par type
        types = db.query(JobOffer.type, func.count(JobOffer.id)).group_by(JobOffer.type).all()
        types_dict = {t[0]: t[1] for t in types}

        # Offres ajoutées aujourd'hui
        today = datetime.datetime.now().date()
        new_jobs_today = db.query(func.count(JobOffer.id)).filter(JobOffer.date_added == today).scalar()

        # Nombre d'entreprises uniques
        unique_companies = db.query(func.count(func.distinct(JobOffer.entreprise))).scalar()

        return {
            "total_jobs": total_jobs,
            "by_type": types_dict,
            "new_today": new_jobs_today,
            "unique_companies": unique_companies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des statistiques: {str(e)}")

@app.get("/db-stats")
def get_db_stats(db: Session = Depends(get_db)):
    """Renvoie des statistiques sur la base de données"""
    stats = {
        "total_jobs": db.query(func.count(JobOffer.id)).scalar(),
        "newest_job": db.query(JobOffer).order_by(desc(JobOffer.date_added)).first(),
        "last_update": db.query(func.max(JobOffer.date_added)).scalar(),
        "job_types": {
            type_name: count for type_name, count in 
            db.query(JobOffer.type, func.count(JobOffer.id)).group_by(JobOffer.type).all()
        }
    }
    
    if stats["newest_job"]:
        stats["newest_job"] = {
            "id": stats["newest_job"].id,
            "title": stats["newest_job"].title,
            "added_on": stats["newest_job"].date_added.isoformat() if stats["newest_job"].date_added else None
        }
    
    return stats

@app.get("/latest-jobs")
def get_latest_jobs(limit: int = 10, db: Session = Depends(get_db)):
    """Renvoie les dernières offres ajoutées à la base de données"""
    latest_jobs = db.query(JobOffer).order_by(desc(JobOffer.date_added), desc(JobOffer.id)).limit(limit).all()
    return latest_jobs

# Point de terminaison pour récupérer les valeurs distinctes (pour les filtres)
@app.get("/filter-values/{field}")
def get_filter_values(field: str, db: Session = Depends(get_db)):
    valid_fields = {"type", "lieu", "niveau", "metier", "entreprise"}

    if field not in valid_fields:
        raise HTTPException(status_code=400,
                            detail=f"Champ invalide. Les champs valides sont: {', '.join(valid_fields)}")

    try:
        # Récupérer l'attribut de la classe par son nom
        attr = getattr(JobOffer, field)

        # Requête pour obtenir les valeurs distinctes
        values = db.query(attr).distinct().filter(attr != None, attr != "").all()

        # Transformer la liste de tuples en liste simple
        flat_values = [v[0] for v in values]

        return sorted(flat_values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des valeurs de filtre: {str(e)}")


@app.get("/jobs/", response_model=List[JobOfferResponse])
def search_jobs(
        q: Optional[str] = Query(None, description="Mots-clés de recherche"),
        type: Optional[str] = None,
        lieu: Optional[str] = None,
        niveau: Optional[str] = None,
        metier: Optional[str] = None,
        entreprise: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        exclude_expired: bool = True,
        sort_by: str = "date_added",
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
        db: Session = Depends(get_db)
):
    query = db.query(JobOffer)

    # Filtrage par mots-clés
    if q:
        search_terms = q.split()
        for term in search_terms:
            query = query.filter(
                or_(
                    JobOffer.title.ilike(f"%{term}%"),
                    JobOffer.description_poste.ilike(f"%{term}%"),
                    JobOffer.entreprise.ilike(f"%{term}%"),
                    JobOffer.profil_poste.ilike(f"%{term}%"),
                    JobOffer.metier.ilike(f"%{term}%")
                )
            )

    # Filtres additionnels
    if type:
        query = query.filter(JobOffer.type == type)
    if lieu:
        query = query.filter(JobOffer.lieu.ilike(f"%{lieu}%"))
    if niveau:
        # Gérer les listes de niveaux (ex: "BAC+2,BAC+3")
        niveau_list = niveau.split(",")
        niveau_filters = []
        for n in niveau_list:
            niveau_filters.append(JobOffer.niveau.ilike(f"%{n.strip()}%"))
        if niveau_filters:
            query = query.filter(or_(*niveau_filters))
    if metier:
        query = query.filter(JobOffer.metier.ilike(f"%{metier}%"))
    if entreprise:
        query = query.filter(JobOffer.entreprise.ilike(f"%{entreprise}%"))

    # Filtrage par date
    if date_from:
        try:
            date_from_obj = parser.parse(date_from).date()
            query = query.filter(JobOffer.date_publication >= date_from_obj)
        except:
            pass

    if date_to:
        try:
            date_to_obj = parser.parse(date_to).date()
            query = query.filter(JobOffer.date_publication <= date_to_obj)
        except:
            pass

    # Filtrer les offres expirées
    if exclude_expired:
        today = datetime.datetime.now().date()
        query = query.filter(or_(
            JobOffer.date_limite >= today,
            JobOffer.date_limite == None
        ))

    # Tri
    if sort_by in ["date_added", "date_publication", "date_limite", "title", "entreprise"]:
        sort_column = getattr(JobOffer, sort_by)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)
    else:
        # Par défaut, trier par date d'ajout
        query = query.order_by(desc(JobOffer.date_added))

    # Compter le total avant pagination
    total_count = query.count()

    # Pagination
    results = query.offset(offset).limit(limit).all()

    # Ajouter le total dans les headers HTTP
    return results


@app.get("/jobs/{job_id}", response_model=JobOfferResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Offre d'emploi non trouvée")
    return job


# Route pour la santé de l'API
@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}


@app.post("/import")
async def import_jobs(jobs: List[JobOfferCreate], db: Session = Depends(get_db)):
    """Importe des nouvelles offres d'emploi dans la base de données"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Tentative d'importation de {len(jobs)} offres")
    imported_count = 0
    
    for job_data in jobs:
        existing = db.query(JobOffer).filter(JobOffer.offer_id == job_data.offer_id).first()
        if not existing:
            new_job = JobOffer(**job_data.dict(), date_added=datetime.datetime.now().date())
            db.add(new_job)
            imported_count += 1
            logger.info(f"Nouvelle offre importée: {job_data.title}")
    
    db.commit()
    logger.info(f"Importation terminée: {imported_count} nouvelles offres ajoutées")
    
    return {"status": "success", "imported_count": imported_count}

# Ajouter des données de test si la base est vide
#@app.on_event("startup")
def add_test_data():
    db = SessionLocal()
    try:
        # Vérifier si la base est vide
        count = db.query(func.count(JobOffer.id)).scalar()

        if count == 0:
            print("Base de données vide, ajout de données de test...")

            # Données de test
            test_jobs = [
                {
                    "offer_id": "129440",
                    "type": "Emploi",
                    "title": "Développeur Full Stack",
                    "entreprise": "Tech Solutions CI",
                    "metier": "Informatique",
                    "niveau": "BAC+3",
                    "experience": "2 ans",
                    "lieu": "Abidjan",
                    "date_publication": datetime.date.today() - datetime.timedelta(days=2),
                    "date_limite": datetime.date.today() + datetime.timedelta(days=14),
                    "description_poste": "Nous recherchons un développeur Full Stack talentueux pour rejoindre notre équipe...",
                    "profil_poste": "- Maîtrise de JavaScript, React et Node.js\n- Expérience avec les bases de données SQL et NoSQL\n- Bonne connaissance des principes de développement agile",
                    "url": "https://emploi.educarriere.ci/offre-129440",
                    "date_added": datetime.date.today()
                },
                {
                    "offer_id": "129441",
                    "type": "Stage",
                    "title": "Assistant Marketing Digital",
                    "entreprise": "AfriMedia Group",
                    "metier": "Marketing",
                    "niveau": "BAC+2",
                    "experience": "Débutant",
                    "lieu": "Abidjan",
                    "date_publication": datetime.date.today() - datetime.timedelta(days=3),
                    "date_limite": datetime.date.today() + datetime.timedelta(days=10),
                    "description_poste": "Stage de 6 mois en marketing digital pour accompagner notre équipe dans la gestion des réseaux sociaux...",
                    "profil_poste": "- Formation en marketing ou communication\n- Maîtrise des outils de design (Canva, Photoshop)\n- Bonne capacité rédactionnelle",
                    "url": "https://emploi.educarriere.ci/offre-129441",
                    "date_added": datetime.date.today()
                },
                {
                    "offer_id": "129442",
                    "type": "Consultance",
                    "title": "Expert Comptable",
                    "entreprise": "Deloitte Côte d'Ivoire",
                    "metier": "Finance",
                    "niveau": "BAC+5",
                    "experience": "5 ans",
                    "lieu": "Abidjan",
                    "date_publication": datetime.date.today() - datetime.timedelta(days=1),
                    "date_limite": datetime.date.today() + datetime.timedelta(days=21),
                    "description_poste": "Mission de consultance pour l'audit financier d'une entreprise du secteur agroalimentaire...",
                    "profil_poste": "- Diplôme d'expert-comptable\n- Expérience significative en audit\n- Maîtrise du français et de l'anglais",
                    "url": "https://emploi.educarriere.ci/offre-129442",
                    "date_added": datetime.date.today()
                },
                {
                    "offer_id": "129443",
                    "type": "Emploi",
                    "title": "Responsable Ressources Humaines",
                    "entreprise": "Orange CI",
                    "metier": "Ressources Humaines",
                    "niveau": "BAC+4",
                    "experience": "3 ans",
                    "lieu": "Abidjan",
                    "date_publication": datetime.date.today() - datetime.timedelta(days=5),
                    "date_limite": datetime.date.today() + datetime.timedelta(days=7),
                    "description_poste": "Nous recherchons un Responsable RH dynamique pour superviser tous les aspects de la gestion des ressources humaines...",
                    "profil_poste": "- Formation supérieure en RH ou équivalent\n- Expérience dans un poste similaire\n- Excellente connaissance du droit du travail ivoirien",
                    "url": "https://emploi.educarriere.ci/offre-129443",
                    "date_added": datetime.date.today() - datetime.timedelta(days=5)
                },
                {
                    "offer_id": "129444",
                    "type": "Stage",
                    "title": "Stagiaire en Agronomie",
                    "entreprise": "Cargill",
                    "metier": "Agriculture",
                    "niveau": "BAC+3",
                    "experience": "Débutant",
                    "lieu": "San Pedro",
                    "date_publication": datetime.date.today() - datetime.timedelta(days=4),
                    "date_limite": datetime.date.today() + datetime.timedelta(days=16),
                    "description_poste": "Stage de 3 mois pour participer à nos programmes de recherche sur l'amélioration des cultures de cacao...",
                    "profil_poste": "- Formation en agronomie\n- Intérêt pour la recherche agricole\n- Disponibilité pour travail sur le terrain",
                    "url": "https://emploi.educarriere.ci/offre-129444",
                    "date_added": datetime.date.today() - datetime.timedelta(days=4)
                }
            ]

            # Ajouter les offres de test
            for job_data in test_jobs:
                job = JobOffer(**job_data)
                db.add(job)

            db.commit()
            print("Données de test ajoutées avec succès!")
        else:
            print(f"Base de données contient déjà {count} offres, pas besoin d'ajouter des données de test.")
    except Exception as e:
        db.rollback()
        print(f"Erreur lors de l'ajout des données de test: {str(e)}")
    finally:
        db.close()


# Démarrer le serveur directement en mode développement
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
