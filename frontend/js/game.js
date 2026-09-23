// game.js — Step 2.9: hybrid d-pad + center joystick.

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

let myDeadUntilMs = 0;
let myFrozenUntilMs = 0;
let mySpeedUntilMs = 0;
let myShieldUntilMs = 0;

// ---------- touch detection ----------

const isTouchDevice = ("ontouchstart" in window) || (navigator.maxTouchPoints > 0);

if (isTouchDevice) {
  document.body.classList.add("touch");
  const hint = document.getElementById("hintText");
  if (hint) hint.textContent = "Swipe, joystick, or d-pad";
}

// ---------- send move ----------

function canMove() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  if (meFinished) return false;
  if (myDeadUntilMs > 0) return false;
  if (myFrozenUntilMs > performance.now()) return false;
  return true;
}

function sendMove(drow, dcol) {
  if (!canMove()) return;
  ws.send(JSON.stringify({ type: "MOVE", drow, dcol }));
}

// ---------- swipe detection on canvas ----------

const SWIPE_MIN_DISTANCE = 24;

let touchStartX = 0, touchStartY = 0, touchActive = false;

canvas.addEventListener("touchstart", (e) => {
  const t = e.changedTouches[0];
  touchStartX = t.clientX;
  touchStartY = t.clientY;
  touchActive = true;
  e.preventDefault();
}, { passive: false });

canvas.addEventListener("touchend", (e) => {
  if (!touchActive) return;
  touchActive = false;

  const t = e.changedTouches[0];
  const dx = t.clientX - touchStartX;
  const dy = t.clientY - touchStartY;
  const absX = Math.abs(dx), absY = Math.abs(dy);

  if (Math.max(absX, absY) < SWIPE_MIN_DISTANCE) return;

  if (absX > absY) sendMove(0, dx > 0 ? 1 : -1);
  else             sendMove(dy > 0 ? 1 : -1, 0);

  e.preventDefault();
}, { passive: false });

canvas.addEventListener("touchmove", (e) => { e.preventDefault(); }, { passive: false });

// ---------- d-pad buttons ----------

document.querySelectorAll(".dpad").forEach((btn) => {
  btn.addEventListener("touchstart", (e) => {
    e.preventDefault();
    const dir = btn.dataset.dir;
    if (dir === "up")    sendMove(-1, 0);
    if (dir === "down")  sendMove(1, 0);
    if (dir === "left")  sendMove(0, -1);
    if (dir === "right") sendMove(0, 1);
  }, { passive: false });

  btn.addEventListener("click", (e) => {
    e.preventDefault();
    const dir = btn.dataset.dir;
    if (dir === "up")    sendMove(-1, 0);
    if (dir === "down")  sendMove(1, 0);
    if (dir === "left")  sendMove(0, -1);
    if (dir === "right") sendMove(0, 1);
  });
});

// ---------- joystick ----------

const joystickBase = document.getElementById("joystickBase");
const joystickKnob = document.getElementById("joystickKnob");

const JOY_MAX_DIST = 26;     // max knob travel from center, in pixels
const JOY_DEADZONE = 8;      // no move if knob within this radius
const JOY_REPEAT_MS = 200;   // how often to send a MOVE while held

let joyActive = false;
let joyDrow = 0;
let joyDcol = 0;
let joyRepeatTimer = null;

