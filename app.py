# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import sqlite3
import os
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler

DB_FILE = "devices.db"

app = FastAPI(title="Network POC API")

# Allow local frontend (relax for dev; tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Database Setup --------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the devices and history tables if missing."""
    conn = get_db_connection()

    conn.execute('''CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT NOT NULL,
        hostname TEXT,
        status TEXT,
        last_seen TEXT,
        device_group TEXT,
        open_ports TEXT,
        site TEXT
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS device_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER,
        timestamp TEXT,
        status TEXT,
        message TEXT,
        FOREIGN KEY (device_id) REFERENCES devices(id)
    )''')

    conn.commit()
    conn.close()

init_db()

# -------------------- Models --------------------

class DeviceIn(BaseModel):
    ip: str
    hostname: Optional[str] = ""
    status: str
    last_seen: Optional[str] = None
    device_group: Optional[str] = ""
    open_ports: Optional[str] = ""  # comma-separated
    site: Optional[str] = ""        # multi-site support

# -------------------- Endpoints --------------------

@app.post("/devices/", status_code=201)
async def add_device(device: DeviceIn):
    """Simple insert — kept for backward compatibility."""
    last_seen = device.last_seen or datetime.utcnow().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO devices (ip, hostname, status, last_seen, device_group, open_ports, site) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (device.ip, device.hostname, device.status, last_seen, device.device_group, device.open_ports, device.site),
    )
    conn.commit()
    did = cur.lastrowid

    # Log initial history event
    cur.execute("""
        INSERT INTO device_history (device_id, timestamp, status, message)
        VALUES (?, ?, ?, ?)
    """, (did, last_seen, device.status, "Device added manually"))
    conn.commit()
    conn.close()
    return {"id": did, "status": "created"}


@app.post("/devices/upsert/")
async def upsert_device(device: DeviceIn):
    """
    Insert or update device (based on IP + site).
    Tracks history of status changes.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    last_seen = device.last_seen or datetime.utcnow().isoformat()

    # Does device already exist?
    cur.execute("SELECT id, status FROM devices WHERE ip = ? AND site = ?", (device.ip, device.site))
    row = cur.fetchone()

    if row:
        device_id, old_status = row
        new_status = device.status

        # Update existing device record
        cur.execute("""
            UPDATE devices
            SET hostname=?, status=?, last_seen=?, device_group=?, open_ports=?
            WHERE id=?
        """, (device.hostname, new_status, last_seen, device.device_group, device.open_ports, device_id))

        # Log status change if it differs
        if old_status != new_status:
            cur.execute("""
                INSERT INTO device_history (device_id, timestamp, status, message)
                VALUES (?, ?, ?, ?)
            """, (device_id, last_seen, new_status, f"Status changed from {old_status} → {new_status}"))
    else:
        # New device — insert and log discovery
        cur.execute("""
            INSERT INTO devices (ip, hostname, status, last_seen, device_group, open_ports, site)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            device.ip, device.hostname, device.status,
            last_seen, device.device_group, device.open_ports, device.site
        ))

        device_id = cur.lastrowid
        cur.execute("""
            INSERT INTO device_history (device_id, timestamp, status, message)
            VALUES (?, ?, ?, ?)
        """, (device_id, last_seen, device.status, "Device discovered"))

    conn.commit()
    conn.close()
    return {"message": "Device upserted successfully"}


@app.get("/devices/")
async def get_devices(limit: int = 50, site: Optional[str] = None):
    """Fetch latest devices, optionally filtered by site."""
    conn = get_db_connection()
    if site:
        rows = conn.execute(
            "SELECT * FROM devices WHERE site = ? ORDER BY last_seen DESC LIMIT ?",
            (site, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM devices ORDER BY last_seen DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/device/{device_id}")
async def get_device(device_id: int):
    """Fetch a single device by ID."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return dict(row)


@app.get("/history/{device_id}")
async def get_history(device_id: int):
    """Return history entries for a device."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, status, message
        FROM device_history
        WHERE device_id = ?
        ORDER BY timestamp DESC
    """, (device_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -------------------- Scheduler (optional) --------------------

def run_discovery_job():
    """
    Periodically run discover_and_push.py to update device statuses.
    Adjust the path to your local script if needed.
    """
    try:
        print("[Scheduler] Running network discovery job...")
        subprocess.Popen(["python3", "discover_and_push.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Scheduler] Error launching discovery: {e}")

@app.on_event("startup")
def start_scheduler():
    """Start a background scheduler to run discovery every 10 minutes."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_discovery_job, "interval", minutes=10)
    scheduler.start()
    print("[INFO] Discovery scheduler started (every 10 minutes)")
