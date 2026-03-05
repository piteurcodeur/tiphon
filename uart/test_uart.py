import socket

# L'IP par défaut de l'AP ESP32 est 192.168.4.1
ESP32_IP = '192.168.4.1'
PORT = 3333

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ESP32_IP, PORT))
    print("Connecté à l'ESP32 ! En attente de données de la Jetson...")
    
    while True:
        data = s.recv(1024)
        if not data:
            break
        print(f"Reçu : {data.decode('utf-8', errors='ignore')}")
except Exception as e:
    print(f"Erreur : {e}")
finally:
    s.close()