function getJoystickCenter() {
  const rect = joystickBase.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

// Snap a vector to one of 8 directions.
function snapTo8(dx, dy) {
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;    // -180..180, 0 = right
  const sector = ((Math.round(angle / 45) + 8) % 8);    // 0..7

  switch (sector) {
    case 0: return [ 0,  1];   // E
    case 1: return [ 1,  1];   // SE
    case 2: return [ 1,  0];   // S
    case 3: return [ 1, -1];   // SW
    case 4: return [ 0, -1];   // W
    case 5: return [-1, -1];   // NW
    case 6: return [-1,  0];   // N
    case 7: return [-1,  1];   // NE
  }
  return [0, 0];
}

function startJoyRepeat() {
  if (joyRepeatTimer !== null) return;
  joyRepeatTimer = setInterval(() => {
    if (!joyActive) return;
    if (joyDrow === 0 && joyDcol === 0) return;
    sendMove(joyDrow, joyDcol);
  }, JOY_REPEAT_MS);
}

function stopJoyRepeat() {
  if (joyRepeatTimer !== null) {
    clearInterval(joyRepeatTimer);
    joyRepeatTimer = null;
  }
}

function updateJoystick(e) {
  const t = e.touches ? e.touches[0] : e;
  const center = getJoystickCenter();
  let dx = t.clientX - center.x;
  let dy = t.clientY - center.y;

  const dist = Math.hypot(dx, dy);

  // Clamp the knob inside the base.
  if (dist > JOY_MAX_DIST) {
    dx = dx / dist * JOY_MAX_DIST;
    dy = dy / dist * JOY_MAX_DIST;
  }

  joystickKnob.style.transform = `translate(${dx}px, ${dy}px)`;

  if (dist < JOY_DEADZONE) {
    joyDrow = 0;
    joyDcol = 0;
    return;
  }

  const [drow, dcol] = snapTo8(dx, dy);
  joyDrow = drow;
  joyDcol = dcol;
}

function resetJoystick() {
  joyActive = false;
  joyDrow = 0;
  joyDcol = 0;
  joystickKnob.style.transform = "translate(0, 0)";
  stopJoyRepeat();
}

joystickBase.addEventListener("touchstart", (e) => {
  e.preventDefault();
  joyActive = true;
  updateJoystick(e);
  // Immediate one-shot move on first contact.
  if (joyDrow !== 0 || joyDcol !== 0) sendMove(joyDrow, joyDcol);
  startJoyRepeat();
}, { passive: false });

joystickBase.addEventListener("touchmove", (e) => {
  if (!joyActive) return;
  e.preventDefault();
  updateJoystick(e);
}, { passive: false });

joystickBase.addEventListener("touchend", (e) => {
  e.preventDefault();
  resetJoystick();
}, { passive: false });

joystickBase.addEventListener("touchcancel", () => resetJoystick());

// Mouse fallback for testing on desktop.
joystickBase.addEventListener("mousedown", (e) => {
  e.preventDefault();
  joyActive = true;
  updateJoystick(e);
  if (joyDrow !== 0 || joyDcol !== 0) sendMove(joyDrow, joyDcol);
  startJoyRepeat();
});
window.addEventListener("mousemove", (e) => {
  if (!joyActive) return;
  updateJoystick(e);
});
window.addEventListener("mouseup", () => {
  if (joyActive) resetJoystick();
});

// ---------- toast ----------

const toastEl = document.getElementById("toast");
let toastTimer = null;

function showToast(text, durationMs = 2500) {
  toastEl.textContent = text;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, durationMs);
}

// ---------- status bar ----------

const statusBar = document.createElement("div");
statusBar.className = "status-bar";
document.querySelector(".game-wrap").insertBefore(
  statusBar,
  document.querySelector(".game-footer")
);

function renderStatusBar() {
  const now = performance.now();
  const parts = [];

  if (mySpeedUntilMs > now) {
    const s = Math.ceil((mySpeedUntilMs - now) / 1000);
    parts.push(`<span class="effect speed">⚡ SPEED ${s}s</span>`);
  }
  if (myShieldUntilMs > now) {
    const s = Math.ceil((myShieldUntilMs - now) / 1000);
    parts.push(`<span class="effect shield">🛡 SHIELD ${s}s</span>`);
  }
  if (myFrozenUntilMs > now) {
    const s = Math.ceil((myFrozenUntilMs - now) / 1000);
    parts.push(`<span class="effect frozen">❄ FROZEN ${s}s</span>`);
  }

  statusBar.innerHTML = parts.join(" ");
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
    case "A": return "#3d5c2a";
    case "B": return "#2a3d5c";
    case "C": return "#4a2a5c";
    default:  return "#000000";
  }
}

