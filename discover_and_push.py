#!/usr/bin/env python3
"""
discover_and_push.py

- Scans a /24 subnet (default 192.168.0.0/24)
- Uses Scapy for ICMP discovery and TCP SYN port scanning
- Resolves reverse DNS hostname
- Categorizes device (simple heuristics)
- Posts discovered devices to the Master API (FastAPI) at /devices/
"""

import sys
import os
import time
import socket
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network
from typing import List
import logging

# Scapy
from scapy.all import IP, ICMP, sr1, TCP, sr, conf
# HTTP client
import requests

# ===== Configuration =====
SITE_NAME = "Home" # change per site
SUBNET = "192.168.0.0/24"          # target subnet
TARGET_PORTS = [22, 80, 443, 21, 8080, 161, 5060]   # ports to check
API_ENDPOINT = "http://127.0.0.1:8000/devices/"     # FastAPI endpoint
WORKERS = 80                       # concurrency: adjust to your env
ICMP_TIMEOUT = 1.0
TCP_TIMEOUT = 1.0
VERBOSE = True                     # set False to reduce printouts
# =========================

# Configure scapy
conf.verb = 0  # silence scapy output

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def log(msg):
    if VERBOSE:
        print(msg)


def is_host_up_icmp(ip: str, timeout: float = ICMP_TIMEOUT) -> bool:
    """Send an ICMP echo request and return True if we get a reply."""
    try:
        pkt = IP(dst=ip)/ICMP()
        resp = sr1(pkt, timeout=timeout, verbose=0)
        return resp is not None
    except PermissionError:
        logging.error("Permission denied: need root privileges to send raw packets (scapy).")
        raise
    except Exception as e:
        logging.debug(f"ICMP error for {ip}: {e}")
        return False


def is_host_up_tcp(ip: str, ports: List[int], timeout: float = TCP_TIMEOUT) -> bool:
    """Try connecting with TCP SYN to a few common ports — fallback if ICMP is blocked."""
    try:
        for port in ports:
            pkt = IP(dst=ip)/TCP(dport=port, flags="S")
            resp = sr1(pkt, timeout=timeout, verbose=0)
            if resp is not None and resp.haslayer(TCP):
                if resp.getlayer(TCP).flags & 0x12:  # SYN/ACK
                    # send RST to close politely
                    rst = IP(dst=ip)/TCP(dport=port, flags="R")
                    sr1(rst, timeout=0.5, verbose=0)
                    return True
        return False
    except Exception as e:
        logging.debug(f"TCP probe error for {ip}: {e}")
        return False


def scan_ports_syn(ip: str, ports: List[int], timeout: float = TCP_TIMEOUT) -> List[int]:
    """Perform a SYN scan on the provided ports and return a list of open ports."""
    open_ports = []
    for port in ports:
        try:
            pkt = IP(dst=ip)/TCP(dport=port, flags="S")
            resp = sr1(pkt, timeout=timeout, verbose=0)
            if resp is not None and resp.haslayer(TCP):
                flags = resp.getlayer(TCP).flags
                # SYN/ACK = 0x12
                if flags & 0x12:
                    open_ports.append(port)
                    # send RST to tear down
                    rst = IP(dst=ip)/TCP(dport=port, flags="R")
                    sr1(rst, timeout=0.5, verbose=0)
        except Exception as e:
            logging.debug(f"Error scanning {ip}:{port} -> {e}")
    return open_ports


def get_hostname(ip: str) -> str:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, TimeoutError):
        name = ""
    return name


def categorize_device(ip: str, open_ports: List[int], hostname: str) -> str:
    """Simple heuristics to categorize device types."""
    h = hostname.lower() if hostname else ""
    if any(p in open_ports for p in [161]):  # SNMP often on switches/routers
        return "Switch/Network"
    if any(p in open_ports for p in [5060, 5061]):  # SIP
        return "VOIP"
    if 22 in open_ports or "server" in h or "web" in h:
        return "Server"
    if 80 in open_ports or 8080 in open_ports or 443 in open_ports:
        return "Web/HTTP"
    # fallback
    return "Unknown"


def discover_single(ip: str):
    """Discover one host: check up/down, ports, hostname, category and return dict or None."""
    # Skip network and broadcast addresses if passed
    log(f"[+] Probing {ip}")

    # Prefer ICMP discovery, fallback to quick TCP probe on common ports if ICMP blocked
    up = is_host_up_icmp(ip)
    if not up:
        # quick TCP probe to common ports (22,80,443 etc.)
        up = is_host_up_tcp(ip, ports=[22, 80, 443, 161, 5060, 21])
    if not up:
        log(f"[-] {ip} seems down")
        return None

    # Host is up — scan for ports and get hostname
    open_ports = scan_ports_syn(ip, TARGET_PORTS)
    hostname = get_hostname(ip)
    device_group = categorize_device(ip, open_ports, hostname)

    device = {
        "ip": ip,
        "site": SITE_NAME,
        "hostname": hostname or "",
        "status": "Up",
        "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_group": device_group,
        "open_ports": ",".join(str(p) for p in open_ports)
    }
    log(f"[+] Found: {device['ip']} {device['hostname']} ports: {device['open_ports']} group: {device['device_group']}")
    return device


def post_device(device: dict):
    """POST the discovered device to the API endpoint. Returns True on success."""
    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.post(API_ENDPOINT, headers=headers, json=device, timeout=5)
        if resp.status_code in (200, 201):
            logging.info(f"Pushed {device['ip']} -> {resp.status_code}")
            return True
        else:
            logging.warning(f"Failed to push {device['ip']}: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logging.warning(f"Error posting {device['ip']}: {e}")
        return False


def scan_subnet_and_push(subnet_cidr: str = SUBNET):
    net = IPv4Network(subnet_cidr)
    ips = [str(ip) for ip in net.hosts()]  # excludes network & broadcast
    logging.info(f"Scanning {len(ips)} hosts in {subnet_cidr} with {WORKERS} workers")

    discovered = []

    with ThreadPoolExecutor(max_workers=WORKERS) as exec:
        future_to_ip = {exec.submit(discover_single, ip): ip for ip in ips}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                result = future.result()
                if result:
                    discovered.append(result)
            except Exception as e:
                logging.error(f"Exception scanning {ip}: {e}")

    logging.info(f"Discovery complete. Found {len(discovered)} hosts up.")
    # Post them to the API
    pushed = 0
    for dev in discovered:
        ok = post_device(dev)
        if ok:
            pushed += 1

    logging.info(f"Pushed {pushed}/{len(discovered)} discovered devices to {API_ENDPOINT}")


if __name__ == "__main__":
    if not hasattr(sys, "argv"):
        pass

    # small guard: scapy needs root on Linux
    if sys.platform.startswith("linux") and not (os.geteuid() == 0):
        logging.warning("This script should be run with root privileges for packet sending/receiving (sudo).")

    try:
        scan_subnet_and_push(SUBNET)
    except KeyboardInterrupt:
        logging.info("User interrupted")
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
