"""
Database models for SmartProcure
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON, ForeignKey, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import uuid

# Database configuration - 强制要求环境变量
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 环境变量未设置，请在 .env 文件中配置")

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
    role = Column(String(20), nullable=False, default="user", server_default="user", index=True)

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


class Notification(Base):
    """Notification model for user messages"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    type = Column(String(20), nullable=False, default="info", server_default="info")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


def _ensure_legacy_columns():
    """
    Ensure newly added columns exist on legacy databases.
    Keep this minimal and idempotent.
    """
    try:
        with engine.begin() as conn:
            dialect = conn.dialect.name
            if dialect == "postgresql":
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'")
                )
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")
                )
                return

            if dialect == "sqlite":
                rows = conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
                columns = {r[1] for r in rows}
                if "role" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                    )
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")
                return

            # Generic fallback for other SQL dialects
            try:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
                )
            except Exception:
                pass
            try:
                conn.execute(text("CREATE INDEX ix_users_role ON users (role)"))
            except Exception:
                pass
    except Exception:
        # Never block startup on best-effort compatibility patching.
        pass


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    _ensure_legacy_columns()


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get database session for background tasks"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
