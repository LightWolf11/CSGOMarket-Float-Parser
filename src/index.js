import "dotenv/config";
import { store } from "./store.js";
import { tg } from "./telegram.js";
import { exportIndex, exportFile, parseMarketHashNameFromUrl, buildIdx, parseLot } from "./marketExport.js";

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const CURRENCY = (process.env.CURRENCY || "rub").toLowerCase();

const SCAN_INTERVAL_SEC = Number(process.env.SCAN_INTERVAL_SEC || "3");
const FILES_PER_SCAN = Number(process.env.FILES_PER_SCAN || "30");
const DOWNLOAD_CONCURRENCY = Number(process.env.DOWNLOAD_CONCURRENCY || "8");
const INDEX_CACHE_SEC = Number(process.env.INDEX_CACHE_SEC || "120");
const MAX_RESULTS_PER_SCAN = Number(process.env.MAX_RESULTS_PER_SCAN || "500");

const BATCH_SIZE = Number(process.env.BATCH_SIZE || "10");
const BATCH_MIN_SEND = Number(process.env.BATCH_MIN_SEND || "3");
const BATCH_MAX_WAIT_SEC = Number(process.env.BATCH_MAX_WAIT_SEC || "40");

const PAGE_SIZE = 10;

if (!BOT_TOKEN) {
  console.error("No TELEGRAM_BOT_TOKEN in .env");
  process.exit(1);
}

const bot = tg(BOT_TOKEN);

// ---------- helpers ----------
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

function parseRubToCents(s) {
  if (s == null) return null;
  const cleaned = String(s).trim().replace(/\s+/g, "").replace(",", ".");
  if (!cleaned) return null;
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return Math.round(n * 100);
}

function formatRubFromCents(cents) {
  const n = Number(cents);
  if (!Number.isFinite(n)) return String(cents ?? "");
  return new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n / 100);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function lotKey(lot) {
  return String(lot.id ?? lot.asset ?? `${lot.markethashname}:${lot.float}:${lot.price}`);
}

function lotUrl(lot, track) {
  const id = lot.id ?? lot.asset;
  if (!id) return null;
  if (!track?.baseUrl) return null;
  try {
    const u = new URL(track.baseUrl);
    u.searchParams.set("id", String(id));
    return u.toString();
  } catch {
    return null;
  }
}

function match(lot, t) {
  if (t.paused) return false;

  if (!lot.markethashname) return false;
  if (lot.markethashname !== t.market_hash_name) return false;

  const f = num(lot.float);
  if (f == null) return false;
  if (f < t.minFloat || f > t.maxFloat) return false;

  const p = num(lot.price);
  if (p == null) return false;

  if (t.minPrice != null && p < t.minPrice) return false;
  if (t.maxPrice != null && p > t.maxPrice) return false;

  return true;
}

async function sendToChat(chatId, text, replyMarkup = null, parseMode = null) {
  await bot.sendMessage(chatId, text, replyMarkup, parseMode);
}

// ---------- batching (in-memory) ----------
const batches = new Map(); // `${chatId}:${trackId}` -> { items: [], firstAt }
function bk(chatId, trackId) { return `${chatId}:${trackId}`; }

function pushToBatch(chatId, track, lot) {
  const key = bk(chatId, track.id);
  let b = batches.get(key);
  if (!b) { b = { items: [], firstAt: Date.now() }; batches.set(key, b); }

  b.items.push({
    markethashname: lot.markethashname,
    float: lot.float,
    price: Number(lot.price),
    url: lotUrl(lot, track),
    at: Date.now()
  });
}

async function flushBatch(chatId, trackId, reason) {
  const key = bk(chatId, trackId);
  const b = batches.get(key);
  if (!b) return;

  const items = b.items;
  if (!items.length) { batches.delete(key); return; }
  if (items.length < BATCH_MIN_SEND && reason !== "force") return;

  items.sort((a, b) => (a.price ?? 0) - (b.price ?? 0));

  while (items.length >= BATCH_MIN_SEND) {
    const chunk = items.splice(0, BATCH_SIZE);

    const lines = chunk.map((x, i) => {
      const n = i + 1;
      const name = escapeHtml(x.markethashname);
      const f = escapeHtml(x.float);
      const p = escapeHtml(formatRubFromCents(x.price));
      const link = x.url ? `<a href="${escapeHtml(x.url)}">открыть</a>` : `нет ссылки`;
      return `${n}. ${name}\nfloat: ${f}\nprice: ${p} ${CURRENCY.toUpperCase()} | ${link}`;
    });

    await sendToChat(chatId, lines.join("\n\n"), null, "HTML");
  }

  if (items.length === 0) batches.delete(key);
  else b.items = items;
}

