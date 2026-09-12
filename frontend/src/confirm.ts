/**
 * "Точно удалить?" — the app's own dialog, not the browser's.
 *
 * Inside Telegram this defers to `showConfirm`, which draws the platform's
 * native sheet. Outside it, the fallback used to be `window.confirm`: a grey
 * OS box in a typeface the app does not use, anchored to the top of the
 * window, with buttons labelled by the browser's locale rather than ours —
 * and it blocks the whole page while it is up. Every destructive action in
 * the product goes through here, so that box was the last thing a user saw
 * before losing a bot or a block.
 *
 * Built imperatively rather than as a React component because it is called
 * from plain event handlers deep in the tree (`await confirmDialog(...)`),
 * where there is no render to hang a portal off. `<dialog showModal()>`
 * gives focus trapping, Esc-to-dismiss and the top layer for free.
 */

const CANCEL = "Отмена";
const CONFIRM = "Удалить";

function webConfirm(message: string): Promise<boolean> {
  // No document (SSR, a test runner without a DOM) — refuse rather than
  // silently proceeding with something destructive.
  if (typeof document === "undefined" || typeof HTMLDialogElement === "undefined") {
    return Promise.resolve(false);
  }

  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog";

    const text = document.createElement("p");
    text.className = "confirm-dialog__text";
    text.textContent = message;

    const row = document.createElement("div");
    row.className = "confirm-dialog__actions";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "confirm-dialog__button";
    cancel.textContent = CANCEL;

    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "confirm-dialog__button confirm-dialog__button--danger";
    confirm.textContent = CONFIRM;

    row.append(cancel, confirm);
    dialog.append(text, row);
    document.body.appendChild(dialog);

    let answer = false;
    const close = (value: boolean) => {
      answer = value;
      dialog.close();
    };
    cancel.addEventListener("click", () => close(false));
    confirm.addEventListener("click", () => close(true));
    // Esc and a click on the backdrop both mean "no" — the safe answer is
    // always the one that changes nothing.
    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      close(false);
    });
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) close(false);
    });
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(answer);
    });

    dialog.showModal();
    // Focus lands on "Отмена", not on the destructive button: an Enter
    // pressed out of habit must not delete anything.
    cancel.focus();
  });
}

/** Native-feeling confirmation — Telegram's own popup inside the Mini App,
 * the app's dialog everywhere else. */
export function confirmDialog(message: string): Promise<boolean> {
  const webApp = window.Telegram?.WebApp;
  if (webApp?.showConfirm) {
    return new Promise((resolve) => webApp.showConfirm!(message, resolve));
  }
  return webConfirm(message);
}
