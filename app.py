import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, Response, send_from_directory
from flask_socketio import SocketIO, emit
import cv2
from ultralytics import YOLO
import yt_dlp
import numpy as np
import math
from collections import defaultdict, deque, Counter

import threading
import time
import os

from config import *


app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")



def compute_ancestors_map(m):
    anc = {k: set() for k in m}
    for k in m:
        stack = list(m[k])
        while stack:
            p = stack.pop()
            if p not in anc[k]:
                anc[k].add(p)
                stack.extend(m.get(p, []))
    return anc

ANCESTORS = compute_ancestors_map(ANALOGY_MAP)

# === UTIL ===
def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    area_a = max(1, a[2]-a[0]) * max(1, a[3]-a[1])
    area_b = max(1, b[2]-b[0]) * max(1, b[3]-b[1])
    return inter / (area_a + area_b - inter) if (area_a + area_b - inter) > 0 else 0

def filter_detections_by_analogy(dets, thresh=0.5):
    if not dets: return dets
    items = [{"box": d[:4], "cid": d[5], "keep": True, "orig": d} for d in dets]
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            if not items[i]["keep"] or not items[j]["keep"]: continue
            if iou(items[i]["box"], items[j]["box"]) < thresh: continue
            ci, cj = items[i]["cid"], items[j]["cid"]
            if ci in ANCESTORS.get(cj, set()): items[i]["keep"] = False
            elif cj in ANCESTORS.get(ci, set()): items[j]["keep"] = False
    return [it["orig"] for it in items if it["keep"]]



def try_load_model(pt_path, engine_path=None, name="model"):
    if engine_path and os.path.exists(engine_path):
        try: return YOLO(engine_path)
        except: pass
    try: return YOLO(pt_path)
    except: return None



def load_models_once():
    global modelA, modelB, modelC
    if modelA is None: modelA = try_load_model(MODEL_A_PATH, ENGINE_A_PATH, "ModelA")
    if modelB is None: modelB = try_load_model(MODEL_B_PATH, ENGINE_B_PATH, "ModelB")
    if modelC is None: modelC = try_load_model(MODEL_C_PATH, ENGINE_C_PATH, "ModelC")

def classify_crop(model, crop_img, model_names, conf_thr):
    if model is None: return None
    try:
        h, w = crop_img.shape[:2]
        crop_small = crop_img
        scale = 1.0
        if max(h,w) > MAX_CROP_SIDE:
            scale = MAX_CROP_SIDE / max(h,w)
            crop_small = cv2.resize(crop_img, (0,0), fx=scale, fy=scale)
        kwargs = {"conf": conf_thr, "verbose": False}
        if use_cuda: kwargs["device"] = 0
        res = model(crop_small, **kwargs)[0]
        if not res.boxes: return None
        confs = res.boxes.conf.cpu().numpy()
        idx = int(np.argmax(confs))
        if confs[idx] < conf_thr: return None
        cls = int(res.boxes.cls.cpu().numpy()[idx])
        name = model_names[cls] if cls < len(model_names) else str(cls)
        bbox = res.boxes.xyxy.cpu().numpy()[idx]
        if scale != 1.0: bbox = bbox / scale
        return {"name": name, "conf": float(confs[idx]), "box": bbox}
    except Exception: return None


def submit_classification(tid, crop_img, crop_origin):
    def job():
        load_models_once()
        resB = classify_crop(modelB, crop_img, modelB_names, CONF_THRESHOLD_B)
        resC = classify_crop(modelC, crop_img, modelC_names, CONF_THRESHOLD_C) if resB else None
        return {"tid": tid, "resB": resB, "resC": resC}
    return executor.submit(job)

def get_video_source(url):
    if url.startswith("http"):
        try:
            with yt_dlp.YoutubeDL({"format": "bestvideo[ext=mp4]/best", "quiet": True}) as ydl:
                return ydl.extract_info(url, download=False).get("url")
        except: pass
    return url

def scale_for_processing(frame, max_w=PROC_MAX_WIDTH):
    h, w = frame.shape[:2]
    if w <= max_w: return frame, 1.0
    scale = max_w / w
    return cv2.resize(frame, (int(w*scale), int(h*scale))), scale

def bgr_to_hex(bgr):
    # Convertit un tuple (B, G, R) en string hex '#RRGGBB'
    return "#{:02x}{:02x}{:02x}".format(bgr[2], bgr[1], bgr[0])

