# app.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import sqlite3
import os

DB_FILE = "devices.db"

app = FastAPI(title="Network POC API")

# Allow local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for demo only; lock this down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_FILE):
        conn = get_db_connection()
        conn.execute('''CREATE TABLE devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            hostname TEXT,
            status TEXT,
            last_seen TEXT,
            device_group TEXT,
            open_ports TEXT,
            site TEXT
        )''')
        conn.commit()
        conn.close()

init_db()

class DeviceIn(BaseModel):
    ip: str
    hostname: Optional[str] = ""
    status: str
    last_seen: Optional[str] = None
    device_group: Optional[str] = ""
    open_ports: Optional[str] = ""  # comma-separated
    site: Optional[str] = ""        # new field for multi-site

@app.post("/devices/", status_code=201)
async def add_device(device: DeviceIn):
    last_seen = device.last_seen or datetime.utcnow().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO devices (ip, hostname, status, last_seen, device_group, open_ports, site) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (device.ip, device.hostname, device.status, last_seen, device.device_group, device.open_ports, device.site),
    )
    conn.commit()
    did = cur.lastrowid
    conn.close()
    return {"id": did, "status": "created"}

@app.get("/devices/")
async def get_devices(limit: int = 50, site: Optional[str] = None):
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
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return dict(row)
