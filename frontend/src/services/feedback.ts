// Non-visual and non-auditory feedback: answer audio, earcons, vibration and
// screen flash. Which channels fire depends on the profile (see App.tsx).

import type { Language } from './api';

export const VIBRATE = {
  tick: [30],
  captured: [60, 60, 60],
  answer: [120],
  alert: [300, 120, 300, 120, 300],
  error: [400],
} as const;

let audioCtx: AudioContext | null = null;
let current: HTMLAudioElement | null = null;
let currentUtterance: SpeechSynthesisUtterance | null = null;

/** Mobile Chrome blocks audio until a user gesture; call from the first tap. */
export function unlockAudio() {
  audioCtx ??= new AudioContext();
  if (audioCtx.state === 'suspended') void audioCtx.resume();
}

export function vibrate(pattern: readonly number[]) {
  if ('vibrate' in navigator) navigator.vibrate([...pattern]);
}

/** Short tones so a blind user knows the app's state without speech. */
export function earcon(kind: 'listening' | 'captured' | 'stable' | 'error') {
  if (!audioCtx) return;
  const notes: Record<typeof kind, number[]> = {
    listening: [660, 880],
    captured: [880, 660, 880],
    stable: [990],
    error: [300, 220],
  };
  let t = audioCtx.currentTime;
  for (const f of notes[kind]) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = f;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.25, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(t);
    osc.stop(t + 0.13);
    t += 0.14;
  }
}

/** Visual alert for deaf users; App renders the overlay when this event fires. */
export function flash() {
  window.dispatchEvent(new CustomEvent('signsaathi:flash'));
}

export function stopSpeech() {
  current?.pause();
  current = null;
  if (currentUtterance) speechSynthesis.cancel();
  currentUtterance = null;
}

/** Plays Bhashini TTS audio at the user's chosen speed. */
export function playAudio(b64: string, mime: string, rate: number): Promise<void> {
  stopSpeech();
  const el = new Audio(`data:${mime};base64,${b64}`);
  el.playbackRate = rate;
  el.preservesPitch = true;
  current = el;
  return new Promise((resolve) => {
    el.onended = () => resolve();
    el.onerror = () => resolve();
    el.play().catch(() => resolve());
  });
}

const BCP47: Record<Language, string> = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN' };

/** On-device fallback when Bhashini audio is unavailable (offline, quota, errors). */
export function speakLocally(text: string, lang: Language, rate: number): Promise<void> {
  stopSpeech();
  if (!('speechSynthesis' in window) || !text) return Promise.resolve();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = BCP47[lang];
  u.rate = rate;
  const voice = speechSynthesis.getVoices().find((v) => v.lang.replace('_', '-').startsWith(BCP47[lang]));
  if (voice) u.voice = voice;
  currentUtterance = u;
  return new Promise((resolve) => {
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}