def process_frame_worker():
    global current_frame, target_id, running
    load_models_once()
    prev_time = time.time()

    while running:
        if not cap or not cap.isOpened():
            time.sleep(0.1); continue
        
        ret, frame = cap.read()
        if not ret: time.sleep(0.05); continue

        # Mesure FPS
        now = time.time()
        dt = now - prev_time
        prev_time = now
        fps = 1.0 / dt if dt > 0 else 0

        proc_frame, scale = scale_for_processing(frame)
        fh_orig, fw_orig = frame.shape[:2]
        
        # Async Classification
        done = []
        for tid, fut in list(pending_futures.items()):
            if fut.done():
                try: done.append(fut.result())
                except: pass
                del pending_futures[tid]
        
        for res in done:
            tid = res['tid']
            st = track_state.get(tid, {'votes': deque(maxlen=CLASS_VOTE_WINDOW)})
            chosen = res['resC'] if res['resC'] else res['resB']
            if chosen:
                st['votes'].append(chosen['name'])
                most, num = Counter(st['votes']).most_common(1)[0]
                if num >= VOTE_MIN_CONFIRM:
                    st['confirmed_name'] = most
                    st['confirmed_conf'] = chosen['conf']
            track_state[tid] = st

        # Tracking
        try:
            res_all = modelA.track(proc_frame, persist=True, conf=CONF_THRESHOLD_A, verbose=False)[0]
        except: time.sleep(0.1); continue

        active.clear()
        
        if res_all and getattr(res_all.boxes, "id", None) is not None:
            boxes = res_all.boxes.xyxy.cpu().numpy()
            cls = res_all.boxes.cls.int().cpu().numpy()
            ids = res_all.boxes.id.int().cpu().numpy()
            confs = res_all.boxes.conf.cpu().numpy()
            
            raw = []
            for b, c, cf, tid in zip(boxes, cls, confs, ids):
                if scale != 1.0: b = b / scale
                nameA = modelA_names[c] if c < len(modelA_names) else "Inconnu"
                raw.append([b[0], b[1], b[2], b[3], nameA, float(cf), c, int(tid)])
            
            filtered = filter_detections_by_analogy(raw)
            frame_idx = int(time.time()*30)

            for d in filtered:
                x1, y1, x2, y2 = map(int, d[:4])
                tid = int(d[7])
                nameA = d[4]
                conf_val = d[5]
                
                active.add(tid)
                ages[tid] = 0

                # Mise à jour des coordonnées pour le clic (normalisé 0-1)
                box_locations[tid] = (x1/fw_orig, y1/fh_orig, x2/fw_orig, y2/fh_orig)
                
                # Logic Classif
                st = track_state.get(tid, {'stage':'A', 'name':nameA, 'votes': deque(maxlen=CLASS_VOTE_WINDOW)})
                final_name = st.get('confirmed_name', st.get('name', nameA))
                final_conf = st.get('confirmed_conf', conf_val)

                if nameA in ["Bateau", "bateau"]:
                    if (frame_idx - st.get('last_cl', -999) > CLASSIFY_INTERVAL) and tid not in pending_futures:
                        pad = 10
                        cx1, cy1 = max(0, x1-pad), max(0, y1-pad)
                        cx2, cy2 = min(fw_orig, x2+pad), min(fh_orig, y2+pad)
                        pending_futures[tid] = submit_classification(tid, frame[cy1:cy2, cx1:cx2].copy(), (cx1,cy1))
                        st['last_cl'] = frame_idx
                
                track_state[tid] = st

                # Physics
                h_box = max(1, y2-y1)
                raw_dist = (boat_heights.get(final_name, REAL_BOAT_HEIGHT) * 800) / h_box
                dist = 0.7 * dist_f.get(tid, raw_dist) + 0.3 * raw_dist
                dist_f[tid] = dist
                
                cx, cy = (x1+x2)//2, (y1+y2)//2
                history[tid].append((cx, cy, dist))
                
                speed = 0.0; heading = 0.0
                if len(history[tid]) > 1:
                    dx = history[tid][-1][0] - history[tid][-2][0]
                    dy = history[tid][-1][1] - history[tid][-2][1]
                    if math.hypot(dx, dy) > 1:
                        speed = (math.hypot(dx,dy) * dist / 800) * 30 * 1.94
                        heading = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
                
                azimuth_factor = (cx - (fw_orig/2)) / (fw_orig/2)
                
                # Récupération couleur + conversion Hex pour le HTML
                col_bgr = class_colors.get(final_name, (0,200,200))
                col_hex = bgr_to_hex(col_bgr)
                
                info[tid] = {
                    'name': final_name, 
                    'distance': dist, 
                    'speed': speed, 
                    'heading': heading, 
                    'azimuth_factor': azimuth_factor,
                    'color_hex': col_hex # Pour le radar
                }

                # === DESSIN SUR IMAGE ===
                # Épaissir la boîte UNIQUEMENT si c'est la cible
                # 6 = Gras (Sélectionné)
                # 2 = Normal/Fin (Non sélectionné)
                thick = 6 if tid == target_id else 2
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), col_bgr, thick)

                # Construction du texte
                txt = ""
                if overlay_options["ID"]: txt += f"ID:{tid} "
                if overlay_options["Classe"]: txt += f"{final_name} "
                if overlay_options["Distance"]: txt += f"{dist:.0f}m "
                if overlay_options["Vitesse"]: txt += f"{speed:.1f}kt "
                if overlay_options["Cap"]: txt += f"{heading:.0f}° "
                if overlay_options["Conf"]: txt += f"{final_conf:.2f}"
                
                if txt.strip():
                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame, (x1, y1-th-4), (x1+tw+4, y1), col_bgr, -1)
                    cv2.putText(frame, txt.strip(), (x1+2, y1-3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        # Cleanup
        for tid in list(ages):
            if tid not in active:
                ages[tid] += 1
                if ages[tid] > MAX_TRACK_AGE:
                    for db in [history, info, dist_f, ages, track_state, box_locations]: db.pop(tid, None)
            else: ages[tid] = 0

        try:
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            with frame_lock: current_frame = buffer.tobytes()
        except: pass

        socketio.emit('update', {
            "tracks": {str(k): v for k, v in info.items() if k in active},
            "target_id": target_id,
            "fps": round(fps, 1)
        })
        time.sleep(0.01)

def generate_frames():
    while True:
        with frame_lock:
            if current_frame: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
        time.sleep(0.04)


#############################################################################################################
#                                   ROUTES & EVENEMENTS WEBSOCKETS                                          #
#############################################################################################################
  
# affichage page html
@app.route('/')
def index(): return render_template('index.html')

# flux vidéo (JPEG)
@app.route('/video_feed')
def video_feed(): return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# route pour servir les fichiers statiques (JS, CSS)
@app.route('/static/<path:filename>')
def serve_static(filename): return send_from_directory('static', filename)


@socketio.on('start')
def handle_start(data):
    global cap, running
    running = True
    src = get_video_source(data.get('url'))
    cap = cv2.VideoCapture(src if src else 0)
    threading.Thread(target=process_frame_worker, daemon=True).start()

@socketio.on('stop')
def handle_stop(d):
    global running, cap
    running = False
    if cap: cap.release()

@socketio.on('toggle')
def handle_toggle(data):
    key = data.get('key')
    if key in overlay_options:
        overlay_options[key] = not overlay_options[key]

@socketio.on('click')
def handle_click(data):
    # Réception d'un clic sur l'image (coordonnées normalisées de 0.0 à 1.0)
    global target_id
    cx = data.get('x')
    cy = data.get('y')
    
    if cx is None or cy is None:
        return

    found = None
    min_dist = 1000
    
    # Chercher la boîte la plus proche ou contenant le clic
    # On itère sur box_locations rempli par process_frame_worker
    for tid, (x1, y1, x2, y2) in box_locations.items():
        # Vérifier si le point est dans la boîte
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            # Calcul de la distance au centre de la boîte pour départager
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            dist = (cx - center_x)**2 + (cy - center_y)**2
            
            if dist < min_dist:
                min_dist = dist
                found = tid

    # Si on a trouvé une cible, on la sélectionne, ou on désélectionne si c'est la même
    if found is not None:
        if target_id == found:
            target_id = None # Désélection
        else:
            target_id = found # Sélection
    else:
        # Clic hors de tout bateau -> désélection
        target_id = None


# Démarrage de l'application
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)