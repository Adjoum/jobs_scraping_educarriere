from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from pydantic import BaseModel
from typing import Optional, List
import datetime
import os
# Base SQLAlchemy pour les modèles
Base = declarative_base()

class JobOffer(Base):
    """Modèle SQLAlchemy pour les offres d'emploi"""
    __tablename__ = "job_offers"

    id = Column(Integer, primary_key=True)
    offer_id = Column(String, unique=True, index=True)  # ID d'origine du site
    type = Column(String, index=True)
    title = Column(String, index=True)
    url = Column(String)
    code = Column(String)
    date_edition = Column(Date)
    date_limite = Column(Date, index=True)
    metier = Column(String, index=True)
    niveau = Column(String, index=True)
    experience = Column(String)
    lieu = Column(String, index=True)
    date_publication = Column(Date, index=True)
    entreprise = Column(String, index=True)
    description_poste = Column(Text)
    profil_poste = Column(Text)
    dossier_candidature = Column(Text)
    email_candidature = Column(String)
    description_complete = Column(Text)
    date_added = Column(Date, index=True)

    def __repr__(self):
        return f"<JobOffer(id={self.id}, title='{self.title}', entreprise='{self.entreprise}')>"


# Modèles Pydantic pour l'API
class JobOfferBase(BaseModel):
    """Schéma de base pour les offres d'emploi"""
    type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    code: Optional[str] = None
    date_edition: Optional[datetime.date] = None
    date_limite: Optional[datetime.date] = None
    metier: Optional[str] = None
    niveau: Optional[str] = None
    experience: Optional[str] = None
    lieu: Optional[str] = None
    date_publication: Optional[datetime.date] = None
    entreprise: Optional[str] = None
    description_poste: Optional[str] = None
    profil_poste: Optional[str] = None
    dossier_candidature: Optional[str] = None
    email_candidature: Optional[str] = None
    description_complete: Optional[str] = None


class JobOfferCreate(JobOfferBase):
    """Schéma pour la création d'une offre d'emploi"""
    offer_id: str
    title: str  # Obligatoire pour la création


class JobOfferResponse(JobOfferBase):
    """Schéma pour la réponse API"""
    id: int
    offer_id: Optional[str] = None
    date_added: Optional[datetime.date] = None

    class Config:
        #orm_mode = True
        from_attributes = True


class StatsResponse(BaseModel):
    """Schéma pour les statistiques"""
    total_jobs: int
    by_type: dict
    new_today: int
    unique_companies: int


# Fonctions helper pour la base de données
def get_engine(database_url):
    """Crée et retourne un moteur SQLAlchemy"""
    return create_engine(database_url)


def get_session_maker(engine):
    """Crée et retourne un SessionMaker SQLAlchemy"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables(engine):
    """Crée toutes les tables dans la base de données"""
    Base.metadata.create_all(bind=engine)