function flushByTimeoutTick() {
  const now = Date.now();
  for (const [key, b] of batches.entries()) {
    const ageSec = (now - b.firstAt) / 1000;
    if (ageSec >= BATCH_MAX_WAIT_SEC) {
      const [chatId, trackId] = key.split(":");
      flushBatch(Number(chatId), trackId, "timeout").catch(() => {});
    }
  }
}

// ---------- found paging/sort + confirm clear ----------
const foundSortPref = new Map(); // `${chatId}:${trackId}` -> "price" | "float"
function fk(chatId, trackId) { return `${chatId}:${trackId}`; }

function renderFoundPage(chatId, trackId, page) {
  const itemsRaw = store.getFound(chatId, trackId) || [];
  const sortMode = foundSortPref.get(fk(chatId, trackId)) || "price";

  const items = itemsRaw.slice();
  if (sortMode === "float") items.sort((a, b) => (Number(a.float) || 0) - (Number(b.float) || 0));
  else items.sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0));

  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const p = Math.min(Math.max(1, page), totalPages);

  const start = (p - 1) * PAGE_SIZE;
  const chunk = items.slice(start, start + PAGE_SIZE);

  const lines = chunk.map((x, i) => {
    const n = start + i + 1;
    const name = escapeHtml(x.markethashname);
    const f = escapeHtml(x.float);
    const price = escapeHtml(formatRubFromCents(x.price));
    const link = x.url ? `<a href="${escapeHtml(x.url)}">открыть</a>` : `нет ссылки`;
    return `${n}. ${name}\nfloat: ${f}\nprice: ${price} ${CURRENCY.toUpperCase()} | ${link}`;
  });

  const headerSort = sortMode === "float" ? "Float" : "Цена";

  const text =
    `Найденные (track ${trackId})\n` +
    `Сортировка: ${headerSort} | Всего: ${items.length} | Страница: ${p}/${totalPages}\n\n` +
    (lines.length ? lines.join("\n\n") : "Пока пусто");

  const kb = {
    inline_keyboard: [
      [
        { text: sortMode === "price" ? "✅ Цена" : "Цена", callback_data: `fs:${trackId}:price:${p}` },
        { text: sortMode === "float" ? "✅ Float" : "Float", callback_data: `fs:${trackId}:float:${p}` }
      ],
      [
        { text: "◀", callback_data: `fp:${trackId}:${p - 1}` },
        { text: `${p}/${totalPages}`, callback_data: "noop" },
        { text: "▶", callback_data: `fp:${trackId}:${p + 1}` }
      ],
      [
        { text: "🧹 Очистить", callback_data: `fca:${trackId}:${p}` }
      ]
    ]
  };

  return { text, kb };
}

function renderClearConfirm(trackId, backPage) {
  const text =
    `Точно очистить найденные по track ${trackId}?\n` +
    `Будут удалены found и sent (бот сможет снова присылать те же лоты).`;

  const kb = {
    inline_keyboard: [[
      { text: "✅ Да, очистить", callback_data: `fcc:${trackId}:${backPage}` },
      { text: "❌ Нет", callback_data: `fp:${trackId}:${backPage}` }
    ]]
  };

  return { text, kb };
}

// ---------- list menu ----------
function renderListMenu(chatId, page) {
  const tracks = store.listTracks(chatId);
  if (!tracks.length) {
    return { text: "Список пуст. Добавь трек через /track ...", kb: null };
  }

  const totalPages = Math.max(1, Math.ceil(tracks.length / 10));
  const p = Math.min(Math.max(1, page), totalPages);

  const start = (p - 1) * 10;
  const chunk = tracks.slice(start, start + 10);

  const rows = chunk.map(t => ([
    { text: t.market_hash_name || `track ${t.id}`, callback_data: `ls:${t.id}:1` }
  ]));

  rows.push([
    { text: "◀", callback_data: `lp:${p - 1}` },
    { text: `${p}/${totalPages}`, callback_data: "noop" },
    { text: "▶", callback_data: `lp:${p + 1}` }
  ]);

  return { text: "Выбери трек для просмотра found:", kb: { inline_keyboard: rows } };
}

