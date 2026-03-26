import fs from "node:fs";

const PATH = "./data.json";

function normalize(d) {
  if (!d || typeof d !== "object") d = {};
  if (!Array.isArray(d.chats)) d.chats = [];
  if (typeof d.byChat !== "object" || d.byChat == null) d.byChat = {};
  return d;
}

function ensureChat(d, chatId) {
  const key = String(chatId);
  if (!d.byChat[key] || typeof d.byChat[key] !== "object") {
    d.byChat[key] = { tracks: [], cursor: 0 };
  }
  if (!Array.isArray(d.byChat[key].tracks)) d.byChat[key].tracks = [];
  if (!Number.isFinite(d.byChat[key].cursor)) d.byChat[key].cursor = 0;

  d.byChat[key].tracks = d.byChat[key].tracks.map(t => ({
    id: t.id ?? String(Date.now()),
    baseUrl: typeof t.baseUrl === "string" ? t.baseUrl : "",
    market_hash_name: t.market_hash_name ?? "",
    minFloat: Number(t.minFloat ?? 0),
    maxFloat: Number(t.maxFloat ?? 1),
    minPrice: t.minPrice ?? null,
    maxPrice: t.maxPrice ?? null,
    paused: Boolean(t.paused ?? false),
    createdAt: t.createdAt ?? Date.now(),
    sent: Array.isArray(t.sent) ? t.sent : [],
    found: Array.isArray(t.found) ? t.found : []
  }));

  for (const t of d.byChat[key].tracks) {
    if (t.sent.length > 50000) t.sent = t.sent.slice(-50000);
    if (t.found.length > 500) t.found = t.found.slice(-500);
  }

  return d.byChat[key];
}

function load() {
  try {
    if (!fs.existsSync(PATH)) return normalize({});
    return normalize(JSON.parse(fs.readFileSync(PATH, "utf8")));
  } catch {
    return normalize({});
  }
}

function save(d) {
  fs.writeFileSync(PATH, JSON.stringify(d, null, 2));
}

function findTrack(chat, trackId) {
  return chat.tracks.find(t => t.id === String(trackId));
}

export const store = {
  addChat(chatId) {
    const d = load();
    if (!d.chats.includes(chatId)) d.chats.push(chatId);
    ensureChat(d, chatId);
    save(d);
  },

  listChats() {
    return load().chats;
  },

  listTracks(chatId) {
    const d = load();
    const c = ensureChat(d, chatId);
    save(d);
    return c.tracks;
  },

  addTrack(chatId, track) {
    const d = load();
    const c = ensureChat(d, chatId);

    const id = String(Date.now());
    c.tracks.push({
      id,
      baseUrl: track.baseUrl,
      market_hash_name: track.market_hash_name,
      minFloat: track.minFloat,
      maxFloat: track.maxFloat,
      minPrice: track.minPrice ?? null,
      maxPrice: track.maxPrice ?? null,
      paused: false,
      createdAt: Date.now(),
      sent: [],
      found: []
    });

    save(d);
    return id;
  },

  updateTrack(chatId, trackId, patch) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    if (!t) return false;
    Object.assign(t, patch);
    save(d);
    return true;
  },

  removeTrack(chatId, trackId) {
    const d = load();
    const c = ensureChat(d, chatId);
    c.tracks = c.tracks.filter(t => t.id !== String(trackId)); // вместе с found/sent
    save(d);
  },

  getCursor(chatId) {
    const d = load();
    const c = ensureChat(d, chatId);
    save(d);
    return c.cursor;
  },

  setCursor(chatId, v) {
    const d = load();
    const c = ensureChat(d, chatId);
    c.cursor = v;
    save(d);
  },

  wasSent(chatId, trackId, lotKey) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    if (!t) { save(d); return false; }
    const ok = t.sent.includes(String(lotKey));
    save(d);
    return ok;
  },

  markSent(chatId, trackId, lotKey) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    if (!t) { save(d); return; }

    t.sent.push(String(lotKey));
    if (t.sent.length > 50000) t.sent = t.sent.slice(-50000);
    save(d);
  },

  addFound(chatId, trackId, item) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    if (!t) { save(d); return; }

    t.found.push(item);
    if (t.found.length > 500) t.found = t.found.slice(-500);
    save(d);
  },

  getFound(chatId, trackId) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    const res = t?.found ?? [];
    save(d);
    return res;
  },

  clearTrackState(chatId, trackId) {
    const d = load();
    const c = ensureChat(d, chatId);
    const t = findTrack(c, trackId);
    if (t) {
      t.found = [];
      t.sent = [];
    }
    save(d);
  }
};
