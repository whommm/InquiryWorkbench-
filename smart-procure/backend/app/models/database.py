"""
Database models for SmartProcure
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import os
import uuid

# Database configuration - 从环境变量读取
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://smartprocure:smartprocure123@localhost:5432/smartprocure"
)

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100))

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)


class InquirySheet(Base):
    """Inquiry sheet model for storing procurement data"""
    __tablename__ = "inquiry_sheets"

    id = Column(String, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
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

    # 渠道标签 - 记录是谁添加的这个供应商
    created_by = Column(String(36), ForeignKey("users.id"), index=True)

    # Extended fields
    contact_name = Column(String)
    tags = Column(JSON, default=list)

    # Statistics
    quote_count = Column(Integer, default=0)
    last_quote_date = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplierProduct(Base):
    """供应商-产品关联表，记录供应商报价过的产品"""
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)

    # 产品信息（完整保存）
    product_name = Column(String, index=True)
    product_model = Column(String, index=True)
    brand = Column(String, index=True)

    # 报价信息
    last_price = Column(Float)
    quote_count = Column(Integer, default=1)

    # 时间戳
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
