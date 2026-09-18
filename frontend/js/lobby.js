// lobby.js — logic for the lobby page.
// 1. Reads room code + player id from URL query string.
// 2. Fetches current room state via REST.
// 3. Opens a WebSocket and stays in sync.
// 4. Handles Ready toggle.
// 5. Enables Start only for the host when all players are ready.

const params = new URLSearchParams(window.location.search);
const roomCode = params.get("code");
const playerId = params.get("player");

const roomCodeEl = document.getElementById("roomCode");
const statusEl = document.getElementById("status");
const playerListEl = document.getElementById("playerList");
const playerCountEl = document.getElementById("playerCount");
const readyBtn = document.getElementById("readyBtn");
const startBtn = document.getElementById("startBtn");
const errorEl = document.getElementById("error");

let myReady = false;
let ws = null;

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

if (!roomCode || !playerId) {
  showError("Missing room code or player id in the URL.");
}

roomCodeEl.textContent = roomCode || "—";

function renderRoom(room) {
  playerCountEl.textContent = `(${room.players.length})`;
  playerListEl.innerHTML = "";

  for (const p of room.players) {
    const li = document.createElement("li");

    const dot = document.createElement("span");
    dot.className = "dot" + (p.ready ? " ready" : "");

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = p.name;

    li.appendChild(dot);
    li.appendChild(name);

    if (p.id === playerId) {
      const you = document.createElement("span");
      you.className = "you";
      you.textContent = "(you)";
      li.appendChild(you);
    }

    if (p.is_host) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "HOST";
      li.appendChild(badge);
    }

    playerListEl.appendChild(li);
  }

  updateButtons(room);
}

function updateButtons(room) {
  const me = room.players.find((p) => p.id === playerId);
  if (me) {
    myReady = me.ready;
    readyBtn.textContent = myReady ? "Cancel Ready" : "I'm Ready";
  }

  const allReady = room.players.every((p) => p.ready);
  const isHost = me && me.is_host;

  startBtn.disabled = !(isHost && allReady && room.players.length >= 2);
}

function connectWebSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${wsProtocol}://${window.location.host}/ws/${roomCode}/${playerId}`;

  ws = new WebSocket(url);

  ws.addEventListener("open", () => {
    statusEl.textContent = "Online";
    statusEl.classList.add("online");
    statusEl.classList.remove("offline");
  });

  ws.addEventListener("close", () => {
    statusEl.textContent = "Disconnected";
    statusEl.classList.add("offline");
    statusEl.classList.remove("online");
  });

  ws.addEventListener("message", (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (msg.type) {
      case "ROOM_STATE":
      case "PLAYER_READY":
        renderRoom(msg.room);
        break;

      case "PLAYER_JOINED":
      case "PLAYER_LEFT":
        refreshRoomState();
        break;

      default:
        break;
    }
  });
}

async function refreshRoomState() {
  try {
    const res = await fetch(`/rooms/${encodeURIComponent(roomCode)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Failed to load room (${res.status})`);
    }
    const room = await res.json();
    renderRoom(room);
  } catch (err) {
    showError(err.message);
  }
}

readyBtn.addEventListener("click", () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  myReady = !myReady;
  ws.send(JSON.stringify({ type: "SET_READY", ready: myReady }));
});

startBtn.addEventListener("click", () => {
  alert("Game would start here. (Not implemented yet — coming in a later step.)");
});

refreshRoomState().then(connectWebSocket);