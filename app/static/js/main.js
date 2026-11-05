// 全ページ共通の JS の入口。
import { setupSideToggle } from "./sidebar.js";
import { setupSingleSubmit } from "./forms.js";

const shell = document.getElementById("shell");
const button = document.getElementById("side-toggle");
if (shell && button) {
  setupSideToggle(shell, button);
}
setupSingleSubmit();
