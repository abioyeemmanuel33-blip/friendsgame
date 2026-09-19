// game.js — Step 2.6c: death roll + 5-second respawn.

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const TILE_SIZE = 40;

const params = new URLSearchParams(window.location.search);
const roomCode = params.get("code");
const playerId = params.get("player");
document.getElementById("roomCode").textContent = roomCode || "—";

const players = new Map();
let ws = null;
let meFinished = false;
let MAP = [];

let myDeadUntilMs = 0;     // performance.now() timestamp; 0 = alive

// ---------- toast ----------

const toastEl = document.getElementById("toast");
let toastTimer = null;

function showToast(text, durationMs = 2500) {
  toastEl.textContent = text;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, durationMs);
}

// ---------- death overlay ----------

const deathOverlayEl = document.getElementById("deathOverlay");
const deathCountEl = document.getElementById("deathCount");

// ---------- results overlay ----------

const overlayEl = document.getElementById("resultsOverlay");
const rankingListEl = document.getElementById("rankingList");

function showResults(rankings) {
  rankingListEl.innerHTML = "";
  rankings.forEach((r, i) => {
    const li = document.createElement("li");
    const medal = document.createElement("span");
    medal.className = "medal";
    medal.textContent = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i + 1}`;
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = r.color;
    const name = document.createElement("span");
    name.className = "rank-name";
    name.textContent = r.player_name;
    li.appendChild(medal);
    li.appendChild(swatch);
    li.appendChild(name);
    if (r.player_id === playerId) {
      const you = document.createElement("span");
      you.className = "rank-you";
      you.textContent = "(you)";
      li.appendChild(you);
    }
    rankingListEl.appendChild(li);
  });
  overlayEl.hidden = false;
}

// ---------- drawing ----------

function tileColor(ch) {
  switch (ch) {
    case "#": return "#1a1d26";
    case ".": return "#2a2f40";
    case "S": return "#3a4a6a";
    case "F": return "#3ddc84";
    case "X": return "#7a1f1f";
    case "Y": return "#4a5568";
    case "Z": return "#5a3a1f";
    default:  return "#000000";
  }
}

function drawHazardDecoration(ch, x, y) {
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 22px system-ui";
  if (ch === "X") {
    ctx.fillStyle = "#ff5c5c";
    ctx.fillText("🔥", x + TILE_SIZE / 2, y + TILE_SIZE / 2 + 2);
  } else if (ch === "Y") {
    ctx.fillStyle = "#e8eaf0";
    ctx.fillText("▲", x + TILE_SIZE / 2, y + TILE_SIZE / 2 + 2);
  } else if (ch === "Z") {
    ctx.fillStyle = "#c9a879";
    ctx.fillText("▦", x + TILE_SIZE / 2, y + TILE_SIZE / 2 + 2);
  }
}

function drawMap() {
  if (!MAP.length) {
    ctx.fillStyle = "#0f1116";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#8b90a0";
    ctx.font = "16px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("Waiting for map…", canvas.width / 2, canvas.height / 2);
    return;
  }

  const rows = MAP.length;
  const cols = MAP[0].length;

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const ch = MAP[row][col];
      const x = col * TILE_SIZE;
      const y = row * TILE_SIZE;

      ctx.fillStyle = tileColor(ch);
      ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);

      ctx.strokeStyle = "#0f1116";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);

      if (ch === "F") {
        ctx.fillStyle = "#0f1116";
        ctx.font = "bold 20px system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("F", x + TILE_SIZE / 2, y + TILE_SIZE / 2);
      } else if (ch === "X" || ch === "Y" || ch === "Z") {
        drawHazardDecoration(ch, x, y);
      }
    }
  }
}

function drawPlayer(p) {
  if (p.dead_until !== null && p.dead_until !== undefined) {
    // Dead players are invisible.
    if (performance.now() < p.dead_until * 1000 - performance.timeOrigin) return;
    // Actually, dead_until is a server epoch time in SECONDS.
    // Simpler check: if p.dead flag is set by client, skip.
  }
  if (p.dead) return;

  const x = p.col * TILE_SIZE;
  const y = p.row * TILE_SIZE;

  const bodyColor = p.finished_at ? "#facc15" : p.color;

  ctx.fillStyle = bodyColor;
  ctx.fillRect(x + 4, y + 4, TILE_SIZE - 8, TILE_SIZE - 8);

  ctx.fillStyle = "rgba(255,255,255,0.2)";
  ctx.fillRect(x + 4, y + 4, TILE_SIZE - 8, 6);

  if (p.id === playerId) {
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(x + 3, y + 3, TILE_SIZE - 6, TILE_SIZE - 6);
  }

  ctx.fillStyle = "#e8eaf0";
  ctx.font = "11px system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.fillText(p.name, x + TILE_SIZE / 2, y - 2);

  if (p.finished_at) {
    ctx.fillStyle = "#facc15";
    ctx.font = "bold 14px system-ui";
    ctx.textBaseline = "top";
    ctx.fillText("✓", x + TILE_SIZE / 2, y + TILE_SIZE + 2);
  }
}

function draw() {
  drawMap();
  for (const p of players.values()) {
    if (p.id !== playerId) drawPlayer(p);
  }
  const me = players.get(playerId);
  if (me && !me.dead) drawPlayer(me);
}

let lastDeathCountShown = -1;

function updateDeathOverlay() {
  if (myDeadUntilMs <= 0) {
    deathOverlayEl.hidden = true;
    lastDeathCountShown = -1;
    return;
  }

  const remaining = myDeadUntilMs - performance.now();
  if (remaining <= 0) {
    myDeadUntilMs = 0;
    deathOverlayEl.hidden = true;
    lastDeathCountShown = -1;
    return;
  }

  deathOverlayEl.hidden = false;
  const seconds = Math.ceil(remaining / 1000);
  if (seconds !== lastDeathCountShown) {
    deathCountEl.textContent = String(seconds);
    lastDeathCountShown = seconds;
  }
}

function animate() {
  draw();
  updateDeathOverlay();
  requestAnimationFrame(animate);
}

// ---------- websocket ----------

function connectWebSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${wsProtocol}://${window.location.host}/ws/${roomCode}/${playerId}`;

  ws = new WebSocket(url);

  ws.addEventListener("open", () => console.log("ws: open"));
  ws.addEventListener("close", () => console.log("ws: closed"));

  ws.addEventListener("message", (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }

    switch (msg.type) {
      case "ROOM_STATE":
      case "GAME_STARTED":
        applyRoomState(msg.room);
        break;

      case "HAZARDS_UPDATED":
        if (msg.hazard_map) MAP = msg.hazard_map.slice();
        break;

      case "PLAYER_MOVED": {
        const p = players.get(msg.player_id);
        if (p) {
          p.row = msg.row;
          p.col = msg.col;
        }
        if (msg.hazard_map) MAP = msg.hazard_map.slice();
        break;
      }

      case "PLAYER_DIED": {
        const p = players.get(msg.player_id);
        if (p) {
          p.dead = true;
        }
        if (msg.player_id === playerId) {
          // Dead_until is server epoch seconds; convert to local perf clock.
          const serverNow = Date.now() / 1000;
          const secondsUntilAlive = msg.dead_until - serverNow;
          myDeadUntilMs = performance.now() + secondsUntilAlive * 1000;
        } else {
          showToast(`${msg.player_name} died! 💀`);
        }
        if (msg.hazard_map) MAP = msg.hazard_map.slice();
        break;
      }

      case "PLAYER_RESPAWNED": {
        const p = players.get(msg.player_id);
        if (p) {
          p.dead = false;
          p.row = msg.row;
          p.col = msg.col;
        }
        if (msg.player_id === playerId) {
          myDeadUntilMs = 0;
        }
        break;
      }

      case "PLAYER_FINISHED": {
        const p = players.get(msg.player_id);
        if (p) p.finished_at = msg.finished_at;
        if (msg.player_id === playerId) {
          meFinished = true;
          showToast("You finished! Waiting for others…");
        } else {
          showToast(`${msg.player_name} finished!`);
        }
        break;
      }

      case "GAME_ENDED":
        showResults(msg.rankings);
        break;

      case "PLAYER_JOINED":
      case "PLAYER_LEFT":
      case "PLAYER_READY":
        break;

      case "ERROR":
        console.warn("server error:", msg.message);
        break;

      default:
        break;
    }
  });
}

