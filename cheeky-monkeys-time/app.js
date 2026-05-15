/**
 * Cheeky Monkeys — Telling the Time Game
 * Browser toy for ages ~4: o'clock, half past, daily stars, weekly parent view.
 */

const STORAGE_KEY = "cheekyMonkeysTime_v1";

const STAR_TASKS = [
  { id: "played", label: "Play any game today", emoji: "🎮" },
  { id: "three_correct", label: "Get 3 cheeky answers right", emoji: "✅" },
  { id: "two_set", label: "Set the clock right twice", emoji: "🚜" },
  { id: "daily_challenge", label: "Beat today’s Animal Challenge", emoji: "🐵" },
];

const ANIMAL_QUIPS = [
  { emoji: "🐔", text: "Clucky says: when the short hand points at me, it’s snack o’clock!" },
  { emoji: "🐄", text: "Cowbert moos: half past means the long hand sits on the 6 — moo-gnificent!" },
  { emoji: "🚜", text: "Tractor Ted never runs late for hay — can you match his o’clock?" },
  { emoji: "🐑", text: "Woolly wonders: we count round the clock like hopping round the field!" },
  { emoji: "🐷", text: "Piglet Pete snorts: o’clock is when the short hand hugs a number!" },
  { emoji: "🚂", text: "Choo-Choo Charlie says: tick-tock, the blue hand is the boss for o’clock!" },
  { emoji: "🐵", text: "Cheeky Monkey banana rule: short hand = the o’clock number. Easy-peasy!" },
  { emoji: "🦆", text: "Daisy Duck waddles in: at half past, the red hand points down to her pond (the 6)!" },
];

const HOUR_WORDS = [
  "twelve", "one", "two", "three", "four", "five", "six",
  "seven", "eight", "nine", "ten", "eleven",
];

const state = {
  game: null,
  mode: "oclock", // oclock | half
  targetHour: 3,
  targetHalf: false,
  sessionCorrect: 0,
  dragging: false,
  soundOn: true,
  clockHour: 12,
  clockMinute: 0,
  interactive: true,
};

// ——— Storage ———

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function loadStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : { days: {} };
  } catch {
    return { days: {} };
  }
}

function saveStore(store) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function getDayData(date = todayKey()) {
  const store = loadStore();
  if (!store.days[date]) {
    store.days[date] = {
      stars: [],
      stats: { correct: 0, setWins: 0, games: 0 },
    };
  }
  saveStore(store);
  return store.days[date];
}

function updateDay(mutator) {
  const store = loadStore();
  const key = todayKey();
  if (!store.days[key]) {
    store.days[key] = { stars: [], stats: { correct: 0, setWins: 0, games: 0 } };
  }
  mutator(store.days[key]);
  saveStore(store);
}

function hasStar(starId) {
  return getDayData().stars.includes(starId);
}

function awardStar(starId, message) {
  if (hasStar(starId)) return false;
  updateDay((day) => {
    if (!day.stars.includes(starId)) day.stars.push(starId);
  });
  showCelebration(message || "Star earned!");
  renderHome();
  return true;
}

function checkAutoStars() {
  const day = getDayData();
  if (day.stats.games >= 1) awardStar("played", "You played today — star!");
  if (day.stats.correct >= 3) awardStar("three_correct", "Three right answers — superstar!");
  if (day.stats.setWins >= 2) awardStar("two_set", "Two clock sets — Tractor Ted is proud!");
}

// ——— Daily challenge (stable per calendar day) ———

function dailyChallengeHour() {
  const d = new Date();
  return ((d.getDate() + d.getMonth() * 7) % 12) + 1;
}

function dailyChallengeHalf() {
  const d = new Date();
  return d.getDate() % 2 === 0;
}

function formatTimeLabel(hour, half) {
  const h = HOUR_WORDS[hour % 12];
  return half ? `half past ${h}` : `${h} o'clock`;
}

