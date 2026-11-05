// フォームを送信したらボタンを無効にする（2 度押しで二重に送らないため）。

export function setupSingleSubmit() {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll("button[type=submit]").forEach((b) => {
        b.disabled = true;
      });
    });
  });
  // 「戻る」で戻ったときにボタンが無効のままにならないようにする
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      document.querySelectorAll("button[type=submit]").forEach((b) => {
        b.disabled = false;
      });
    }
  });
}
