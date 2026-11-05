// スマホ幅で 2 列目（班の一覧）を開け閉めする。

export function setupSideToggle(shell, button) {
  button.addEventListener("click", () => {
    shell.classList.toggle("side-open");
  });
}
