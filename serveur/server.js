const http = require("http");
const fs   = require("fs");
const path = require("path");
const { WebSocketServer } = require("ws");

const httpServer = http.createServer((req, res) => {
  const filePath = path.join(__dirname, "public", "index.html");
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end("Not found"); return; }
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(data);
  });
});

const wss      = new WebSocketServer({ server: httpServer });
let jetson     = null;
const browsers = new Set();

function broadcastJetsonStatus(connected) {
  const msg = JSON.stringify({ type: "jetson_status", connected });
  for (const b of browsers) {
    if (b.readyState === 1) b.send(msg);
  }
}

wss.on("connection", (ws, req) => {
  console.log(`[NEW CONNECTION] from ${req.socket.remoteAddress}`);

  ws.once("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch(e) { console.log("[PARSE ERROR]", e); ws.close(); return; }

    if (msg.role === "jetson") {
      jetson = ws;
      console.log("[+] Jetson connectée");
      broadcastJetsonStatus(true);   // ← signaler aux navigateurs

      ws.on("message", (data) => {
        const str = data.toString();
        console.log(`[JETSON MSG] ${str.substring(0, 120)}`);
        for (const b of browsers) {
          if (b.readyState === 1) b.send(str);
        }
      });

      ws.on("close", () => {
        jetson = null;
        console.log("[-] Jetson déconnectée");
        broadcastJetsonStatus(false); // ← signaler aux navigateurs
      });

    } else if (msg.role === "browser") {
      browsers.add(ws);
      console.log(`[+] Navigateur connecté (total: ${browsers.size})`);

      // Envoyer immédiatement le statut courant de la Jetson
      ws.send(JSON.stringify({ type: "jetson_status", connected: jetson !== null }));
      ws.send(JSON.stringify({ type: "info", text: "Connecté au serveur" }));

      ws.on("close", () => {
        browsers.delete(ws);
        console.log(`[-] Navigateur déconnecté (total: ${browsers.size})`);
      });

    } else {
      console.log("[?] Rôle inconnu:", msg.role);
    }
  });

  ws.on("error", (e) => console.log("[WS ERROR]", e.message));
});

const PORT = 8765;
httpServer.listen(PORT, "0.0.0.0", () => {
  console.log(`Serveur démarré → http://localhost:${PORT}`);
});