function applyRoomState(room) {
  if (room.hazard_map) {
    MAP = room.hazard_map.slice();
  }
  players.clear();
  for (const p of room.players) {
    players.set(p.id, {
      id: p.id,
      name: p.name,
      color: p.color,
      row: p.row,
      col: p.col,
      is_host: p.is_host,
      finished_at: p.finished_at,
      dead: p.dead_until !== null && p.dead_until !== undefined,
    });
    if (p.id === playerId) {
      if (p.finished_at) meFinished = true;
      if (p.dead_until) {
        const serverNow = Date.now() / 1000;
        const secondsUntilAlive = p.dead_until - serverNow;
        myDeadUntilMs = performance.now() + Math.max(0, secondsUntilAlive) * 1000;
      } else {
        myDeadUntilMs = 0;
      }
    }
  }
}

// ---------- input ----------

window.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (meFinished) return;
  if (myDeadUntilMs > 0) return;   // frozen while dead

  const key = e.key.toLowerCase();
  let drow = 0, dcol = 0;

  if (key === "arrowup" || key === "w")    { drow = -1; }
  else if (key === "arrowdown" || key === "s")  { drow = 1; }
  else if (key === "arrowleft" || key === "a")  { dcol = -1; }
  else if (key === "arrowright" || key === "d") { dcol = 1; }
  else { return; }

  e.preventDefault();

  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "MOVE", drow, dcol }));
});

// ---------- boot ----------

animate();
connectWebSocket();

function backToLobby() {
  window.location.href = `/lobby.html?code=${encodeURIComponent(roomCode)}&player=${encodeURIComponent(playerId)}`;
}
document.getElementById("backBtn").addEventListener("click", backToLobby);
document.getElementById("overlayBackBtn").addEventListener("click", backToLobby);