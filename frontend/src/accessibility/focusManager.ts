// Moves keyboard/accessibility focus on screen changes. Chrome on Android moves
// TalkBack's accessibility focus along with DOM focus, so focusing the answer
// heading makes TalkBack start reading there instead of where the user last tapped.

const stack: HTMLElement[] = [];

/** Focus an element that isn't natively focusable (heading, region). */
export function focusElement(el: HTMLElement | null, opts: { remember?: boolean } = {}) {
  if (!el) return;
  if (opts.remember && document.activeElement instanceof HTMLElement) {
    stack.push(document.activeElement);
  }
  if (!el.hasAttribute('tabindex') && !isNativelyFocusable(el)) el.setAttribute('tabindex', '-1');
  // Wait a frame so React has committed the new content before TalkBack reads it.
  requestAnimationFrame(() => el.focus({ preventScroll: false }));
}

export function focusById(id: string, opts?: { remember?: boolean }) {
  focusElement(document.getElementById(id), opts);
}

/** Return focus to where it was before the last remembered move (e.g. closing a panel). */
export function restoreFocus() {
  const el = stack.pop();
  if (el?.isConnected) requestAnimationFrame(() => el.focus());
}

function isNativelyFocusable(el: HTMLElement): boolean {
  return (
    el instanceof HTMLButtonElement ||
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLAnchorElement && !!el.href)
  );
}
