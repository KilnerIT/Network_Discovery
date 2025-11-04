from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

# ===== Logging =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ===== Database Setup =====
DATABASE_URL = "sqlite:///./devices.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ===== Models =====
class DeviceModel(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, unique=True, index=True, nullable=False)
    hostname = Column(String, default="")
    status = Column(String, nullable=False)
    device_group = Column(String, nullable=False)
    open_ports = Column(String, nullable=False)
    site = Column(String, default="N/A")
    last_seen = Column(DateTime, default=datetime.utcnow)
    history = relationship("DeviceHistoryModel", back_populates="device")

class DeviceHistoryModel(Base):
    __tablename__ = "device_history"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    event = Column(Text)
    device = relationship("DeviceModel", back_populates="history")

Base.metadata.create_all(bind=engine)

# ===== Pydantic Schemas =====
class DeviceIn(BaseModel):
    ip: str
    hostname: Optional[str] = ""
    status: str
    device_group: str
    open_ports: str
    site: Optional[str] = "N/A"

class Device(DeviceIn):
    id: int
    last_seen: datetime

class DeviceHistoryEntry(BaseModel):
    timestamp: datetime
    event: str

# ===== FastAPI App =====
app = FastAPI(title="Network Device API")

# ===== Dependency =====
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== Helpers =====
def log_event(db: Session, device_id: int, event: str):
    entry = DeviceHistoryModel(device_id=device_id, event=event)
    db.add(entry)
    db.commit()

# ===== Endpoints =====

# CORRECTED: Root endpoint to serve the HTML file
@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serves the index.html file from the frontend/ directory."""
    # Define the path to the index.html file
    html_file_path = Path("frontend") / "index.html"
    try:
        with open(html_file_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<html><body><h1>Error</h1><p>index.html file not found in the 'frontend' directory.</p></body></html>", status_code=404)

# CORRECTED: Handles the optional 'site' query parameter
@app.get("/devices/", response_model=List[Device])
def list_devices(site: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(DeviceModel)
    if site:
        query = query.filter(DeviceModel.site == site)
    return query.all()

@app.post("/devices/upsert/", response_model=Device)
def upsert_device(data: DeviceIn, db: Session = Depends(get_db)):
    device = db.query(DeviceModel).filter(DeviceModel.ip == data.ip).first()
    now = datetime.utcnow()

    if device:
        # Update existing
        device.hostname = data.hostname or device.hostname
        device.status = data.status
        device.device_group = data.device_group
        device.open_ports = data.open_ports
        device.site = data.site
        device.last_seen = now
        db.commit()
        log_event(db, device.id, "Device updated via discovery")
        log.info(f"Updated device {device.ip}")
        return device

    # Create new device
    device = DeviceModel(
        ip=data.ip,
        hostname=data.hostname,
        status=data.status,
        device_group=data.device_group,
        open_ports=data.open_ports,
        site=data.site,
        last_seen=now
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    log_event(db, device.id, "Device added")
    log.info(f"Added new device {device.ip} with id {device.id}")
    return device

# CORRECTED: Returns [] instead of raising 404 if no history is found
@app.get("/devices/{device_id}/history/", response_model=List[DeviceHistoryEntry])
def get_device_history(device_id: int, db: Session = Depends(get_db)):
    entries = db.query(DeviceHistoryModel).filter(DeviceHistoryModel.device_id == device_id).all()
    # If no history entries, return an empty list for a clean frontend experience
    return entries

# Seed endpoint (as previously provided)
@app.get("/seed/")
def seed_database(db: Session = Depends(get_db)):
    """
    Adds a few sample devices and history entries for testing.
    """
    sample_data = [
        {
            "ip": "192.168.1.1",
            "hostname": "GatewayRouter",
            "status": "Up",
            "device_group": "Switch/Network",
            "open_ports": "80,443,22",
            "site": "Home"
        },
        {
            "ip": "192.168.1.10",
            "hostname": "Web-Server",
            "status": "Up",
            "device_group": "Server",
            "open_ports": "8080,22",
            "site": "Data Center"
        },
        {
            "ip": "192.168.1.50",
            "hostname": "User-PC",
            "status": "Down",
            "device_group": "Unknown",
            "open_ports": "",
            "site": "Home"
        }
    ]

    count = 0
    for data in sample_data:
        device = db.query(DeviceModel).filter(DeviceModel.ip == data["ip"]).first()
        if not device:
            new_device = DeviceModel(**data)
            db.add(new_device)
            db.commit()
            db.refresh(new_device)
            log_event(db, new_device.id, "Device seeded as sample data") 
            log.info(f"Seeded device {new_device.ip}")
            count += 1
    
    return {"message": f"Database seeded with {count} new devices."}