// ——— Week view (Mon–Sun of current week) ———

function weekDates() {
  const now = new Date();
  const day = now.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(now);
  monday.setHours(12, 0, 0, 0);
  monday.setDate(now.getDate() + mondayOffset);
  const dates = [];
  for (let i = 0; i < 7; i++) {
    const x = new Date(monday);
    x.setDate(monday.getDate() + i);
    dates.push(
      `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`
    );
  }
  return dates;
}

function starsForDate(dateKey) {
  const store = loadStore();
  return store.days[dateKey]?.stars?.length || 0;
}

// ——— DOM helpers ———

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showScreen(id) {
  $$(".screen").forEach((el) => el.classList.remove("active"));
  $(`#screen-${id}`).classList.add("active");
}

function randomQuip() {
  return ANIMAL_QUIPS[Math.floor(Math.random() * ANIMAL_QUIPS.length)];
}

function pickHour(exclude) {
  let h;
  do {
    h = Math.floor(Math.random() * 12) + 1;
  } while (h === exclude);
  return h;
}

// ——— Clock SVG ———

const CX = 160;
const CY = 160;

function initClockFace() {
  const g = $("#clock-numbers");
  g.innerHTML = "";
  for (let i = 1; i <= 12; i++) {
    const angle = ((i % 12) * 30 - 90) * (Math.PI / 180);
    const r = 118;
    const x = CX + r * Math.cos(angle);
    const y = CY + r * Math.sin(angle);
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", x);
    t.setAttribute("y", y);
    t.setAttribute("class", "clock-num");
    t.textContent = i;
    g.appendChild(t);
  }
}

function setClockHands(hour, minute, animate) {
  state.clockHour = hour;
  state.clockMinute = minute;
  const hourAngle = (hour % 12) * 30 + minute * 0.5 - 90;
  const minAngle = minute * 6 - 90;
  const hourRad = hourAngle * (Math.PI / 180);
  const minRad = minAngle * (Math.PI / 180);
  const hourLen = 65;
  const minLen = 105;

  const hx = CX + hourLen * Math.cos(hourRad);
  const hy = CY + hourLen * Math.sin(hourRad);
  const mx = CX + minLen * Math.cos(minRad);
  const my = CY + minLen * Math.sin(minRad);

  const hourEl = $("#hand-hour");
  const minEl = $("#hand-minute");
  const knob = $("#hand-knob");

  hourEl.setAttribute("x2", hx);
  hourEl.setAttribute("y2", hy);
  minEl.setAttribute("x2", mx);
  minEl.setAttribute("y2", my);
  knob.setAttribute("cx", hx);
  knob.setAttribute("cy", hy);

  if (animate) {
    [hourEl, minEl, knob].forEach((el) => {
      el.style.transition = "none";
      requestAnimationFrame(() => {
        el.style.transition = "";
      });
    });
  }
}

function hourFromAngle(angleDeg) {
  let a = ((angleDeg + 90) % 360 + 360) % 360;
  const hour = Math.round(a / 30) % 12;
  return hour === 0 ? 12 : hour;
}

function pointerAngle(clientX, clientY) {
  const svg = $("#clock-svg");
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM().inverse();
  const loc = pt.matrixTransform(ctm);
  const dx = loc.x - CX;
  const dy = loc.y - CY;
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

function setupClockDrag() {
  const knob = $("#hand-knob");
  const svg = $("#clock-svg");

  const onStart = (e) => {
    if (!state.interactive) return;
    e.preventDefault();
    state.dragging = true;
  };

  const onMove = (e) => {
    if (!state.dragging || !state.interactive) return;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const angle = pointerAngle(clientX, clientY);
    const hour = hourFromAngle(angle);
    const minute = state.mode === "half" ? 30 : 0;
    setClockHands(hour, minute);
  };

  const onEnd = () => {
    state.dragging = false;
  };

  knob.addEventListener("mousedown", onStart);
  knob.addEventListener("touchstart", onStart, { passive: false });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("touchmove", onMove, { passive: false });
  window.addEventListener("mouseup", onEnd);
  window.addEventListener("touchend", onEnd);
  svg.addEventListener("mousedown", (e) => {
    if (e.target === svg || e.target.classList.contains("clock-face")) {
      onStart(e);
      onMove(e);
    }
  });
}

// ——— Sound (simple beeps via Web Audio) ———

let audioCtx;

function beep(freq, duration) {
  if (!state.soundOn) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + duration);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch {
    /* ignore */
  }
}

