import socket

ESP32_IP = '192.168.4.1'
PORT = 3333

def start_receiver():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ESP32_IP, PORT))
    print("Connecté à la Jetson via ESP32. En attente de données...")

    buffer = b""
    while True:
        chunk = s.recv(4096)
        if not chunk: break
        buffer += chunk

        # Chercher un marqueur dans le buffer
        if b"TXT:" in buffer and b"\n" in buffer:
            line = buffer.split(b"\n")[0]
            print(f"> MESSAGE : {line.decode().replace('TXT:', '')}")
            buffer = buffer[len(line)+1:]

        elif b"IMG:" in buffer and b"\n" in buffer:
            header = buffer.split(b"\n")[0]
            try:
                size = int(header.decode().split(":")[1])
                print(f"> RÉCEPTION IMAGE : {size} octets...")
                buffer = buffer[len(header)+1:] # On garde le reste du buffer

                # On continue de recevoir jusqu'à avoir toute l'image
                img_data = buffer
                while len(img_data) < size:
                    img_data += s.recv(4096)
                
                # On extrait l'image et on garde le surplus pour la suite
                actual_image = img_data[:size]
                buffer = img_data[size:]

                with open("recu_jetson.jpg", "wb") as f:
                    f.write(actual_image)
                print("--- Image enregistrée sous 'recu_jetson.jpg' ---")
            except Exception as e:
                print(f"Erreur protocole image : {e}")
                buffer = b""

if __name__ == "__main__":
    start_receiver()