// ---------- Telegram updates ----------
let offset = 0;

function tracksKeyboardForList(tracks) {
  return {
    inline_keyboard: tracks.slice(0, 20).map(t => ([
      { text: t.paused ? `▶ ${t.id}` : `⏸ ${t.id}`, callback_data: `toggle:${t.id}` },
      { text: `🗑 ${t.id}`, callback_data: `del:${t.id}` }
    ]))
  };
}

async function handleMessage(chatId, text) {
  store.addChat(chatId);

  if (text.startsWith("/start")) {
    await sendToChat(
      chatId,
      "Команды:\n" +
      "/track <url> <min_float> <max_float> [min_price_rub] [max_price_rub]\n" +
      "/tracks\n" +
      "/untrack <id>\n" +
      "/found <trackId>\n" +
      "/list"
    );
    return;
  }

  if (text.startsWith("/tracks")) {
    const tracks = store.listTracks(chatId);
    if (!tracks.length) { await sendToChat(chatId, "Список пуст"); return; }

    const out = tracks.map(t => {
      const state = t.paused ? "⏸ paused" : "▶ active";
      const pricePart =
        (t.minPrice != null || t.maxPrice != null)
          ? `, price: ${t.minPrice == null ? "-" : formatRubFromCents(t.minPrice)}..${t.maxPrice == null ? "-" : formatRubFromCents(t.maxPrice)}`
          : "";
      return `#${t.id} ${state}\n${t.market_hash_name}\nfloat: ${t.minFloat}..${t.maxFloat}${pricePart}`;
    }).join("\n\n");

    await sendToChat(chatId, out, tracksKeyboardForList(tracks));
    return;
  }

  if (text.startsWith("/list")) {
    const { text: menuText, kb } = renderListMenu(chatId, 1);
    await sendToChat(chatId, menuText, kb);
    return;
  }

  if (text.startsWith("/found")) {
    const trackId = text.split(" ")[1];
    if (!trackId) { await sendToChat(chatId, "Формат: /found <trackId>"); return; }
    if (!foundSortPref.has(fk(chatId, trackId))) foundSortPref.set(fk(chatId, trackId), "price");
    const { text: pageText, kb } = renderFoundPage(chatId, trackId, 1);
    await sendToChat(chatId, pageText, kb, "HTML");
    return;
  }

  if (text.startsWith("/untrack")) {
    const id = text.split(" ")[1];
    if (!id) { await sendToChat(chatId, "Формат: /untrack <id>"); return; }
    store.removeTrack(chatId, id);
    await sendToChat(chatId, `Удалено: ${id}`);
    return;
  }

  if (text.startsWith("/track")) {
    const parts = text.split(" ");
    const url = parts[1];
    const minS = parts[2];
    const maxS = parts[3];
    const minPS = parts[4];
    const maxPS = parts[5];

    if (!url || !minS || !maxS) {
      await sendToChat(chatId, "Формат: /track <url> <min_float> <max_float> [min_price_rub] [max_price_rub]");
      return;
    }

    const minFloat = num(minS);
    const maxFloat = num(maxS);
    if (minFloat == null || maxFloat == null || minFloat >= maxFloat) {
      await sendToChat(chatId, "Неверный float диапазон. Пример: 0.15 0.18");
      return;
    }

    const minPrice = minPS != null ? parseRubToCents(minPS) : null;
    const maxPrice = maxPS != null ? parseRubToCents(maxPS) : null;

    if (minPS != null && minPrice == null) { await sendToChat(chatId, "Не понял min_price. Пример: 3500 или 3500,50"); return; }
    if (maxPS != null && maxPrice == null) { await sendToChat(chatId, "Не понял max_price. Пример: 5000 или 5000,50"); return; }
    if ((minPrice != null && maxPrice != null) && minPrice > maxPrice) {
      await sendToChat(chatId, "Неверный price диапазон: min_price должен быть <= max_price");
      return;
    }

    const baseUrl = url;
    const market_hash_name = parseMarketHashNameFromUrl(url);
    const id = store.addTrack(chatId, { baseUrl, market_hash_name, minFloat, maxFloat, minPrice, maxPrice });

    const total = store.listTracks(chatId).length;
    await sendToChat(
      chatId,
      `Добавлено ${id}\n${market_hash_name}\nfloat: ${minFloat}-${maxFloat}\nprice: ${minPrice == null ? "-" : formatRubFromCents(minPrice)}..${maxPrice == null ? "-" : formatRubFromCents(maxPrice)}\nТреков в этом чате: ${total}\nОткрыть найденные: /found ${id}`
    );
    return;
  }
}

