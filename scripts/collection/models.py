"""SQLAlchemy ORM models for the Dataset Collection Platform."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

# Define Base here to avoid circular imports
Base = declarative_base()


class Project(Base):
    """A dataset collection project."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)
    country = Column(Text, nullable=False, default="Australia")
    status = Column(Text, nullable=False, default="idle")  # idle, running, paused, complete
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Project-level overrides for collection settings
    field_tier = Column(String(20), nullable=True)  # Override PLACES_FIELD_TIER from .env
    search_step_km = Column(Integer, nullable=True)  # Override SEARCH_STEP_KM from .env

    # Relationships
    search_terms = relationship("SearchTerm", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    places = relationship("Place", back_populates="project", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="project", cascade="all, delete-orphan")


class SearchTerm(Base):
    """A search term for a project."""
    __tablename__ = "search_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    term = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="search_terms")


class Job(Base):
    """A collection job (text search or place detail)."""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    job_type = Column(Text, nullable=False)  # text_search or place_detail
    status = Column(Text, nullable=False, default="pending")  # pending, running, complete, failed
    payload = Column(Text, nullable=False)  # JSON: query or place_id
    result_count = Column(Integer, nullable=True)  # Places found (for search jobs)
    attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="jobs")


class Place(Base):
    """A collected place with raw Google Places API data."""
    __tablename__ = "places"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    place_id = Column(Text, nullable=False)  # Google Place ID
    search_term = Column(Text, nullable=False)  # Term that discovered this place
    search_location = Column(Text, nullable=False)  # City/region this was found under
    raw_json = Column(Text, nullable=False)  # Complete API response as JSON string
    display_name = Column(Text, nullable=True)  # Extracted for quick display
    formatted_address = Column(Text, nullable=True)  # Extracted for quick display
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    data_completeness_score = Column(Integer, nullable=True)  # 0-100 percentage of fields populated
    data_hash = Column(Text, nullable=True)  # Hash for change detection

    # Relationships
    project = relationship("Project", back_populates="places")

    # Unique constraint: (project_id, place_id)
    __table_args__ = (
        UniqueConstraint("project_id", "place_id", name="uq_project_place"),
    )


class Log(Base):
    """Log entry for a project."""
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    level = Column(Text, nullable=False)  # info, warning, error
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="logs")