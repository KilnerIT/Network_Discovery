#!/usr/bin/env python3
"""
discover_and_push.py

- Scans a /24 subnet (default 192.168.0.0/24)
- Uses Scapy for ICMP discovery and TCP SYN port scanning
- Resolves reverse DNS hostname
- Categorizes device (simple heuristics)
- Posts discovered devices to the Master API (FastAPI) at /devices/upsert/
"""

import sys
import os
import time
import socket
import logging
from ipaddress import IPv4Network
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import requests
from scapy.all import IP, ICMP, TCP, sr1, conf

# ===== Configuration =====
SITE_NAME = "Home"
SUBNET = "192.168.0.0/24"
TARGET_PORTS = [22, 80, 443, 21, 8080, 161, 5060]
API_ENDPOINT = "http://127.0.0.1:8000/devices/upsert/"
WORKERS = 50
ICMP_TIMEOUT = 1.0
TCP_TIMEOUT = 1.0
VERBOSE = True
# =========================

# Silence scapy verbose output
conf.verb = 0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def log(msg):
    if VERBOSE:
        print(msg)


def is_host_up_icmp(ip: str) -> bool:
    """Ping host with ICMP."""
    try:
        pkt = IP(dst=ip)/ICMP()
        resp = sr1(pkt, timeout=ICMP_TIMEOUT, verbose=0)
        return resp is not None
    except PermissionError:
        logging.error("Root privileges required for ICMP. Run with sudo.")
        raise
    except Exception:
        return False


def is_host_up_tcp(ip: str, ports: List[int]) -> bool:
    """Fallback TCP probe if ICMP blocked."""
    for port in ports:
        try:
            pkt = IP(dst=ip)/TCP(dport=port, flags="S")
            resp = sr1(pkt, timeout=TCP_TIMEOUT, verbose=0)
            if resp and resp.haslayer(TCP) and resp[TCP].flags & 0x12:  # SYN/ACK
                # send RST to close
                rst = IP(dst=ip)/TCP(dport=port, flags="R")
                sr1(rst, timeout=0.5, verbose=0)
                return True
        except Exception:
            continue
    return False


def scan_ports(ip: str, ports: List[int]) -> List[int]:
    """Return list of open ports via SYN scan."""
    open_ports = []
    for port in ports:
        try:
            pkt = IP(dst=ip)/TCP(dport=port, flags="S")
            resp = sr1(pkt, timeout=TCP_TIMEOUT, verbose=0)
            if resp and resp.haslayer(TCP) and resp[TCP].flags & 0x12:
                open_ports.append(port)
                # polite RST
                rst = IP(dst=ip)/TCP(dport=port, flags="R")
                sr1(rst, timeout=0.5, verbose=0)
        except Exception:
            continue
    return open_ports


def get_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, TimeoutError):
        return ""


def categorize_device(ip: str, open_ports: List[int], hostname: str) -> str:
    """Simple device categorization heuristics."""
    h = hostname.lower() if hostname else ""
    if 161 in open_ports:
        return "Switch/Network"
    if 5060 in open_ports or 5061 in open_ports:
        return "VOIP"
    if 22 in open_ports or "server" in h or "web" in h:
        return "Server"
    if any(p in open_ports for p in [80, 443, 8080]):
        return "Web/HTTP"
    return "Unknown"


def discover_single(ip: str):
    """Discover host and return device dict for API."""
    log(f"[+] Probing {ip}")

    up = is_host_up_icmp(ip) or is_host_up_tcp(ip, TARGET_PORTS)
    if not up:
        log(f"[-] {ip} is down")
        return None

    open_ports = scan_ports(ip, TARGET_PORTS)
    hostname = get_hostname(ip)
    device_group = categorize_device(ip, open_ports, hostname)

    device = {
        "ip": ip,
        "hostname": hostname or "",
        "status": "Up",
        "device_group": device_group,
        "open_ports": ",".join(str(p) for p in open_ports),
        "site": SITE_NAME
    }

    log(f"[+] Found {ip} hostname={device['hostname']} ports={device['open_ports']} group={device['device_group']}")
    return device


def post_device(device: dict) -> bool:
    """Push device to API."""
    try:
        resp = requests.post(API_ENDPOINT, json=device, timeout=5)
        if resp.status_code in (200, 201):
            logging.info(f"Pushed {device['ip']} successfully")
            return True
        logging.warning(f"Failed to push {device['ip']} - {resp.status_code}")
        return False
    except Exception as e:
        logging.warning(f"Error pushing {device['ip']}: {e}")
        return False


def scan_subnet_and_push(subnet_cidr: str = SUBNET):
    net = IPv4Network(subnet_cidr)
    ips = [str(ip) for ip in net.hosts()]
    logging.info(f"Scanning {len(ips)} hosts in {subnet_cidr} using {WORKERS} workers")

    discovered = []

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(discover_single, ip): ip for ip in ips}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                result = future.result()
                if result:
                    discovered.append(result)
            except Exception as e:
                logging.error(f"Exception scanning {ip}: {e}")

    logging.info(f"Discovery complete: {len(discovered)} hosts up")
    pushed_count = sum(post_device(dev) for dev in discovered)
    logging.info(f"Pushed {pushed_count}/{len(discovered)} devices to API")


if __name__ == "__main__":
    if sys.platform.startswith("linux") and os.geteuid() != 0:
        logging.warning("Run with sudo/root to allow ICMP/TCP scans")

    try:
        scan_subnet_and_push(SUBNET)
    except KeyboardInterrupt:
        logging.info("User interrupted scan")
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