async function handleCallback(chatId, messageId, data) {
  store.addChat(chatId);
  if (!data || data === "noop") return;

  if (data.startsWith("toggle:")) {
    const id = data.split(":")[1];
    const tracks = store.listTracks(chatId);
    const t = tracks.find(x => x.id === String(id));
    if (!t) return;
    store.updateTrack(chatId, id, { paused: !t.paused });
    await sendToChat(chatId, `Ок: ${id} теперь ${t.paused ? "активен" : "на паузе"}`);
    return;
  }

  if (data.startsWith("del:")) {
    const id = data.split(":")[1];
    store.removeTrack(chatId, id);
    await sendToChat(chatId, `Удалено: ${id}`);
    return;
  }

  // list menu pagination
  if (data.startsWith("lp:")) {
    const page = Number(data.split(":")[1]) || 1;
    const { text, kb } = renderListMenu(chatId, page);
    await bot.editMessageText(chatId, messageId, text, kb, null);
    return;
  }

  // choose track from /list -> open found
  if (data.startsWith("ls:")) {
    const [, trackId, pageStr] = data.split(":");
    const page = Number(pageStr) || 1;
    if (!foundSortPref.has(fk(chatId, trackId))) foundSortPref.set(fk(chatId, trackId), "price");
    const { text, kb } = renderFoundPage(chatId, trackId, page);
    await bot.editMessageText(chatId, messageId, text, kb, "HTML");
    return;
  }

  if (data.startsWith("fp:")) {
    const [, trackId, pageStr] = data.split(":");
    const page = Number(pageStr) || 1;
    const { text, kb } = renderFoundPage(chatId, trackId, page);
    await bot.editMessageText(chatId, messageId, text, kb, "HTML");
    return;
  }

  if (data.startsWith("fs:")) {
    const [, trackId, mode, pageStr] = data.split(":");
    if (mode !== "price" && mode !== "float") return;
    foundSortPref.set(fk(chatId, trackId), mode);
    const page = Number(pageStr) || 1;
    const { text, kb } = renderFoundPage(chatId, trackId, page);
    await bot.editMessageText(chatId, messageId, text, kb, "HTML");
    return;
  }

  // ask confirm clear
  if (data.startsWith("fca:")) {
    const [, trackId, pageStr] = data.split(":");
    const backPage = Number(pageStr) || 1;
    const { text, kb } = renderClearConfirm(trackId, backPage);
    await bot.editMessageText(chatId, messageId, text, kb, null);
    return;
  }

  // confirm clear (clear found + sent)
  if (data.startsWith("fcc:")) {
    const [, trackId] = data.split(":");
    store.clearTrackState(chatId, trackId);
    const { text, kb } = renderFoundPage(chatId, trackId, 1);
    await bot.editMessageText(chatId, messageId, text, kb, "HTML");
    return;
  }
}

async function pollUpdatesLoop() {
  while (true) {
    try {
      const r = await bot.getUpdates(offset);
      if (r.data?.ok) {
        for (const upd of r.data.result) {
          offset = upd.update_id + 1;

          const msg = upd.message;
          if (msg?.text && msg?.chat?.id) {
            await handleMessage(msg.chat.id, msg.text);
            continue;
          }

          const cq = upd.callback_query;
          if (cq?.data && cq?.message?.chat?.id && cq?.message?.message_id) {
            await handleCallback(cq.message.chat.id, cq.message.message_id, cq.data);
            continue;
          }
        }
      }
    } catch (e) {
      console.error("getUpdates error:", e?.message || e);
      await new Promise(res => setTimeout(res, 2000));
    }
  }
}

