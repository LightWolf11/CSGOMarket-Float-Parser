import axios from "axios";

export async function exportIndex(currency) {
  const url = `https://market.csgo.com/api/full-export/${currency.toUpperCase()}.json`;
  const r = await axios.get(url);
  if (!r.data?.success) throw new Error("full-export index failed");
  return r.data;
}

export async function exportFile(fileName) {
  const url = `https://market.csgo.com/api/full-export/${fileName}`;
  const r = await axios.get(url);
  return r.data;
}

export function parseMarketHashNameFromUrl(url) {
  const u = new URL(url);
  return decodeURIComponent(u.pathname.split("/").pop() || "");
}

export function buildIdx(format) {
  const m = new Map();
  for (let i = 0; i < format.length; i++) m.set(String(format[i]).toLowerCase(), i);
  return m;
}

function getField(row, idx, ...names) {
  for (const n of names) {
    const i = idx.get(n);
    if (i != null) return row[i];
  }
  return undefined;
}

export function parseLot(row, idx) {
  return {
    id: getField(row, idx, "id"),
    asset: getField(row, idx, "asset"),
    price: getField(row, idx, "price"),
    oldprice: getField(row, idx, "oldprice"),
    stamp: getField(row, idx, "stamp"),
    baseid: getField(row, idx, "baseid", "base_id"),
    markethashname: getField(row, idx, "markethashname", "market_hash_name"),
    float: getField(row, idx, "float")
  };
}