function drawTileDecoration(ch, x, y) {
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 22px system-ui";

  if (ch === "X")       { ctx.fillStyle = "#ff5c5c"; ctx.fillText("🔥", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
  else if (ch === "Y")  { ctx.fillStyle = "#e8eaf0"; ctx.fillText("▲", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
  else if (ch === "Z")  { ctx.fillStyle = "#c9a879"; ctx.fillText("▦", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
  else if (ch === "A")  { ctx.fillStyle = "#e8eaf0"; ctx.fillText("⚡", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
  else if (ch === "B")  { ctx.fillStyle = "#e8eaf0"; ctx.fillText("🛡", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
  else if (ch === "C")  { ctx.fillStyle = "#e8eaf0"; ctx.fillText("❄", x + TILE_SIZE/2, y + TILE_SIZE/2 + 2); }
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
        ctx.fillText("F", x + TILE_SIZE/2, y + TILE_SIZE/2);
      } else if (["X","Y","Z","A","B","C"].includes(ch)) {
        drawTileDecoration(ch, x, y);
      }
    }
  }
}

function drawPlayer(p) {
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
  ctx.fillText(p.name, x + TILE_SIZE/2, y - 2);

  if (p.finished_at) {
    ctx.fillStyle = "#facc15";
    ctx.font = "bold 14px system-ui";
    ctx.textBaseline = "top";
    ctx.fillText("✓", x + TILE_SIZE/2, y + TILE_SIZE + 2);
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
  renderStatusBar();
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
        if (p) { p.row = msg.row; p.col = msg.col; }
        if (msg.hazard_map) MAP = msg.hazard_map.slice();
        break;
      }

      case "PLAYER_DIED": {
        const p = players.get(msg.player_id);
        if (p) p.dead = true;
        if (msg.player_id === playerId) {
          const serverNow = Date.now() / 1000;
          myDeadUntilMs = performance.now() + (msg.dead_until - serverNow) * 1000;
        } else {
          showToast(`${msg.player_name} died! 💀`);
        }
        if (msg.hazard_map) MAP = msg.hazard_map.slice();
        break;
      }

      case "PLAYER_RESPAWNED": {
        const p = players.get(msg.player_id);
        if (p) { p.dead = false; p.row = msg.row; p.col = msg.col; }
        if (msg.player_id === playerId) myDeadUntilMs = 0;
        break;
      }

      case "POWERUP_GRANTED": {
        if (msg.hazard_map) MAP = msg.hazard_map.slice();

        if (msg.player_id === playerId) {
          const now = performance.now();
          if (msg.effect === "speed")  mySpeedUntilMs  = now + 5000;
          if (msg.effect === "shield") myShieldUntilMs = now + 10000;
        }

        if (msg.effect === "freeze") {
          if (msg.player_id === playerId) {
            showToast("You froze everyone! ❄");
          } else {
            showToast(`${msg.player_name} froze everyone! ❄`);
            if (msg.frozen_others_until) {
              const serverNow = Date.now() / 1000;
              const secondsLeft = msg.frozen_others_until - serverNow;
              myFrozenUntilMs = performance.now() + Math.max(0, secondsLeft) * 1000;
            }
          }
        } else {
          const label = msg.effect.toUpperCase();
          if (msg.player_id === playerId) showToast(`You got ${label}!`);
          else                            showToast(`${msg.player_name} got ${label}`);
        }
        break;
      }

      case "POWERUP_EXPIRED": {
        if (msg.player_id === playerId) {
          for (const eff of msg.effects) {
            if (eff === "speed")  mySpeedUntilMs  = 0;
            if (eff === "shield") myShieldUntilMs = 0;
            if (eff === "frozen") myFrozenUntilMs = 0;
          }
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
  if (room.hazard_map) MAP = room.hazard_map.slice();
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
        myDeadUntilMs = performance.now() + Math.max(0, (p.dead_until - serverNow) * 1000);
      } else {
        myDeadUntilMs = 0;
      }
    }
  }
}

// ---------- keyboard (desktop) ----------

window.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (meFinished) return;
  if (myDeadUntilMs > 0) return;
  if (myFrozenUntilMs > performance.now()) return;

  const key = e.key.toLowerCase();
  let drow = 0, dcol = 0;

  if (key === "arrowup" || key === "w")    { drow = -1; }
  else if (key === "arrowdown" || key === "s")  { drow = 1; }
  else if (key === "arrowleft" || key === "a")  { dcol = -1; }
  else if (key === "arrowright" || key === "d") { dcol = 1; }
  else { return; }

  e.preventDefault();
  sendMove(drow, dcol);
});

// ---------- boot ----------

animate();
connectWebSocket();

function backToLobby() {
  window.location.href = `/lobby.html?code=${encodeURIComponent(roomCode)}&player=${encodeURIComponent(playerId)}`;
}
document.getElementById("backBtn").addEventListener("click", backToLobby);
document.getElementById("overlayBackBtn").addEventListener("click", backToLobby);