"""Flexibles Datenmodell für Dokumente, Befunde und nachvollziehbare Änderungen.

Befundparameter liegen als Kategorien und Werte vor, nicht als immer neue
Tabellenspalten. Damit können spätere Laborparameter ohne Schemaänderung ergänzt
werden. In Phase 1 werden lediglich Tabellen angelegt, noch keine KI-Werte bestätigt.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Gemeinsame Basisklasse sämtlicher Datenbankmodelle."""


class ConfidenceStatus(str, enum.Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    UNCERTAIN = "UNCERTAIN"
    UNREADABLE = "UNREADABLE"
    CONFLICT = "CONFLICT"
    MISSING = "MISSING"


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(250))
    birth_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentType(Base):
    __tablename__ = "document_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    prompt_text: Mapped[str | None] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    document_type_id: Mapped[int | None] = mapped_column(ForeignKey("document_types.id"))
    original_name: Mapped[str] = mapped_column(String(500))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class FindingCategory(Base):
    __tablename__ = "finding_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    group_name: Mapped[str] = mapped_column(String(150))
    typical_unit: Mapped[str | None] = mapped_column(String(50))


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("finding_categories.id"))
    finding_date: Mapped[date] = mapped_column(Date)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(50))
    source_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    confidence_status: Mapped[ConfidenceStatus] = mapped_column(SqlEnum(ConfidenceStatus))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    diagnosis_name: Mapped[str] = mapped_column(String(300))
    diagnosis_code: Mapped[str | None] = mapped_column(String(50))
    first_diagnosis_date: Mapped[date | None] = mapped_column(Date)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    status: Mapped[str] = mapped_column(String(30), default="UNSICHER")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIResult(Base):
    __tablename__ = "ai_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    raw_ai_response: Mapped[str] = mapped_column(Text)
    kis_summary_compact: Mapped[str | None] = mapped_column(Text)
    kis_summary_detailed: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(150))
    provider: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIWarning(Base):
    __tablename__ = "ai_warnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    warning_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30))
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    user_feedback: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FollowUpItem(Base):
    __tablename__ = "follow_up_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    text: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="OFFEN")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    preference_key: Mapped[str] = mapped_column(String(200), unique=True)
    preference_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(150))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    # Es werden bewusst nur technische Metadaten vorgesehen. Patientendaten oder
    # API-Antworten gehören nicht in Debug- beziehungsweise Audit-Nachrichten.
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

