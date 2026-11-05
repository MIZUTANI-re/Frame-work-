// 探す画面の「文字をそろえる」「合い方の強さ」（見本 v2 の関数）。画面に触らない部品なので、node でも試せる。

// ※ 未習: 文字の正規化 — 比べる前に、全角/半角・大文字/小文字・ひらがな/カタカナの違いをそろえる
// 全角/半角・大文字/小文字・カタカナ/ひらがなをそろえる
export function normChar(ch) {
  let c = ch.normalize("NFKC").toLowerCase();
  const k = c.charCodeAt(0);
  if (c.length === 1 && k >= 0x30a1 && k <= 0x30f6) c = String.fromCharCode(k - 0x60);
  return c;
}
export const norm = (s) => Array.from(s).map(normChar).join("");

export const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// 合った所を <mark> で囲む（HTML に直した文字を返す）
export function highlight(text, q) {
  if (!q) return esc(text);
  const chars = Array.from(text);
  const n = chars.map(normChar);
  const nq = norm(q);
  const at = n.join("").indexOf(nq);
  if (at < 0 || n.some((c) => c.length !== 1)) return esc(text);
  const L = nq.length;
  return esc(chars.slice(0, at).join("")) + "<mark>" + esc(chars.slice(at, at + L).join("")) + "</mark>" + esc(chars.slice(at + L).join(""));
}

// 合い方の強さ：名前の頭 4 → 名前のどこか 3 → 別名・読み 2 → 説明・タグ・目的 1 → 合わない -1。空なら 0
export function score(f, q) {
  const nq = norm(q);
  if (!nq) return 0;
  if (norm(f.name).startsWith(nq)) return 4;
  if (norm(f.name).includes(nq)) return 3;
  if ([...f.aliases, ...(f.yomi || [])].some((a) => norm(a).includes(nq))) return 2;
  const rest = [f.description, f.purpose_label, f.thinking_label, ...f.tags].map(norm).join(" ");
  return rest.includes(nq) ? 1 : -1;
}

// 候補を絞って並べる。空ならよく使われている順（同じ回数は元の順）、文字があれば合い方の強い順（同じなら回数順）
export function search(list, q) {
  const rows = list.map((f, i) => ({ f, i, s: score(f, q) })).filter((x) => !q || x.s >= 0);
  rows.sort((a, b) => b.s - a.s || b.f.uses - a.f.uses || a.i - b.i);
  return rows.map((x) => x.f);
}
