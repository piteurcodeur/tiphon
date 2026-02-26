"""
jetson_comm.py — Bibliothèque de communication WebSocket vers le serveur monitor.

Usage minimal :
    from jetson_comm import JetsonComm
    comm = JetsonComm("192.168.1.XX")
    await comm.connect()
    await comm.send_text("Hello")
    await comm.send_image_file("photo.jpg")
    await comm.disconnect()

Ou en mode context manager :
    async with JetsonComm("192.168.1.XX") as comm:
        await comm.send_text("Hello")
"""

import asyncio
import json
import base64
import logging
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger("jetson_comm")


class JetsonComm:
    """
    Client WebSocket pour envoyer des messages et images au serveur monitor.

    Paramètres
    ----------
    host : str
        IP ou hostname du serveur (ex: "192.168.1.45")
    port : int
        Port WebSocket du serveur (défaut: 8765)
    auto_reconnect : bool
        Reconnexion automatique si la connexion est perdue (défaut: True)
    reconnect_delay : float
        Secondes d'attente entre deux tentatives (défaut: 3.0)
    """

    def __init__(self, host: str, port: int = 8765,
                 auto_reconnect: bool = True, reconnect_delay: float = 3.0):
        self.uri             = f"ws://{host}:{port}"
        self.auto_reconnect  = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self._ws             = None
        self._connected      = False

    # ── Propriété ──────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """True si la connexion WebSocket est active."""
        return self._connected and self._ws is not None

    # ── Connexion ──────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Établit la connexion au serveur.
        Retourne True si succès, False sinon.
        """
        try:
            self._ws = await websockets.connect(self.uri)
            await self._ws.send(json.dumps({"role": "jetson"}))
            self._connected = True
            logger.info(f"[JetsonComm] Connecté à {self.uri}")
            return True
        except Exception as e:
            self._connected = False
            logger.error(f"[JetsonComm] Échec connexion : {e}")
            return False

    async def disconnect(self):
        """Ferme proprement la connexion."""
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("[JetsonComm] Déconnecté")

    async def _ensure_connected(self) -> bool:
        """Vérifie la connexion et tente de reconnecter si nécessaire."""
        if self.connected:
            return True
        if self.auto_reconnect:
            logger.warning("[JetsonComm] Connexion perdue, reconnexion...")
            return await self.connect()
        return False

    # ── Envoi ──────────────────────────────────────────────────────────────────

    async def send_text(self, text: str) -> bool:
        """
        Envoie un message texte.

        Paramètres
        ----------
        text : str  Le message à envoyer.

        Retourne True si envoyé avec succès.
        """
        if not await self._ensure_connected():
            logger.error("[JetsonComm] send_text : non connecté")
            return False
        try:
            payload = json.dumps({"type": "text", "text": str(text)})
            await self._ws.send(payload)
            logger.debug(f"[JetsonComm] Texte envoyé : {text[:80]}")
            return True
        except (ConnectionClosed, WebSocketException) as e:
            self._connected = False
            logger.error(f"[JetsonComm] Erreur envoi texte : {e}")
            return False

    async def send_image_bytes(self, data: bytes, fmt: str = "jpeg") -> bool:
        """
        Envoie une image à partir de bytes bruts.

        Paramètres
        ----------
        data : bytes  Contenu binaire de l'image.
        fmt  : str    Format de l'image ("jpeg", "png", …).

        Retourne True si envoyé avec succès.
        """
        if not await self._ensure_connected():
            logger.error("[JetsonComm] send_image_bytes : non connecté")
            return False
        try:
            b64 = base64.b64encode(data).decode("utf-8")
            payload = json.dumps({"type": "image", "fmt": fmt, "data": b64})
            await self._ws.send(payload)
            logger.debug(f"[JetsonComm] Image envoyée ({len(data)} octets, {fmt})")
            return True
        except (ConnectionClosed, WebSocketException) as e:
            self._connected = False
            logger.error(f"[JetsonComm] Erreur envoi image : {e}")
            return False

    async def send_image_file(self, path: str | Path) -> bool:
        """
        Envoie une image à partir d'un fichier disque.

        Paramètres
        ----------
        path : str | Path  Chemin vers le fichier image (jpg, png…).

        Retourne True si envoyé avec succès.
        """
        path = Path(path)
        if not path.exists():
            logger.error(f"[JetsonComm] Fichier introuvable : {path}")
            return False
        fmt = path.suffix.lstrip(".").lower()
        if fmt == "jpg":
            fmt = "jpeg"
        with open(path, "rb") as f:
            data = f.read()
        return await self.send_image_bytes(data, fmt)

    async def send_image_numpy(self, frame, fmt: str = "jpeg", quality: int = 85) -> bool:
        """
        Envoie une image à partir d'un array NumPy (frame OpenCV).

        Paramètres
        ----------
        frame   : np.ndarray  Image BGR (format OpenCV).
        fmt     : str         "jpeg" ou "png".
        quality : int         Qualité JPEG 0-100 (ignoré pour PNG).

        Retourne True si envoyé avec succès.
        """
        try:
            import cv2
        except ImportError:
            logger.error("[JetsonComm] OpenCV (cv2) requis pour send_image_numpy")
            return False

        ext    = ".jpg" if fmt == "jpeg" else ".png"
        params = [cv2.IMWRITE_JPEG_QUALITY, quality] if fmt == "jpeg" else []
        ok, buf = cv2.imencode(ext, frame, params)
        if not ok:
            logger.error("[JetsonComm] Échec encodage image NumPy")
            return False
        return await self.send_image_bytes(buf.tobytes(), fmt)

    # ── Context manager ────────────────────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()


# ── Helpers synchrones ────────────────────────────────────────────────────────

def run_send_text(host: str, text: str, port: int = 8765):
    """Envoi synchrone d'un texte (pour scripts simples sans async)."""
    async def _run():
        async with JetsonComm(host, port, auto_reconnect=False) as comm:
            await comm.send_text(text)
    asyncio.run(_run())


def run_send_image_file(host: str, path, port: int = 8765):
    """Envoi synchrone d'un fichier image (pour scripts simples sans async)."""
    async def _run():
        async with JetsonComm(host, port, auto_reconnect=False) as comm:
            await comm.send_image_file(path)
    asyncio.run(_run())