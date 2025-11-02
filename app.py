from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="Network Discovery POC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Models
class Device(BaseModel):
    id: int
    ip: str
    hostname: Optional[str] = "Unknown"
    status: str
    device_group: str
    open_ports: str
    site: Optional[str] = "N/A"
    last_seen: str

class DeviceCreate(BaseModel):
    ip: str
    hostname: Optional[str] = "Unknown"
    status: str
    device_group: str
    open_ports: str
    site: Optional[str] = "N/A"

class DeviceHistoryEntry(BaseModel):
    timestamp: str
    event: str

# In-memory storage
devices: List[Device] = []
device_history: dict[int, List[DeviceHistoryEntry]] = {}
next_id = 1

# Helpers
def add_device(data: dict):
    global next_id
    device = Device(id=next_id, last_seen=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **data)
    devices.append(device)
    device_history[next_id] = [DeviceHistoryEntry(timestamp=device.last_seen, event="Device added")]
    next_id += 1
    return device

def log_event(device_id: int, event: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = DeviceHistoryEntry(timestamp=now, event=event)
    device_history.setdefault(device_id, []).append(entry)

# Endpoints
@app.get("/devices/", response_model=List[Device])
def get_devices(site: Optional[str] = None):
    if site:
        return [d for d in devices if d.site == site]
    return devices

@app.post("/devices/", response_model=Device)
def create_device(data: DeviceCreate):
    return add_device(data.dict())

@app.get("/device/{device_id}", response_model=Device)
def get_device(device_id: int):
    for d in devices:
        if d.id == device_id:
            return d
    raise HTTPException(status_code=404, detail="Device not found")

@app.get("/device/{device_id}/history", response_model=List[DeviceHistoryEntry])
def get_device_history(device_id: int):
    if device_id not in device_history:
        raise HTTPException(status_code=404, detail="Device history not found")
    return device_history[device_id]

# Sample seeding
@app.get("/seed/")
def seed_sample():
    samples = [
        {"ip": "192.168.1.10", "hostname": "webserver-1", "status": "Up", "device_group": "Server", "open_ports": "22,80,443", "site": "Manchester"},
        {"ip": "192.168.1.20", "hostname": "switch-1", "status": "Up", "device_group": "Switch", "open_ports": "161", "site": "Manchester"},
        {"ip": "192.168.2.30", "hostname": "ip-phone-1", "status": "Up", "device_group": "VOIP", "open_ports": "5060,80", "site": "London"},
        {"ip": "192.168.3.40", "hostname": "legacy-ftp", "status": "Down", "device_group": "Server", "open_ports": "21", "site": "Birmingham"},
    ]
    for s in samples:
        add_device(s)
    return {"message": "Sample devices added."}
