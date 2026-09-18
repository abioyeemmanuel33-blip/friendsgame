// home.js — logic for the home page (index.html).
// Reads the name field, calls /rooms/create or /rooms/join,
// then navigates to /lobby.html with the room code and player id.

const nameInput = document.getElementById("nameInput");
const codeInput = document.getElementById("codeInput");
const createBtn = document.getElementById("createBtn");
const joinBtn = document.getElementById("joinBtn");
const errorEl = document.getElementById("error");

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.textContent = "";
  errorEl.hidden = true;
}

function getPlayerName() {
  const name = nameInput.value.trim();
  if (!name) {
    showError("Please enter your name first.");
    return null;
  }
  return name;
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

function goToLobby(roomCode, playerId) {
  const url = `/lobby.html?code=${encodeURIComponent(roomCode)}&player=${encodeURIComponent(playerId)}`;
  window.location.href = url;
}

createBtn.addEventListener("click", async () => {
  clearError();
  const name = getPlayerName();
  if (!name) return;

  createBtn.disabled = true;
  try {
    const room = await postJson("/rooms/create", { host_name: name });
    const hostPlayer = room.players[0];
    goToLobby(room.code, hostPlayer.id);
  } catch (err) {
    showError(err.message);
    createBtn.disabled = false;
  }
});

joinBtn.addEventListener("click", async () => {
  clearError();
  const name = getPlayerName();
  if (!name) return;

  const code = codeInput.value.trim().toUpperCase();
  if (!code) {
    showError("Please enter a room code.");
    return;
  }

  joinBtn.disabled = true;
  try {
    const room = await postJson("/rooms/join", { room_code: code, player_name: name });
    const me = room.players[room.players.length - 1];
    goToLobby(room.code, me.id);
  } catch (err) {
    showError(err.message);
    joinBtn.disabled = false;
  }
});

nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createBtn.click();
});
codeInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") joinBtn.click();
});