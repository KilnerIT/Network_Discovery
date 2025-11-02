Make sure all Requirements have been installed



Open Terminal Window (1) 

1. Create a Python virtual environment

python3 -m venv .venv
source .venv/bin/activate       # Linux/macOS

2. Install Dependcies 
pip install --upgrade pip
pip install fastapi uvicorn scapy requests jinja2

3. In enviroment 1 -
uvicorn main:app --reload

Open Terminal Windows (2)
1. source .venv/bin/activate       # Linux/macOS

sudo python3 discover_and_push.py

Open Terminal Window (3)
1. source .venv/bin/activate

2. python3 -m http.server 8080


