// 全ページ共通の JS の入口。
import { setupSideToggle } from "./sidebar.js";
import { setupSingleSubmit } from "./forms.js";

const shell = document.getElementById("shell");
const button = document.getElementById("side-toggle");
if (shell && button) {
  setupSideToggle(shell, button);
}
setupSingleSubmit();

// ボードの画面だけ、盤面をつなぐ
const boardRoot = document.getElementById("board");
if (boardRoot) {
  import("./board.js").then((m) => m.setupBoard(boardRoot));
}
