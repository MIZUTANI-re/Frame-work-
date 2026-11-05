// 「フレームワークを探す」画面：打つたびに絞る・チャット（見本 v2 と同じ動き）。
import { esc, highlight, search } from "./search_logic.js";

const candsBox = document.getElementById("cands");
const input = document.getElementById("search");
const list = JSON.parse(document.getElementById("fw-data").textContent);
const courseId = candsBox.dataset.courseId;

// ※ 未習: 打つと候補が出る検索（サジェスト）— 一覧を最初に全部受け取り、打つたびにブラウザの中で絞り込む
function render() {
  const q = input.value;
  const rows = search(list, q).map((f) => `<div class="cand"><div class="body">
      <div class="name">${highlight(f.name, q)}<span class="badge">${esc(f.purpose_label)}</span><span class="badge">${esc(f.thinking_label)}</span></div>
      <div class="sub">別名：${f.aliases.map((a) => highlight(a, q)).join("・")}</div>
      <div class="sub">${esc(f.description)}</div></div>
      <div class="uses">${f.uses} 回使われています</div>
      <form method="post" action="/courses/${courseId}/flow/add">
        <input type="hidden" name="framework_key" value="${esc(f.key)}">
        <input type="hidden" name="q" value="${esc(q)}">
        <button type="submit" class="ghost" ${f.in_flow ? "disabled" : ""}>${f.in_flow ? "流れに入っています" : "流れに足す"}</button>
      </form></div>`).join("");
  candsBox.innerHTML = rows || `<div class="empty">合うフレームワークがありません</div>`;
}
input.addEventListener("input", render);
render();

// ---- チャット（Enter で送る・Shift + Enter で改行。日本語の変換中の Enter は送らない）----
const log = document.getElementById("chat-log");
const textarea = document.getElementById("chat-text");
const sendButton = document.getElementById("chat-send");

function addMessage(role, text) {
  const empty = document.getElementById("chat-empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text; // textContent なので、打った文字が HTML として動くことはない
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function send() {
  const text = textarea.value.trim();
  if (!text) return;
  sendButton.disabled = true;
  try {
    const res = await fetch(`/courses/${courseId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ text }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    data.messages.forEach((m) => addMessage(m.role, m.text));
    textarea.value = "";
  } catch (e) {
    addMessage("assistant", "送れませんでした。もう一度試してください");
  } finally {
    sendButton.disabled = false;
  }
}
sendButton.addEventListener("click", send);
textarea.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