// ---------- scanner ----------
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function fetchWithRetry(fn, tries = 4) {
  let delay = 250;
  for (let i = 0; i < tries; i++) {
    try {
      return await fn();
    } catch (e) {
      const status = e?.response?.status;
      if (status === 429 || status === 403) {
        await sleep(delay);
        delay *= 2;
        continue;
      }
      throw e;
    }
  }
  throw new Error("Too many retries");
}

async function asyncPool(limit, items, worker) {
  const executing = new Set();
  const results = [];
  for (const item of items) {
    const p = Promise.resolve().then(() => worker(item));
    results.push(p);
    executing.add(p);
    const clean = () => executing.delete(p);
    p.then(clean).catch(clean);
    if (executing.size >= limit) await Promise.race(executing);
  }
  return Promise.allSettled(results);
}

let cachedIndex = null;
let cachedIndexAt = 0;
let cachedIdxMap = null;
let cachedFormatSig = null;

async function getIndexCached() {
  const now = Date.now();
  if (cachedIndex && (now - cachedIndexAt) < INDEX_CACHE_SEC * 1000) return cachedIndex;
  const idx = await fetchWithRetry(() => exportIndex(CURRENCY));
  cachedIndex = idx;
  cachedIndexAt = now;
  return idx;
}

function getIdxMapFromIndex(idxFile) {
  const sig = JSON.stringify(idxFile.format);
  if (cachedIdxMap && cachedFormatSig === sig) return cachedIdxMap;
  cachedIdxMap = buildIdx(idxFile.format);
  cachedFormatSig = sig;
  return cachedIdxMap;
}

let scanning = false;

async function scanOnce() {
  if (scanning) return;
  scanning = true;

  try {
    const idxFile = await getIndexCached();
    const idx = getIdxMapFromIndex(idxFile);
    const files = idxFile.items;
    if (!Array.isArray(files) || !files.length) return;

    for (const chatId of store.listChats()) {
      const tracks = store.listTracks(chatId);
      if (!tracks.length) continue;

      const cursor = store.getCursor(chatId);
      const batch = [];
      for (let i = 0; i < Math.min(FILES_PER_SCAN, files.length); i++) {
        batch.push(files[(cursor + i) % files.length]);
      }
      store.setCursor(chatId, (cursor + batch.length) % files.length);

      const settled = await asyncPool(DOWNLOAD_CONCURRENCY, batch, async (file) => {
        const rows = await fetchWithRetry(() => exportFile(file));
        return rows;
      });

      let matchedNow = 0;

      for (const s of settled) {
        if (s.status !== "fulfilled") continue;
        const rows = s.value;
        if (!Array.isArray(rows)) continue;

        for (const row of rows) {
          const lot = parseLot(row, idx);

          for (const t of tracks) {
            if (!match(lot, t)) continue;

            const key = lotKey(lot);
            if (store.wasSent(chatId, t.id, key)) continue;
            store.markSent(chatId, t.id, key);

            pushToBatch(chatId, t, lot);

            store.addFound(chatId, t.id, {
              markethashname: lot.markethashname,
              float: lot.float,
              price: Number(lot.price),
              url: lotUrl(lot, t),
              at: Date.now()
            });

            matchedNow += 1;
            if (matchedNow >= MAX_RESULTS_PER_SCAN) break;
          }

          if (matchedNow >= MAX_RESULTS_PER_SCAN) break;
        }

        if (matchedNow >= MAX_RESULTS_PER_SCAN) break;
      }

      for (const t of tracks) {
        await flushBatch(chatId, t.id, "scan");
      }
    }
  } catch (e) {
    console.error("scan error:", e?.message || e);
  } finally {
    scanning = false;
  }
}

// ---------- start ----------
(async () => {
  console.log("Bot started. Currency:", CURRENCY);
  setInterval(() => scanOnce().catch(() => {}), SCAN_INTERVAL_SEC * 1000);
  setInterval(() => flushByTimeoutTick(), 1000);
  await pollUpdatesLoop();
})();
