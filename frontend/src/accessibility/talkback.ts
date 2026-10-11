// TalkBack support helpers.
//
// A web page cannot query whether TalkBack is on. What it can see: TalkBack
// activates controls through the accessibility tree (double-tap anywhere), which
// Chrome delivers as a `click` with no preceding pointerdown on that element. A
// few of those in a row are a strong hint, used as a condition signal
// (state/interactionMachine.ts) - never as a silent switch: the user confirms.
//
// Markup rules every component follows (TalkBack reads the accessibility tree):
// - Native <button>/<input>/<select> only; no clickable <div>s.
// - Every control has a visible or aria label; toggles use aria-pressed;
//   disclosures use aria-expanded + aria-controls.
// - One <h1>, an <h2> per section, landmarks (<header>, <main>, <section aria-labelledby>).
// - Answer text carries a `lang` attribute so TalkBack picks a Hindi/Telugu voice.
// - Decorative visuals (camera preview, overlay) are aria-hidden; their meaning is
//   provided as text.
// - Touch targets are at least 48x48 CSS px (styles.css).

export type SpeechOwner = 'app' | 'screen_reader';

const OWNER_KEY = 'signsaathi.speechOwner';

/**
 * Who speaks answers. 'app' plays Bhashini audio (natural Telugu/Hindi voices that
 * TalkBack may lack) and only announces a short "answer ready"; 'screen_reader'
 * skips app audio and lets TalkBack read the answer text itself, so the two never
 * talk over each other.
 */
export function getSpeechOwner(): SpeechOwner {
  try {
    return (localStorage.getItem(OWNER_KEY) as SpeechOwner) || 'app';
  } catch {
    return 'app';
  }
}

export function setSpeechOwner(owner: SpeechOwner) {
  try {
    localStorage.setItem(OWNER_KEY, owner);
  } catch {
    /* storage blocked: preference lasts for this page only */
  }
}

/** Calls `onHint` each time a control is activated without touching it directly. */
export function watchAssistiveActivation(onHint: () => void): () => void {
  let lastPointer = { target: null as EventTarget | null, at: 0 };
  let lastKey = 0;
  const onPointer = (e: PointerEvent) => (lastPointer = { target: e.target, at: Date.now() });
  const onKey = () => (lastKey = Date.now());
  const onClick = (e: MouseEvent) => {
    const t = e.target as HTMLElement | null;
    if (!t?.closest('button, a, input, select, [role="button"]')) return;
    const now = Date.now();
    const touched = now - lastPointer.at < 800;
    const keyed = now - lastKey < 800;
    // TalkBack double-tap: no pointer and no key on this element just before the click.
    if (!keyed && (!touched || e.detail === 0)) onHint();
  };
  window.addEventListener('pointerdown', onPointer, true);
  window.addEventListener('keydown', onKey, true);
  window.addEventListener('click', onClick, true);
  return () => {
    window.removeEventListener('pointerdown', onPointer, true);
    window.removeEventListener('keydown', onKey, true);
    window.removeEventListener('click', onClick, true);
  };
}

/** Pinch-zoom is a hint that text is too small (ageing / low-vision signal). */
export function watchZoom(onZoom: () => void): () => void {
  const vv = window.visualViewport;
  if (!vv) return () => {};
  let zoomed = false;
  const onResize = () => {
    const now = vv.scale > 1.2;
    if (now && !zoomed) onZoom();
    zoomed = now;
  };
  vv.addEventListener('resize', onResize);
  return () => vv.removeEventListener('resize', onResize);
}
