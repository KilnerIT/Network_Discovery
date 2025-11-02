from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Network Device API")

# ===== Models =====
class DeviceIn(BaseModel):
    ip: str
    hostname: Optional[str] = ""
    status: str
    device_group: str
    open_ports: str
    site: Optional[str] = "N/A"
    last_seen: Optional[str] = None  # Optional, will be set by server

class Device(DeviceIn):
    id: int  # Assigned by server

class DeviceHistoryEntry(BaseModel):
    timestamp: str
    event: str

# ===== Storage =====
devices: List[Device] = []
device_history: Dict[int, List[DeviceHistoryEntry]] = {}
next_id = 1

# ===== Helper =====
def log_event(device_id: int, event: str):
    entry = DeviceHistoryEntry(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event=event)
    device_history.setdefault(device_id, []).append(entry)

# ===== Endpoints =====
@app.get("/devices/", response_model=List[Device])
def list_devices():
    return devices

@app.post("/devices/upsert/", response_model=Device)
def upsert_device(data: DeviceIn):
    """Upsert a device based on its IP"""
    global next_id

    # Check if device exists
    for d in devices:
        if d.ip == data.ip:
            # Update existing
            d.hostname = data.hostname or d.hostname
            d.status = data.status
            d.device_group = data.device_group
            d.open_ports = data.open_ports
            d.site = data.site
            d.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_event(d.id, "Device updated via discovery")
            log.info(f"Updated device {d.ip}")
            return d

    # Add new device
    device = Device(
        id=next_id,
        ip=data.ip,
        hostname=data.hostname,
        status=data.status,
        device_group=data.device_group,
        open_ports=data.open_ports,
        site=data.site,
        last_seen=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    devices.append(device)
    device_history[next_id] = [DeviceHistoryEntry(timestamp=device.last_seen, event="Device added")]
    log.info(f"Added new device {device.ip} with id {next_id}")
    next_id += 1
    return device

@app.get("/devices/{device_id}/history/", response_model=List[DeviceHistoryEntry])
def get_device_history(device_id: int):
    if device_id not in device_history:
        raise HTTPException(status_code=404, detail="Device history not found")
    return device_history[device_id]