function soundSuccess() {
  beep(523, 0.12);
  setTimeout(() => beep(659, 0.15), 100);
}

function soundOops() {
  beep(220, 0.2);
}

// ——— Confetti ———

function burstConfetti() {
  const canvas = $("#confetti");
  const ctx = canvas.getContext("2d");
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const pieces = Array.from({ length: 60 }, () => ({
    x: canvas.width / 2,
    y: canvas.height / 2,
    vx: (Math.random() - 0.5) * 14,
    vy: Math.random() * -12 - 4,
    color: ["#ffc107", "#7cb342", "#e53935", "#1e88e5", "#ff8f00"][Math.floor(Math.random() * 5)],
    size: 6 + Math.random() * 8,
    life: 80 + Math.random() * 40,
  }));

  let frame = 0;
  function tick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    pieces.forEach((p) => {
      if (p.life <= 0) return;
      alive = true;
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.35;
      p.life -= 1;
      ctx.fillStyle = p.color;
      ctx.fillRect(p.x, p.y, p.size, p.size);
    });
    frame++;
    if (alive && frame < 120) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  tick();
}

function showCelebration(text) {
  $("#celebration-text").textContent = text;
  $("#celebration").classList.remove("hidden");
  burstConfetti();
  soundSuccess();
  setTimeout(() => $("#celebration").classList.add("hidden"), 2200);
}

// ——— Games ———

function registerGamePlay() {
  updateDay((day) => {
    day.stats.games += 1;
  });
  checkAutoStars();
}

function registerCorrect(wasSetGame) {
  state.sessionCorrect += 1;
  $("#session-score").textContent = state.sessionCorrect;
  updateDay((day) => {
    day.stats.correct += 1;
    if (wasSetGame) day.stats.setWins += 1;
  });
  checkAutoStars();
}

function matchesTarget(hour, minute) {
  const h = hour % 12 || 12;
  const t = state.targetHour % 12 || 12;
  if (state.targetHalf) {
    return h === t && minute === 30;
  }
  return h === t && minute === 0;
}

function startGame(gameId) {
  state.game = gameId;
  state.sessionCorrect = 0;
  $("#session-score").textContent = "0";
  registerGamePlay();

  const quip = randomQuip();
  $("#play-quip").textContent = `${quip.emoji} ${quip.text}`;

  $("#btn-check").classList.add("hidden");
  $("#btn-next").classList.add("hidden");
  $("#choices-row").classList.add("hidden");
  $("#choices-row").innerHTML = "";

  if (gameId === "set" || gameId === "daily") {
    state.mode = gameId === "daily" && dailyChallengeHalf() ? "half" : gameId === "half" ? "half" : "oclock";
    if (gameId === "daily") {
      state.targetHour = dailyChallengeHour();
      state.targetHalf = dailyChallengeHalf();
    } else if (gameId === "half") {
      state.mode = "half";
      state.targetHour = pickHour();
      state.targetHalf = true;
    } else {
      state.mode = "oclock";
      state.targetHour = pickHour();
      state.targetHalf = false;
    }
    setupSetRound();
  } else if (gameId === "read") {
    state.mode = Math.random() > 0.65 ? "half" : "oclock";
    state.targetHour = pickHour();
    state.targetHalf = state.mode === "half";
    setupReadRound();
  } else if (gameId === "half") {
    state.mode = "half";
    state.targetHour = pickHour();
    state.targetHalf = true;
    setupSetRound();
  }

  showScreen("play");
}

