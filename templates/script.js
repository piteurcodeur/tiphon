const socket = io();
const statusLine = document.getElementById('status-line');
const tacticalList = document.getElementById('tactical-list');
const canvas = document.getElementById('radarCanvas');
const ctx = canvas.getContext('2d');
const videoImg = document.getElementById('video');

// --- HORLOGE ZULU (UTC) ---
function updateClock() {
    const now = new Date();
    // UTC Hours/Minutes/Seconds, formatage avec padStart pour 0
    const h = String(now.getUTCHours()).padStart(2, '0');
    const m = String(now.getUTCMinutes()).padStart(2, '0');
    const s = String(now.getUTCSeconds()).padStart(2, '0');
    document.getElementById('clock-zulu').textContent = `${h}:${m}:${s} Z`;
}
// Mise à jour toutes les secondes
setInterval(updateClock, 1000);
updateClock(); // Appel initial

// --- CLICK SUR VIDEO (Pour sélectionner la cible) ---
videoImg.onclick = function(e) {
    const rect = videoImg.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    socket.emit('click', { x: x, y: y });
};

// --- SLIDE PANELS ---
const leftPanel = document.getElementById('left-panel');
const btnLeft = document.getElementById('btn-left');
btnLeft.onclick = () => {
    leftPanel.classList.toggle('closed');
    btnLeft.textContent = leftPanel.classList.contains('closed') ? '►' : '◄';
};

const rightPanel = document.getElementById('right-panel');
const btnRight = document.getElementById('btn-right');
btnRight.onclick = () => {
    rightPanel.classList.toggle('closed');
    btnRight.textContent = rightPanel.classList.contains('closed') ? '◄' : '►';
};

// --- CHECKBOXES COMPLETES ---
const allOptions = ['ID', 'Classe', 'Distance', 'Vitesse', 'Cap', 'Conf'];
const defaults = { 'Classe': true, 'ID': false, 'Distance': false, 'Vitesse': false, 'Cap': false, 'Conf': false };
const boxContainer = document.getElementById('checkboxes');

allOptions.forEach(opt => {
    const div = document.createElement('div');
    div.className = 'chk-item';
    
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = 'chk-' + opt;
    if(defaults[opt]) input.checked = true;
    
    input.addEventListener('change', () => {
        socket.emit('toggle', { key: opt });
    });

    const lbl = document.createElement('label');
    lbl.htmlFor = 'chk-' + opt;
    lbl.textContent = opt;

    div.onclick = (e) => {
        if(e.target !== input) {
            input.checked = !input.checked;
            socket.emit('toggle', { key: opt });
        }
    };

    div.appendChild(input);
    div.appendChild(lbl);
    boxContainer.appendChild(div);
});

// --- COMMANDES ---
document.getElementById('btnStart').onclick = () => {
    socket.emit('start', { url: document.getElementById('url').value });
    statusLine.textContent = "Démarrage...";
};
document.getElementById('btnStop').onclick = () => socket.emit('stop', {});

// --- RADAR LOGIC ---
let radarZoom = 1.0;
const zoomSlider = document.getElementById('zoomSlider');
const zoomText = document.getElementById('zoomText');

zoomSlider.oninput = function() {
    radarZoom = parseFloat(this.value);
    zoomText.textContent = radarZoom.toFixed(1);
};

function drawRadar(tracks, targetId) {
    const w = canvas.width, h = canvas.height;
    const cx = w/2, cy = h/2;
    const radius = (w/2)-10;
    
    // Zoom Logic: Plus le zoom est grand, plus la distance Max affichée est petite
    const maxDist = 200 / radarZoom;

    ctx.clearRect(0,0,w,h);
    
    // Grille radar
    ctx.strokeStyle = '#005500'; ctx.lineWidth = 1;
    [1, 0.66, 0.33].forEach(r => { ctx.beginPath(); ctx.arc(cx,cy,radius*r,0,Math.PI*2); ctx.stroke(); });
    // Croix centrale
    ctx.beginPath(); ctx.moveTo(cx-radius,cy); ctx.lineTo(cx+radius,cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx,cy-radius); ctx.lineTo(cx,cy+radius); ctx.stroke();
    
    // FOV Lines
    ctx.strokeStyle = '#003300';
    ctx.beginPath();
    ctx.moveTo(cx, cy); ctx.lineTo(cx + radius * Math.sin(1.3), cy - radius * Math.cos(1.3));
    ctx.moveTo(cx, cy); ctx.lineTo(cx - radius * Math.sin(1.3), cy - radius * Math.cos(1.3));
    ctx.stroke();

    // Balayage
    const angle = (Date.now()/1000 * 2) % (Math.PI*2);
    ctx.strokeStyle = 'rgba(0,255,0,0.4)';
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx+radius*Math.cos(angle), cy+radius*Math.sin(angle)); ctx.stroke();

    // Dessin des Bateaux
    for (const [tid, t] of Object.entries(tracks)) {
        if (t.azimuth_factor === undefined || t.distance === undefined) continue;
        const ang = t.azimuth_factor * (150 * (Math.PI/180) / 2);
        const distPx = (t.distance / maxDist) * radius;
        
        if (distPx > radius) continue;
        
        const rx = cx + distPx * Math.sin(ang);
        const ry = cy - distPx * Math.cos(ang);
        
        const isTgt = (String(tid) === String(targetId));
        
        let pointColor = t.color_hex || '#00ffcc'; 
        let pointSize = 4;

        if (isTgt) {
            pointSize = 7;
            if (Date.now() % 500 < 250) pointColor = '#ffffff'; 
        }

        ctx.fillStyle = pointColor;
        ctx.beginPath(); 
        ctx.arc(rx, ry, pointSize, 0, Math.PI*2); 
        ctx.fill();
        
        ctx.fillStyle = '#fff'; 
        ctx.font = '10px Arial'; 
        ctx.fillText(tid, rx+6, ry-4);
    }
}

// --- SOCKET UPDATE ---
socket.on('update', d => {
    statusLine.textContent = `FPS: ${d.fps}`;

    const tracks = d.tracks || {};
    let html = "";
    
    // Génération du tableau
    for (const [id, t] of Object.entries(tracks)) {
        const isTgt = String(d.target_id) === String(id);
        
        // NOUVELLE LOGIQUE: Couleur ROUGE si la classe est Militaire, Fregate, Patrouilleur, etc.
        const isMilitary = t.name && (
            t.name.includes('Militaire') || 
            t.name.includes('Fregate') || 
            t.name.includes('Patrouilleur') ||
            t.name.includes('Porte-avion') ||
            t.name.includes('Ravitailleur') ||
            t.name.includes('Sous-marin')
        );

        // Si Militaire = ROUGE, si Cible = ROUGE Clair, sinon VERT
        const rowColor = isMilitary ? '#ff0000' : (isTgt ? '#ff3333' : '#0aff0a'); 
        const fontWeight = isTgt || isMilitary ? 'bold' : 'normal';

        html += `<div class="track-row" style="color:${rowColor}; font-weight:${fontWeight};">
            <span>${id}</span>
            <span>${t.name.slice(0,9)}</span>
            <span>${Math.round(t.distance)}m</span>
            <span>${t.speed.toFixed(1)}kt</span>
        </div>`;
    }
    tacticalList.innerHTML = html;
    
    // Mise à jour du radar
    drawRadar(tracks, d.target_id);
});