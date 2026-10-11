import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Strings } from '../i18n';
import type { Language } from '../services/api';
import type { Phase } from '../state/interactionMachine';

interface Props {
  t: Strings;
  lang: Language;
  phase: Phase;
  micAvailable: boolean;
  onStartVoice: () => void;
  onStopVoice: () => void;
  onAsk: (text: string) => void;
}

/**
 * Ask by voice (tap to start, tap to stop: press-and-hold is awkward under
 * TalkBack), by typing, or from a phrase board for when speech fails.
 */
export function VoiceControl({ t, lang, phase, micAvailable, onStartVoice, onStopVoice, onAsk }: Props) {
  const [text, setText] = useState('');
  const listening = phase === 'listening';
  const busy = phase === 'capturing' || phase === 'processing';

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = text.trim();
    if (!q) return;
    onAsk(q);
    setText('');
  }

  return (
    <section className="ask" aria-labelledby="ask-title">
      <h2 id="ask-title">{t.askSection}</h2>

      {micAvailable && (
        <button
          type="button"
          className={`mic big ${listening ? 'recording' : ''}`}
          aria-pressed={listening}
          aria-describedby={listening ? 'mic-status' : undefined}
          onClick={listening ? onStopVoice : onStartVoice}
          disabled={busy}
        >
          <span aria-hidden="true" className="mic-icon" />
          {listening ? t.stopSpeaking : t.speak}
        </button>
      )}
      {listening && (
        <p id="mic-status" className="hint">
          {t.listening}
        </p>
      )}

      <form className="ask-form" onSubmit={submit}>
        <label htmlFor="question">{t.typeQuestion}</label>
        <div className="ask-row">
          <input
            id="question"
            type="text"
            lang={lang}
            value={text}
            onChange={(e) => setText(e.target.value)}
            enterKeyHint="send"
            autoComplete="off"
            disabled={busy}
          />
          <button type="submit" className="primary" disabled={busy || !text.trim()}>
            {t.send}
          </button>
        </div>
      </form>

      <h3 id="phrases-title">{t.commonQuestions}</h3>
      <ul className="phrases" aria-labelledby="phrases-title">
        {t.phrases.map((ph) => (
          <li key={ph}>
            <button type="button" className="phrase" lang={lang} onClick={() => onAsk(ph)} disabled={busy}>
              {ph}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
