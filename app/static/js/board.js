// ボードの盤面。WebSocket で付箋を受け取り、足す・動かす・消す操作を送る。
// 付箋の本文は textContent で入れる（HTML として解釈させない）。

// ※ 未習: WebSocket — ブラウザとサーバーがつなぎっぱなしになり、どちらからでも送れる通信
function socketUrl(boardId) {
  // http なら ws、https なら wss（自動で切り替える）
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws/boards/${boardId}`;
}

const PING_MS = 30000;      // 30 秒ごとの合図（Cloudflare に切られないため）
const RETRY_MS = 2000;      // 切れたら 2 秒後につなぎ直す
// ログイン切れ・見る権限なし。つなぎ直しても同じなので止めて、案内を出す
const FINAL_MESSAGES = {
  4401: "ログインし直してください。",
  4403: "このボードは見られなくなりました。",
};

export function setupBoard(root) {
  const boardId = root.dataset.boardId;
  const status = document.getElementById("board-status");
  let notes = new Map();
  let me = null;
  let writable = false;
  let socket = null;
  let pingTimer = null;

  function send(obj) {
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(obj));
  }

  function noteElement(n) {
    const el = document.createElement("div");
    el.className = "note" + (n.author_id === me ? " mine" : "");
    el.style.background = n.color;
    el.dataset.id = n.id;
    const body = document.createElement("div");
    body.textContent = n.text;
    const who = document.createElement("div");
    who.className = "who";
    const name = document.createElement("span");
    name.textContent = n.author_name;
    who.append(name);
    if (writable && n.author_id === me) {  // 動かせる・消せるのは書いた本人だけ
      el.draggable = true;
      el.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", String(n.id)));
      const del = document.createElement("button");
      del.type = "button";
      del.className = "del";
      del.textContent = "×";
      del.title = "消す";
      del.addEventListener("click", () => send({ type: "note.delete", id: n.id }));
      who.append(del);
    }
    el.append(body, who);
    return el;
  }

  function render() {
    root.querySelectorAll(".zone .notes").forEach((box) => (box.textContent = ""));
    for (const n of notes.values()) {
      const box = root.querySelector(`.zone[data-zone="${n.zone_key}"] .notes`);
      if (box) box.append(noteElement(n));
    }
    root.querySelectorAll(".write-only").forEach((el) => (el.hidden = !writable));
  }

  function onMessage(m) {
    if (m.type === "snapshot") {  // 全部を取り直す（つないだとき・つなぎ直したとき）
      notes = new Map(m.notes.map((n) => [n.id, n]));
      me = m.me;
      writable = m.writable;
    } else if (m.type === "note.created" || m.type === "note.moved") {
      notes.set(m.note.id, m.note);
    } else if (m.type === "note.deleted") {
      notes.delete(m.id);
    } else if (m.type === "error") {
      alert("操作できませんでした（" + m.code + "）");
      return;
    } else {
      return;
    }
    render();
  }

  function connect() {
    socket = new WebSocket(socketUrl(boardId));
    socket.addEventListener("open", () => {
      if (status) status.hidden = true;
      pingTimer = setInterval(() => send({ type: "ping" }), PING_MS);
    });
    socket.addEventListener("message", (e) => onMessage(JSON.parse(e.data)));
    socket.addEventListener("close", (e) => {
      clearInterval(pingTimer);
      if (FINAL_MESSAGES[e.code]) {
        if (status) { status.textContent = FINAL_MESSAGES[e.code]; status.hidden = false; }
        return;
      }
      if (status) { status.textContent = "つなぎ直しています…"; status.hidden = false; }
      setTimeout(connect, RETRY_MS);  // つなぎ直すと、サーバーが全部を送り直してくる
    });
  }

  root.querySelectorAll("[data-add]").forEach((button) =>
    button.addEventListener("click", () => {
      const text = prompt("付箋に書くこと");
      if (text && text.trim()) send({ type: "note.add", zone_key: button.dataset.add, text });
    }));
  root.querySelectorAll(".zone").forEach((zone) => {
    zone.addEventListener("dragover", (e) => { if (writable) { e.preventDefault(); zone.classList.add("over"); } });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("over");
      const id = Number(e.dataTransfer.getData("text/plain"));
      const note = notes.get(id);
      // 同じ区画に落としたときは送らない
      if (writable && note && note.zone_key !== zone.dataset.zone) send({ type: "note.move", id, zone_key: zone.dataset.zone });
    });
  });

  connect();
}
