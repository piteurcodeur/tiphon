import asyncio
import websockets
import json
import base64
import time

SERVER_IP = "10.4.252.183"  # ← IP du PC Windows 11 sur le réseau WiFi
SERVER_PORT = 8765

async def send_text(ws, text):
    msg = json.dumps({"type": "text", "text": text})
    await ws.send(msg)
    print(f"[→ texte] {text}")

async def send_image(ws, image_path):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    msg = json.dumps({"type": "image", "data": img_b64})
    await ws.send(msg)
    print(f"[→ image] {image_path}")

async def main():
    uri = f"ws://{SERVER_IP}:{SERVER_PORT}"
    print(f"Connexion à {uri}...")
    
    async with websockets.connect(uri) as ws:
        # S'identifier comme Jetson
        await ws.send(json.dumps({"role": "jetson"}))
        print("[+] Connecté au serveur relay")

        # Boucle de test : texte toutes les 3s, image toutes les 10s
        counter = 0
        while True:
            counter += 1
            await send_text(ws, f"Message #{counter} depuis la Jetson — {time.strftime('%H:%M:%S')}")
            
            if counter % 3 == 0:
                # Envoyer une image test (remplacer par votre fichier)
                try:
                    await send_image(ws, "test_image.jpg")
                except FileNotFoundError:
                    print("[!] test_image.jpg introuvable, skip")
            
            await asyncio.sleep(3)

asyncio.run(main())