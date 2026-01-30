"""
Database models for SmartProcure
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Database configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'smartprocure.db')}"

# Create engine and session
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class InquirySheet(Base):
    """Inquiry sheet model for storing procurement data"""
    __tablename__ = "inquiry_sheets"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    sheet_data = Column(JSON, nullable=False)
    chat_history = Column(JSON, default=list)

    # Metadata
    item_count = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Supplier(Base):
    """Supplier model for storing supplier information"""
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core fields
    company_name = Column(String, nullable=False, unique=True)
    contact_phone = Column(String, nullable=False)
    owner = Column(String, nullable=False, default="系统自动")

    # Extended fields
    contact_name = Column(String)
    tags = Column(JSON, default=list)

    # Statistics
    quote_count = Column(Integer, default=0)
    last_quote_date = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
