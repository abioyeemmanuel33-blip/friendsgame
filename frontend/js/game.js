// game.js — Step 2.2: tile-based track with three routes.
//
// Map layout is a string array. Each character is one tile:
//   #  wall (you cannot walk here)
//   .  road (walkable)
//   S  start (where players spawn)
//   F  finish (goal)
//
// The map is 20 cols wide and 20 rows tall.
// Tiles are 40x40 pixels, so the canvas is 800x800.
//
// Movement is TILE-BASED:
//   - arrow keys move exactly one tile at a time
//   - the target tile must not be a wall
//   - one keydown = one tile move (no holding-to-glide)
//
// This is Step 2.2. Server sync comes in Step 2.3.

// ---------- map definition ----------

const MAP = [
  "####################",   // row 0
  "#S.S.S.S.S.S.S.S.S.#",   // row 1  ← start strip (S marks each spawn column)
  "#..................#",   // row 2
  "#.###.######.#####.#",   // row 3  ← route A wall | route B open | route C open
  "#.#...#....#.#...#.#",   // row 4
  "#.#.#.#.####.#.#.#.#",   // row 5
  "#.#.#.#......#.#.#.#",   // row 6
  "#.#.#.######.#.#.#.#",   // row 7
  "#.#.#........#.#.#.#",   // row 8
  "#.#.########.#.#.#.#",   // row 9
  "#.#..........#.#.#.#",   // row 10
  "#.#.########.#.#.#.#",   // row 11
  "#.#..........#.#.#.#",   // row 12
  "#.#.########.#.#.#.#",   // row 13
  "#.#..........#.#.#.#",   // row 14
  "#.#.########.#.#.#.#",   // row 15
  "#.#..........#.#.#.#",   // row 16
  "#.###.######.#####.#",   // row 17
  "#..................#",   // row 18
  "#########F##########",   // row 19 ← finish
];

const TILE_SIZE = 40;
const COLS = MAP[0].length;      // 20
const ROWS = MAP.length;         // 20

// ---------- canvas ----------

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const WIDTH = canvas.width;
const HEIGHT = canvas.height;

// ---------- player ----------

// Player position in TILE coordinates (not pixels).
const player = {
  row: 1,             // on the start row
  col: 2,             // first S cell in the start strip (see MAP row 1)
  color: "#5b7cfa",
};

// ---------- room code from URL (unchanged) ----------

const params = new URLSearchParams(window.location.search);
const roomCode = params.get("code");
const playerId = params.get("player");
document.getElementById("roomCode").textContent = roomCode || "—";

// ---------- input ----------

// One keydown = one tile move. We ignore auto-repeat by checking e.repeat.
window.addEventListener("keydown", (e) => {
  if (e.repeat) return;      // ignore held-down repeat

  const key = e.key.toLowerCase();

  if (key === "arrowup" || key === "w")    { e.preventDefault(); tryMove(-1, 0); }
  if (key === "arrowdown" || key === "s")  { e.preventDefault(); tryMove(1, 0); }
  if (key === "arrowleft" || key === "a")  { e.preventDefault(); tryMove(0, -1); }
  if (key === "arrowright" || key === "d") { e.preventDefault(); tryMove(0, 1); }
});

function tryMove(rowDelta, colDelta) {
  const newRow = player.row + rowDelta;
  const newCol = player.col + colDelta;

  // Out of bounds?
  if (newRow < 0 || newRow >= ROWS || newCol < 0 || newCol >= COLS) return;

  // Wall?
  if (MAP[newRow][newCol] === "#") return;

  player.row = newRow;
  player.col = newCol;

  // Debug log so you can watch your coordinates change.
  console.log(`player -> row=${player.row} col=${player.col}`);
}

// ---------- drawing ----------

function tileColor(char) {
  switch (char) {
    case "#": return "#1a1d26";   // wall — darker than road
    case ".": return "#2a2f40";   // road
    case "S": return "#3a4a6a";   // start (bluish)
    case "F": return "#3ddc84";   // finish (green)
    default:  return "#000000";   // unknown — should never happen
  }
}

function drawMap() {
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const ch = MAP[row][col];
      ctx.fillStyle = tileColor(ch);

      const x = col * TILE_SIZE;
      const y = row * TILE_SIZE;
      ctx.fillRect(x, y, TILE_SIZE, TILE_SIZE);

      // Draw a faint border between tiles.
      ctx.strokeStyle = "#0f1116";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);

      // Label the start and finish cells.
      if (ch === "F") {
        ctx.fillStyle = "#0f1116";
        ctx.font = "bold 20px system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("F", x + TILE_SIZE / 2, y + TILE_SIZE / 2);
      }
    }
  }
}

function drawPlayer() {
  const x = player.col * TILE_SIZE;
  const y = player.row * TILE_SIZE;

  // Main body
  ctx.fillStyle = player.color;
  ctx.fillRect(x + 4, y + 4, TILE_SIZE - 8, TILE_SIZE - 8);

  // Highlight
  ctx.fillStyle = "rgba(255,255,255,0.2)";
  ctx.fillRect(x + 4, y + 4, TILE_SIZE - 8, 6);
}

function draw() {
  // No need to clear — we paint every tile each frame.
  drawMap();
  drawPlayer();
}

// ---------- render ----------

draw();   // draw once; redraw after each move

// Wrap draw into a tiny helper the input code can call.
// (Kept simple for now — the loop version comes back when we have animated things.)

const originalTryMove = tryMove;
// override reference: reassign by redefining tryMove to redraw
// Simple approach: just call draw inside tryMove.
// To avoid rewriting the whole file, monkey-patch here:

// NOTE: In Step 2.3 we'll restore a proper requestAnimationFrame loop.
// For 2.2 the only thing that changes is player.row/col, so drawing
// on input is enough.
(function hookDraw() {
  const orig = tryMove;
  // eslint-disable-next-line no-func-assign
  tryMove = function (r, c) {
    orig(r, c);
    draw();
  };
})();

// ---------- back button ----------

document.getElementById("backBtn").addEventListener("click", () => {
  window.location.href = `/lobby.html?code=${encodeURIComponent(roomCode)}&player=${encodeURIComponent(playerId)}`;
});