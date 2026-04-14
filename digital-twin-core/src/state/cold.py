from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class AssetTelemetryHistory(Base):
    __tablename__ = 'asset_telemetry'
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String, index=True)
    asset_type = Column(String)
    status = Column(String)
    temperature = Column(Float, nullable=True)
    cpu_utilization = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class SystemTelemetryHistory(Base):
    __tablename__ = 'system_telemetry'
    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(String, index=True)
    parent_asset_id = Column(String)
    system_type = Column(String)
    status = Column(String)
    memory_utilization = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

DATABASE_URL = "sqlite:///history.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Initialized SQLite cold state persistence in history.db.")

def record_asset_drift(asset_data: dict):
    try:
        db = SessionLocal()
        record = AssetTelemetryHistory(
            asset_id=asset_data['asset_id'],
            asset_type=asset_data['asset_type'],
            status=asset_data['status'],
            temperature=asset_data.get('temperature'),
            cpu_utilization=asset_data.get('cpu_utilization'),
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record state drift: {e}")
    finally:
        if 'db' in locals():
            db.close()

def record_system_drift(system_data: dict):
    try:
        db = SessionLocal()
        record = SystemTelemetryHistory(
            system_id=system_data['system_id'],
            parent_asset_id=system_data['parent_asset_id'],
            system_type=system_data['system_type'],
            status=system_data['status'],
            memory_utilization=system_data.get('memory_utilization'),
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record system drift: {e}")
    finally:
        if 'db' in locals():
            db.close()

def load_latest_state() -> list:
    """Load the latest known state from history.db on restart"""
    db = SessionLocal()
    try:
        # Get most recent asset records
        assets = db.query(AssetTelemetryHistory).all()
        # Get most recent system records
        systems = db.query(SystemTelemetryHistory).all()
        return assets, systems
    finally:
        db.close()
