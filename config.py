from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque, Counter

import threading
import os

os.environ["ULTRALYTICS_AUTO_INSTALL"] = "False"

# === CONFIG ===
MODEL_A_PATH = "dataset-A.pt"
MODEL_B_PATH = "dataset-B.pt"
MODEL_C_PATH = "dataset-C.pt"

ENGINE_A_PATH = "engineA.engine"
ENGINE_B_PATH = "engineB.engine"
ENGINE_C_PATH = "engineC.engine"

CONF_THRESHOLD_A = 0.30
CONF_THRESHOLD_B = 0.30
CONF_THRESHOLD_C = 0.35

CLASSIFY_INTERVAL = 5
MAX_CROP_SIDE = 640
CLASS_VOTE_WINDOW = 5
VOTE_MIN_CONFIRM = 3
MAX_THREAD_WORKERS = 2
PROC_MAX_WIDTH = 640
JPEG_QUALITY = 75
REAL_BOAT_HEIGHT = 3.0
TRACK_BUFFER = 30
MAX_TRACK_AGE = 30

# === OPTIONS D'AFFICHAGE (Ce qui est dessiné SUR la vidéo) ===
overlay_options = {
    "ID": False, 
    "Classe": True, 
    "Distance": False, 
    "Vitesse": False, 
    "Cap": False, 
    "Conf": False
}

# === CLASSES / COLORS ===
CLASS_NAMES = [
    "Autre", "Bateau", "Commerce", "Loisir", "Militaire",
    "Fregate", "Patrouilleur", "Porte-avion", "Ravitailleur",
    "Sous-marin", "Porte-conteneur", "Bateau de peche",
    "Petrolier", "Navire de croisiere", "Ferry",
    "Voilier", "Bateau a moteur", "Petit bateau"
]

# Note: OpenCV utilise BGR
class_colors = {
    "Autre": (180, 180, 180), "Bateau": (0, 200, 200), "Commerce": (0, 120, 255),
    "Loisir": (255, 140, 0), "Militaire": (0, 0, 255), "Fregate": (0, 0, 200),
    "Patrouilleur": (50, 50, 200), "Porte-avion": (100, 0, 150), "Ravitailleur": (0, 150, 150),
    "Sous-marin": (150, 0, 150), "Porte-conteneur": (0, 80, 200), "Bateau de peche": (0, 180, 80),
    "Petrolier": (30, 90, 150), "Navire de croisiere": (20, 140, 200), "Ferry": (80, 120, 255),
    "Voilier": (220, 20, 60), "Bateau a moteur": (255, 165, 0), "Petit bateau": (144, 238, 144)
}

boat_heights = {name: h for name, h in zip(CLASS_NAMES, [
    3.0, REAL_BOAT_HEIGHT, 25.0, 3.0, 25.0, 25.0, 20.0, 60.0, 30.0, 8.0,
    30.0, 6.0, 35.0, 40.0, 15.0, 10.0, 4.0, 2.0
])}

ANALOGY_MAP = {i: v for i, v in enumerate([
    [], [], [1], [1], [1], [4,1], [4,1], [4,1], [4,1], [4,1],
    [2,1], [2,1], [2,1], [2,1], [2,1], [3,1], [3,1], [3,1]
])}


modelA = None; modelB = None; modelC = None

executor = ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS)
pending_futures = {}
track_state = {}
modelA_names = ['Autre', 'Bateau']
modelB_names = ['Commerce', 'Militaire', 'Loisir']
modelC_names = ['Autre', 'Fregate', 'Patrouilleur', 'Porte-avion', 'Ravitailleur', 'Sous-marin', 'Porte-conteneur', 'Bateau de peche', 'Petrolier', 'Navire de croisiere', 'Ferry', 'Voilier', 'Bateau a moteur', 'Petit bateau']

# Global State
target_id = None
history = defaultdict(lambda: deque(maxlen=TRACK_BUFFER))
info = {}
dist_f = {}
ages = {}
active = set()
box_locations = {} # Stockage des coordonnées normalisées pour le clic
cap = None
current_frame = None
frame_lock = threading.Lock()
running = False

# Models
use_cuda = False
try:
    import torch
    use_cuda = torch.cuda.is_available()
except Exception: pass
print(f"[INFO] CUDA: {use_cuda}")