function setupSetRound() {
  state.interactive = true;
  const titles = {
    set: "Set the Clock",
    half: "Half Past Moo",
    daily: "Daily Animal Challenge",
  };
  $("#play-title").textContent = titles[state.game] || "Set the Clock";
  $("#clock-hint").innerHTML =
    state.targetHalf
      ? "Drag the <strong>blue</strong> hand. Keep the <strong>red</strong> hand on the <strong>6</strong>!"
      : "Drag the <strong>blue</strong> short hand! Red hand stays at the top.";

  const wrongHour = pickHour(state.targetHour);
  setClockHands(wrongHour, state.targetHalf ? 30 : 0);
  $("#play-prompt").textContent = `Make it ${formatTimeLabel(state.targetHour, state.targetHalf)}!`;
  $("#btn-check").classList.remove("hidden");
}

function setupReadRound() {
  state.interactive = false;
  $("#play-title").textContent = "Barnyard Quiz";
  $("#clock-hint").textContent = "Look at both hands — pick the right time!";
  const minute = state.targetHalf ? 30 : 0;
  setClockHands(state.targetHour, minute);
  $("#play-prompt").textContent = "What time is it?";

  const correct = formatTimeLabel(state.targetHour, state.targetHalf);
  const wrong1 = formatTimeLabel(pickHour(state.targetHour), state.targetHalf);
  const wrong2 = formatTimeLabel(pickHour(state.targetHour), !state.targetHalf);
  let options = [correct, wrong1, wrong2].filter((v, i, a) => a.indexOf(v) === i);
  while (options.length < 3) {
    options.push(formatTimeLabel(pickHour(), !state.targetHalf));
    options = options.filter((v, i, a) => a.indexOf(v) === i);
  }
  options.sort(() => Math.random() - 0.5);

  const row = $("#choices-row");
  row.classList.remove("hidden");
  row.innerHTML = "";
  options.forEach((label) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-btn";
    btn.textContent = label;
    btn.addEventListener("click", () => onReadChoice(btn, label === correct));
    row.appendChild(btn);
  });
}

function onReadChoice(btn, correct) {
  $$(".choice-btn").forEach((b) => (b.disabled = true));
  if (correct) {
    btn.classList.add("correct");
    soundSuccess();
    registerCorrect(false);
    $("#play-prompt").textContent = "Moo-rvellous! That’s right!";
    maybeDailyStar();
    showNextButton();
  } else {
    btn.classList.add("wrong");
    soundOops();
    $("#play-prompt").textContent = "Nearly! The short hand tells the o’clock number.";
    setTimeout(showNextButton, 1200);
  }
}

function onCheckSet() {
  if (matchesTarget(state.clockHour, state.clockMinute)) {
    soundSuccess();
    registerCorrect(true);
    $("#play-prompt").textContent = "Cheeky brilliant! " + formatTimeLabel(state.targetHour, state.targetHalf);
    maybeDailyStar();
    showNextButton();
  } else {
    soundOops();
    $("#play-prompt").textContent = state.targetHalf
      ? "Oops! Short hand on the hour, red hand on the 6."
      : "Oops! Short hand on the number, red hand at the top.";
  }
}

function maybeDailyStar() {
  if (state.game === "daily") {
    awardStar("daily_challenge", "Animal Challenge beaten!");
  }
}

function showNextButton() {
  $("#btn-check").classList.add("hidden");
  $("#btn-next").classList.remove("hidden");
}

