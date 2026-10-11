// Screen-reader announcements through ARIA live regions (TalkBack reads these
// without moving focus). Two regions: polite for status, assertive for things the
// user must hear now (errors, safety cautions, "answer ready").
//
// Camera framing cues arrive several times a second; cue() throttles them so
// TalkBack isn't flooded and the user can still hear their own navigation.

const CLEAR_DELAY_MS = 60;
const DEDUPE_MS = 1500;
const CUE_MIN_GAP_MS = 2500;
const CUE_REPEAT_MS = 6000;

class Announcer {
  private polite: HTMLElement | null = null;
  private assertive: HTMLElement | null = null;
  private last = { text: '', at: 0 };
  private lastCue = { text: '', at: 0 };

  mount() {
    if (this.polite) return;
    this.polite = this.region('polite');
    this.assertive = this.region('assertive');
  }

  private region(politeness: 'polite' | 'assertive'): HTMLElement {
    const el = document.createElement('div');
    el.setAttribute('aria-live', politeness);
    el.setAttribute('aria-atomic', 'true');
    // role=status/alert add implicit live semantics TalkBack respects reliably.
    el.setAttribute('role', politeness === 'polite' ? 'status' : 'alert');
    el.className = 'sr-only';
    document.body.appendChild(el);
    return el;
  }

  /** Announce text. `lang` makes TalkBack switch to a Hindi/Telugu voice. */
  say(text: string, opts: { assertive?: boolean; lang?: string; force?: boolean } = {}) {
    this.mount();
    const now = Date.now();
    if (!opts.force && text === this.last.text && now - this.last.at < DEDUPE_MS) return;
    this.last = { text, at: now };
    const el = opts.assertive ? this.assertive! : this.polite!;
    // Clear then set: identical consecutive text is otherwise not re-announced.
    el.textContent = '';
    if (opts.lang) el.setAttribute('lang', opts.lang);
    else el.removeAttribute('lang');
    window.setTimeout(() => (el.textContent = text), CLEAR_DELAY_MS);
  }

  /** Throttled camera-framing cue. Returns true if it was announced. */
  cue(text: string, lang?: string): boolean {
    const now = Date.now();
    const sameAsLast = text === this.lastCue.text;
    if (now - this.lastCue.at < CUE_MIN_GAP_MS) return false;
    if (sameAsLast && now - this.lastCue.at < CUE_REPEAT_MS) return false;
    this.lastCue = { text, at: now };
    this.say(text, { lang, force: true });
    return true;
  }

  resetCues() {
    this.lastCue = { text: '', at: 0 };
  }
}

export const announcer = new Announcer();
