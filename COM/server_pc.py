import yaml
from flask import Flask, request, jsonify
import threading

# Lire la config
with open("COM/config.yaml", "r") as f:
    config = yaml.safe_load(f)

SERVER_PORT = config["server_port"]
CERT_FILE = config["cert_file"]
KEY_FILE = config["key_file"]

app = Flask(__name__)
messages_from_clients = []
messages_to_clients = []

@app.route('/send', methods=['POST'])
def receive_message():
    data = request.get_json()
    messages_from_clients.append(data['message'])
    print(f"[Client] {data['message']}")
    return jsonify({"status": "ok"}), 200

@app.route('/receive', methods=['GET'])
def send_message():
    if messages_to_clients:
        return jsonify({"message": messages_to_clients.pop(0)})
    else:
        return jsonify({"message": ""})

def console_input_loop():
    while True:
        msg = input()
        messages_to_clients.append(msg)

if __name__ == "__main__":
    threading.Thread(target=console_input_loop, daemon=True).start()
    # Écoute sur toutes les interfaces avec HTTPS
    app.run(host="0.0.0.0", port=SERVER_PORT, ssl_context=(CERT_FILE, KEY_FILE))