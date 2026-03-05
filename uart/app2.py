import eventlet
eventlet.monkey_patch()  # DOIT être absolument en premier, avant tout autre import

import socket
import time
import base64
from flask import Flask, render_template
from flask_socketio import SocketIO
import os
from flask import request
import webbrowser
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

ESP32_IP = '192.168.4.1'
PORT = 3333
esp_socket = None

HTML_PAGE = "index2.html"


def listen_to_esp():
    """Tâche de fond eventlet - connexion et lecture de l'ESP32."""
    global esp_socket
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ESP32_IP, PORT))
            esp_socket = s
            print("[ESP32] Connecté !")

            buffer = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    print("[ESP32] Connexion fermée par l'ESP32.")
                    break
                buffer += chunk

                while True:
                    if buffer.startswith(b"TXT:"):
                        newline_pos = buffer.find(b"\n")
                        if newline_pos == -1:
                            break
                        line = buffer[:newline_pos].decode(errors='ignore')
                        msg = line.replace("TXT:", "", 1).strip()
                        print(f"[TXT] {msg}")
                        socketio.emit('new_text', {'data': msg})
                        buffer = buffer[newline_pos + 1:]

                    elif buffer.startswith(b"IMG:"):
                        newline_pos = buffer.find(b"\n")
                        if newline_pos == -1:
                            break
                        header_line = buffer[:newline_pos].decode(errors='ignore')
                        try:
                            size = int(header_line.split(":")[1])
                        except (IndexError, ValueError) as e:
                            print(f"[IMG] Header invalide : {header_line} | {e}")
                            buffer = b""
                            break

                        rest = buffer[newline_pos + 1:]
                        if len(rest) < size:
                            break

                        final_img = rest[:size]
                        buffer = rest[size:]

                        filename = f"image_{int(time.time())}.jpg"
                        with open(filename, "wb") as f:
                            f.write(final_img)
                        print(f"[IMG] Sauvegardée : {filename} ({size} octets)")

                        b64_img = base64.b64encode(final_img).decode('utf-8')
                        socketio.emit('new_image', {'data': b64_img})
                        print(f"[IMG] Émis vers le navigateur (base64 len={len(b64_img)})")

                    else:
                        next_txt = buffer.find(b"TXT:")
                        next_img = buffer.find(b"IMG:")
                        positions = [p for p in [next_txt, next_img] if p > 0]
                        if positions:
                            buffer = buffer[min(positions):]
                        else:
                            break

        except ConnectionRefusedError:
            print(f"[ESP32] Connexion refusée sur {ESP32_IP}:{PORT}, retry dans 2s...")
        except Exception as e:
            print(f"[ESP32] Erreur : {e}")
        finally:
            esp_socket = None
            eventlet.sleep(2)  # sleep compatible eventlet


@socketio.on('send_cmd')
def handle_command(json):
    global esp_socket
    if esp_socket:
        try:
            cmd = json['command'].strip() + "\n"
            esp_socket.send(cmd.encode())
            print(f"[CMD] Envoyé : {cmd.strip()}")
        except Exception as e:
            print(f"[CMD] Erreur envoi : {e}")
    else:
        print("[CMD] Pas de connexion ESP32 active.")


@app.route('/')
def index():
    return render_template(HTML_PAGE)

@app.route('/quit', methods=['POST'])
def quit_app():
    os._exit(0)

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    socketio.start_background_task(listen_to_esp)

    # ouvre le navigateur automatiquement
    threading.Timer(1.5, open_browser).start()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)