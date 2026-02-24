import cv2

# On teste l'index 1 avec le backend CAP_DSHOW
# Si 1 ne marche toujours pas, essaie 2 ou 0
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)

if not cap.isOpened():
    print("Toujours pas... Tentative sur l'index 2...")
    cap = cv2.VideoCapture(2, cv2.CAP_DSHOW)

while True:
    ret, frame = cap.read()
    if not ret:
        print("En attente du flux...")
        continue # On continue de boucler au lieu de crash

    cv2.imshow('Ma Logitech USB', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()