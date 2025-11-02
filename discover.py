import os
import socket
import scapy.all as scapy
from concurrent.futures import ThreadPoolExecutor
import time

# Define the IP range to scan (192.168.0.1 - 192.168.0.254)
IP_RANGE = "192.168.0.1/24"
TARGET_PORTS = [22, 80, 443, 21, 8080]  # Common ports to check

# Function to ping a device and check if it is alive
def ping_ip(ip):
    response = os.system(f"ping -c 1 -w 1 {ip} > /dev/null 2>&1")
    return ip if response == 0 else None

# Function to scan open ports on a device using socket
def scan_ports(ip):
    open_ports = []
    for port in TARGET_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip, port))
        if result == 0:
            open_ports.append(str(port))
        sock.close()
    return open_ports

# Function to perform a reverse DNS lookup (get hostname)
def get_hostname(ip):
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except socket.herror:
        hostname = None
    return hostname

# Function to discover devices in the IP range
def discover_devices():
    # First, scan the network with ping
    print(f"Scanning IP range: {IP_RANGE}")
    devices = []
    
    # Use ThreadPoolExecutor to parallelize pinging
    with ThreadPoolExecutor(max_workers=50) as executor:
        active_ips = list(filter(None, executor.map(ping_ip, [f"192.168.0.{i}" for i in range(1, 255)])))
    
    # Then scan open ports and get hostnames for each active device
    for ip in active_ips:
        print(f"Scanning {ip}...")
        open_ports = scan_ports(ip)
        hostname = get_hostname(ip)
        
        # Store discovered device info
        devices.append({
            'ip': ip,
            'hostname': hostname if hostname else 'Unknown',
            'open_ports': ",".join(open_ports),
            'status': 'Up',
            'device_group': categorize_device(ip)
        })
        time.sleep(0.1)  # Small delay to avoid overwhelming network
    
    return devices

# Dummy categorization function (this could be more sophisticated)
def categorize_device(ip):
    if ip.startswith("192.168.0.1"):  # Example condition for "router"
        return "Router"
    elif ip.startswith("192.168.0.2"):  # Example condition for "server"
        return "Server"
    elif ip.endswith(".10"):
        return "VoIP"
    return "Unknown"

# Save discovered devices to your database (example using print for now)
def save_devices_to_db(devices):
    for device in devices:
        print(f"Discovered Device: {device['hostname']} ({device['ip']})")
        print(f"Status: {device['status']}, Open Ports: {device['open_ports']}, Group: {device['device_group']}")

if __name__ == "__main__":
    # Discover devices on the network
    discovered_devices = discover_devices()

    # Print or store the results
    save_devices_to_db(discovered_devices)
