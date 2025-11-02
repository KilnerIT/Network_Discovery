# Network Discovery & Observability PoC

This project is a **proof-of-concept network observability app** inspired by Domotz and LibreNMS.  
It performs automated discovery of devices on a local network, checks their status and open ports, and exposes the results via a FastAPI web interface.

---

## **Features**

- Scans a subnet (default `192.168.0.0/24`) for live devices
- Detects device up/down status
- Detects open TCP ports and highlights concerning ports (`21`, `80`, `8080`)
- Categorizes devices into:
  - Servers
  - Network Switches
  - VOIP
- Click a device in the web UI to view SNMP information
- Centralized FastAPI backend for storing discovered devices
- Responsive HTML/CSS frontend with cards and icons

---

## **Prerequisites**

- Python 3.10+ (recommended)
- Pip (Python package manager)
- Git
- Elevated privileges (root/admin) for raw socket operations
- Optional: Linux for full Scapy functionality, but works on Windows with limitations

---

## **Installation**

### 1. Clone the repository

```bash
git clone https://github.com/KilnerIT/Network_Discovery.git
cd Network_Discovery