function nextRound() {
  $("#btn-next").classList.add("hidden");
  if (state.game === "read") {
    state.mode = Math.random() > 0.6 ? "half" : "oclock";
    state.targetHalf = state.mode === "half";
    state.targetHour = pickHour();
    setupReadRound();
  } else {
    if (state.game === "half" || (state.game === "daily" && dailyChallengeHalf())) {
      state.targetHalf = true;
      state.mode = "half";
    } else if (state.game !== "daily") {
      state.targetHalf = false;
      state.mode = "oclock";
    }
    state.targetHour = state.game === "daily" ? dailyChallengeHour() : pickHour();
    setupSetRound();
  }
}

// ——— UI render ———

function renderHome() {
  const quip = randomQuip();
  $("#home-quip").textContent = `${quip.emoji} ${quip.text}`;
  const day = getDayData();
  const earned = day.stars.length;
  $("#today-star-count").textContent = `${earned}/4`;

  const list = $("#star-tasks-list");
  list.innerHTML = "";
  STAR_TASKS.forEach((task) => {
    const li = document.createElement("li");
    if (day.stars.includes(task.id)) li.classList.add("done");
    li.innerHTML = `<span class="task-star">${day.stars.includes(task.id) ? "⭐" : "☆"}</span> ${task.emoji} ${task.label}`;
    list.appendChild(li);
  });

  const h = dailyChallengeHour();
  const half = dailyChallengeHalf();
  $("#daily-challenge-hint").textContent = `Today: set the clock to ${formatTimeLabel(h, half)}!`;

  if (earned === 4) {
    $("#home-greeting").textContent = "All four stars today! You cheeky superstar!";
    $("#home-monkey-mood").textContent = "🎉";
  } else {
    $("#home-greeting").textContent = "Pick a game and earn today’s stars!";
    $("#home-monkey-mood").textContent = "🐵";
  }
}

function renderWeek() {
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const dates = weekDates();
  const today = todayKey();
  const grid = $("#week-grid");
  grid.innerHTML = "";
  let total = 0;

  dates.forEach((dateKey, i) => {
    const count = starsForDate(dateKey);
    total += count;
    const cell = document.createElement("div");
    cell.className = "week-day" + (dateKey === today ? " today" : "");
    const stars = "⭐".repeat(count) + (count < 4 ? "☆".repeat(4 - count) : "");
    const parts = dateKey.split("-");
    cell.innerHTML = `
      <div class="day-name">${names[i]}</div>
      <div class="day-stars">${stars || "☆☆☆☆"}</div>
      <div class="day-num">${parts[2]}/${parts[1]}</div>
    `;
    grid.appendChild(cell);
  });

  $("#week-total").textContent = String(total);
}

function resetWeek() {
  if (!confirm("Reset star counts for this week? (Grown-ups only)")) return;
  const store = loadStore();
  weekDates().forEach((d) => delete store.days[d]);
  saveStore(store);
  renderWeek();
  renderHome();
}

// ——— Init ———

function bindEvents() {
  $$(".game-card").forEach((card) => {
    card.addEventListener("click", () => startGame(card.dataset.game));
  });
  $("#btn-back").addEventListener("click", () => {
    renderHome();
    showScreen("home");
  });
  $("#btn-back-grownups").addEventListener("click", () => {
    renderHome();
    showScreen("home");
  });
  $("#btn-grownups").addEventListener("click", () => {
    renderWeek();
    showScreen("grownups");
  });
  $("#btn-check").addEventListener("click", onCheckSet);
  $("#btn-next").addEventListener("click", nextRound);
  $("#btn-reset-week").addEventListener("click", resetWeek);
  $("#btn-sound").addEventListener("click", () => {
    state.soundOn = !state.soundOn;
    $("#btn-sound").textContent = state.soundOn ? "🔊" : "🔇";
  });
  $("#celebration").addEventListener("click", () => {
    $("#celebration").classList.add("hidden");
  });
}

function init() {
  initClockFace();
  setupClockDrag();
  bindEvents();
  renderHome();
  setClockHands(12, 0);
}

document.addEventListener("DOMContentLoaded", init);
