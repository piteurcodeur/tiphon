import yaml
import requests
import threading
import time
import urllib3

# Ignorer les avertissements liés au certificat auto-signé
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Charger la config
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SERVER_IP = config["server_ip"]        # ex: 10.4.252.55
SERVER_PORT = config["server_port"]    # ex: 5000
POLL_INTERVAL = config.get("poll_interval", 1)

URL_SEND = f"https://{SERVER_IP}:{SERVER_PORT}/send"
URL_RECEIVE = f"https://{SERVER_IP}:{SERVER_PORT}/receive"

# --- Fonction d'envoi de messages ---
def send_loop():
    while True:
        msg = input()  # Tape ton message dans la console
        if msg.strip() == "":
            continue
        try:
            requests.post(URL_SEND, json={"message": msg}, verify=False)
        except Exception as e:
            print("Erreur en envoyant :", e)

# --- Fonction de réception de messages ---
def receive_loop():
    while True:
        try:
            resp = requests.get(URL_RECEIVE, verify=False)
            message = resp.json().get("message")
            if message:
                print(f"[PC] {message}")
        except Exception as e:
            print("Erreur en recevant :", e)
        time.sleep(POLL_INTERVAL)

# --- Programme principal ---
if __name__ == "__main__":
    # Démarrer l'envoi et la réception en parallèle
    threading.Thread(target=send_loop, daemon=True).start()
    threading.Thread(target=receive_loop, daemon=True).start()

    # Garder le programme actif
    while True:
        time.sleep(1)