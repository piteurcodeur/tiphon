"""
test_comm.py — Script de test pour jetson_comm.py

Lance différents scénarios pour vérifier que la communication
avec le serveur monitor fonctionne correctement.

Usage :
    python test_comm.py --host 192.168.1.XX
    python test_comm.py --host 192.168.1.XX --test texte
    python test_comm.py --host 192.168.1.XX --test image --img photo.jpg
"""

import asyncio
import argparse
import logging
import time
import struct

from jetson_comm import JetsonComm

# Logging lisible dans la console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("test_comm")


# ── Générateur d'image PNG synthétique (sans dépendance externe) ──────────────

def _make_png(width: int, height: int, r: int, g: int, b: int) -> bytes:
    """Génère un PNG unicolore minimal en pur Python."""
    import zlib, struct

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    # En-tête PNG
    header = b"\x89PNG\r\n\x1a\n"
    ihdr   = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    # Données image : une ligne de pixels RGB répétée
    raw    = b""
    row    = b"\x00" + bytes([r, g, b] * width)   # filtre 0 + pixels
    raw    = row * height
    idat   = chunk(b"IDAT", zlib.compress(raw))
    iend   = chunk(b"IEND", b"")

    return header + ihdr + idat + iend


def make_test_image(label: str = "", width: int = 320, height: int = 200) -> bytes:
    """
    Crée une image PNG de test colorée (couleur change selon le label).
    Retourne les bytes PNG.
    """
    colors = {
        "rouge":  (220,  60,  60),
        "vert":   ( 60, 200,  80),
        "bleu":   ( 60, 100, 220),
        "jaune":  (220, 200,  40),
        "violet": (160,  60, 220),
    }
    r, g, b = colors.get(label, (100, 140, 200))
    return _make_png(width, height, r, g, b)


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_connexion(comm: JetsonComm):
    """Test 1 : vérifier la connexion."""
    log.info("══ TEST 1 : Connexion ══")
    ok = await comm.connect()
    if ok:
        log.info("✅ Connexion réussie")
    else:
        log.error("❌ Connexion échouée — vérifier IP et que node server.js tourne")
    return ok


async def test_textes(comm: JetsonComm):
    """Test 2 : envoi de plusieurs messages texte."""
    log.info("══ TEST 2 : Messages texte ══")
    messages = [
        "🟢 Démarrage du test de communication",
        "📊 Température CPU : 42.3 °C",
        "🔋 Tension batterie : 11.8 V",
        "📍 Position GPS : 48.8566° N, 2.3522° E",
        "⚠️  Alerte : seuil de température dépassé",
        "✅ Fin du test texte",
    ]
    for i, msg in enumerate(messages, 1):
        ok = await comm.send_text(msg)
        status = "✅" if ok else "❌"
        log.info(f"  {status} Message {i}/{len(messages)} : {msg[:50]}")
        await asyncio.sleep(0.6)


async def test_images_synthetiques(comm: JetsonComm):
    """Test 3 : envoi d'images PNG générées sans dépendance externe."""
    log.info("══ TEST 3 : Images synthétiques ══")
    couleurs = ["rouge", "vert", "bleu", "jaune", "violet"]
    for i, couleur in enumerate(couleurs, 1):
        await comm.send_text(f"🖼️  Envoi image {i}/{len(couleurs)} — couleur : {couleur}")
        img_bytes = make_test_image(couleur)
        ok = await comm.send_image_bytes(img_bytes, fmt="png")
        status = "✅" if ok else "❌"
        log.info(f"  {status} Image {couleur} ({len(img_bytes)} octets)")
        await asyncio.sleep(1.0)


async def test_image_fichier(comm: JetsonComm, path: str):
    """Test 4 : envoi d'un fichier image existant."""
    log.info(f"══ TEST 4 : Fichier image '{path}' ══")
    await comm.send_text(f"📂 Envoi du fichier : {path}")
    ok = await comm.send_image_file(path)
    status = "✅" if ok else "❌"
    log.info(f"  {status} Fichier '{path}'")


async def test_rafale(comm: JetsonComm, n: int = 20, delay: float = 0.2):
    """Test 5 : envoi rapide de N messages pour tester la robustesse."""
    log.info(f"══ TEST 5 : Rafale de {n} messages (délai {delay}s) ══")
    errors = 0
    for i in range(1, n + 1):
        ts  = time.strftime("%H:%M:%S")
        ok  = await comm.send_text(f"[{ts}] Rafale #{i}/{n}")
        if not ok:
            errors += 1
        await asyncio.sleep(delay)
    log.info(f"  {'✅' if errors == 0 else '⚠️ '} {n - errors}/{n} messages envoyés avec succès")


async def test_deconnexion_reconnexion(host: str, port: int):
    """Test 6 : déconnexion et reconnexion automatique."""
    log.info("══ TEST 6 : Déconnexion / reconnexion ══")
    comm = JetsonComm(host, port, auto_reconnect=True)
    await comm.connect()
    await comm.send_text("📡 Test avant déconnexion")
    await comm.disconnect()
    log.info("  Déconnecté volontairement, reconnexion dans 2s...")
    await asyncio.sleep(2)
    ok = await comm.send_text("📡 Test après reconnexion automatique")
    log.info(f"  {'✅' if ok else '❌'} Reconnexion {'réussie' if ok else 'échouée'}")
    await comm.disconnect()


# ── Point d'entrée ────────────────────────────────────────────────────────────

async def main(host: str, port: int, test: str, img_path: str):
    log.info(f"Serveur cible : ws://{host}:{port}")
    log.info("─" * 50)

    if test == "connexion":
        comm = JetsonComm(host, port)
        await test_connexion(comm)
        await comm.disconnect()

    elif test == "texte":
        async with JetsonComm(host, port) as comm:
            await test_textes(comm)

    elif test == "image":
        async with JetsonComm(host, port) as comm:
            if img_path:
                await test_image_fichier(comm, img_path)
            else:
                await test_images_synthetiques(comm)

    elif test == "rafale":
        async with JetsonComm(host, port) as comm:
            await test_rafale(comm)

    elif test == "reconnexion":
        await test_deconnexion_reconnexion(host, port)

    elif test == "tout":
        async with JetsonComm(host, port) as comm:
            if not comm.connected:
                log.error("Connexion impossible, abandon.")
                return
            await test_textes(comm)
            await asyncio.sleep(0.5)
            await test_images_synthetiques(comm)
            await asyncio.sleep(0.5)
            if img_path:
                await test_image_fichier(comm, img_path)
            await asyncio.sleep(0.5)
            await test_rafale(comm, n=10, delay=0.15)
        await asyncio.sleep(0.5)
        await test_deconnexion_reconnexion(host, port)

    log.info("─" * 50)
    log.info("Tests terminés.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test de jetson_comm.py")
    parser.add_argument("--host", default="192.168.1.XX",
                        help="IP du serveur monitor (défaut: 192.168.1.XX)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port WebSocket (défaut: 8765)")
    parser.add_argument("--test",
                        choices=["connexion", "texte", "image", "rafale", "reconnexion", "tout"],
                        default="tout",
                        help="Scénario à lancer (défaut: tout)")
    parser.add_argument("--img", default=None,
                        help="Chemin d'un fichier image pour le test 'image'")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.test, args.img))