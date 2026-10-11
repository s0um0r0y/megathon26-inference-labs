import { useState } from 'react';
import type { Strings } from '../i18n';
import type { AnalyzeResponse, HelpOffer, Language, Profile, Stage } from '../services/api';
import type { Phase } from '../state/interactionMachine';

interface Props {
  t: Strings;
  uiLang: Language;
  profile: Profile;
  phase: Phase;
  stage: Stage | null;
  response: AnalyzeResponse | null;
  error: string | null;
  stepIndex: number;
  showSimpler: boolean;
  speechRate: number;
  textScale: number;
  helpOffer: HelpOffer | null;
  onRepeat: () => void;
  onToggleSimpler: () => void;
  onNextStep: () => void;
  onPrevStep: () => void;
  onConfirm: (yes: boolean) => void;
  onRetry: () => void;
  onCancel: () => void;
  onHelp: () => void;
  onSpeechRate: (r: number) => void;
  onTextScale: (s: number) => void;
}

/**
 * Answer-first output: one sentence, then caution, then optional steps/details.
 * The heading (#answer-heading) receives focus when an answer arrives so TalkBack
 * starts reading here. Content carries the answer's `lang` so TalkBack switches
 * voice for Hindi/Telugu.
 */
export function GuidanceOutput(p: Props) {
  const { t, response: r } = p;
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [compare, setCompare] = useState(false);
  const answer = r?.answer;
  const lang = r?.language ?? p.uiLang;
  const steps = answer?.steps ?? [];
  const oneStepAtATime = p.profile === 'ageing' || p.profile === 'visual';

  return (
    <section className="answer" aria-labelledby="answer-heading" style={{ fontSize: `${p.textScale}rem` }}>
      <h2 id="answer-heading" tabIndex={-1}>
        {t.answerSection}
      </h2>

      {p.phase === 'processing' && (
        <div className="progress" aria-busy="true">
          <p>{p.stage ? t.stages[p.stage] : t.stages.received}…</p>
          <button type="button" className="secondary" onClick={p.onCancel}>
            {t.cancel}
          </button>
        </div>
      )}

      {p.phase === 'error' && (
        <div className="error-box">
          <p>{p.error && !p.error.startsWith('{') ? p.error : t.errorGeneric}</p>
          <button type="button" className="primary" onClick={p.onRetry}>
            {t.retry}
          </button>
        </div>
      )}

      {p.phase === 'confirm' && r && (
        <div className="confirm">
          <p lang={lang}>
            {r.transcript ? (
              <>
                {t.youAsked}: <q>{r.transcript}</q>
              </>
            ) : (
              r.spoken_text
            )}
          </p>
          <div className="button-row">
            {r.transcript && (
              <button type="button" className="primary big" onClick={() => p.onConfirm(true)}>
                {t.confirmYes}
              </button>
            )}
            <button type="button" className="secondary big" onClick={() => p.onConfirm(false)}>
              {t.confirmNo}
            </button>
          </div>
        </div>
      )}

      {(p.phase === 'answer' || p.phase === 'retake') && answer && (
        <div className="result" lang={lang} data-status={r?.status}>
          <p className="short">{p.showSimpler && answer.simpler ? answer.simpler : answer.short}</p>

          {answer.caution && (
            <p className="caution" role="note">
              <strong lang={p.uiLang}>{t.caution}: </strong>
              {answer.caution}
            </p>
          )}

          {p.phase === 'retake' && r?.retake_hint && r.retake_hint !== answer.short && (
            <p className="retake-hint">{r.retake_hint}</p>
          )}

          {steps.length > 0 &&
            (oneStepAtATime ? (
              <div className="steps" aria-labelledby="step-label">
                <p id="step-label" className="step-count" lang={p.uiLang}>
                  {t.stepOf(p.stepIndex + 1, steps.length)}
                </p>
                <p className="step" aria-live="polite">
                  {steps[p.stepIndex]}
                </p>
                <div className="button-row" lang={p.uiLang}>
                  <button type="button" className="secondary" onClick={p.onPrevStep} disabled={p.stepIndex === 0}>
                    {t.previousStep}
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={p.onNextStep}
                    disabled={p.stepIndex >= steps.length - 1}
                  >
                    {t.nextStep}
                  </button>
                </div>
              </div>
            ) : (
              <ol className="steps">
                {steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            ))}

          {answer.follow_up && <p className="follow-up">{answer.follow_up}</p>}

          {answer.details.length > 0 && (
            <div className="details" lang={p.uiLang}>
              <button
                type="button"
                className="secondary"
                aria-expanded={detailsOpen}
                aria-controls="answer-details"
                onClick={() => setDetailsOpen((o) => !o)}
              >
                {detailsOpen ? t.lessDetails : t.moreDetails}
              </button>
              <ul id="answer-details" hidden={!detailsOpen} lang={lang}>
                {answer.details.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
          )}

          {r?.landmarks && r.landmarks.length > 0 && (
            <details className="landmarks" lang={p.uiLang}>
              <summary>{t.nearby}</summary>
              <ul>
                {r.landmarks.map((l, i) => (
                  <li key={i}>
                    {l.name} ({l.kind}), {l.distance_m} m{l.direction ? `, ${l.direction}` : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {r?.sign_text && (
            <details className="sign-text" lang={p.uiLang}>
              <summary>{t.whatWasRead}</summary>
              <pre>{r.sign_text}</pre>
            </details>
          )}

          {r?.confidence && (
            <p className="confidence" data-level={r.confidence.level} lang={p.uiLang}>
              {t.confidence[r.confidence.level]}
            </p>
          )}
        </div>
      )}

      {(p.phase === 'answer' || p.phase === 'retake') && (
        <div className="controls" lang={p.uiLang}>
          <div className="button-row">
            <button type="button" className="secondary big" onClick={p.onRepeat}>
              {t.repeat}
            </button>
            {answer?.simpler && (
              <button type="button" className="secondary big" aria-pressed={p.showSimpler} onClick={p.onToggleSimpler}>
                {p.showSimpler ? t.showOriginal : t.simpler}
              </button>
            )}
            {p.phase === 'retake' && (
              <button type="button" className="primary big" onClick={p.onRetry}>
                {t.retry}
              </button>
            )}
          </div>

          <div className="sliders">
            <label>
              {t.speechSpeed}
              <input
                type="range"
                min={0.5}
                max={1.5}
                step={0.1}
                value={p.speechRate}
                aria-valuetext={`${Math.round(p.speechRate * 100)}%`}
                onChange={(e) => p.onSpeechRate(Number(e.target.value))}
              />
            </label>
            <label>
              {t.textSize}
              <input
                type="range"
                min={1}
                max={2}
                step={0.25}
                value={p.textScale}
                aria-valuetext={`${Math.round(p.textScale * 100)}%`}
                onChange={(e) => p.onTextScale(Number(e.target.value))}
              />
            </label>
          </div>

          {r?.raw_answer && (
            <div className="compare">
              <button type="button" className="link" aria-expanded={compare} onClick={() => setCompare((c) => !c)}>
                {t.compare}
              </button>
              {compare && (
                <div className="compare-grid">
                  <div>
                    <h3>{t.plainAssistant}</h3>
                    <p lang="en">{r.raw_answer}</p>
                  </div>
                  <div>
                    <h3>{t.signSaathi}</h3>
                    <p lang={lang}>{r.spoken_text}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {(p.phase === 'aiming' || p.phase === 'onboarding') && !r && <p className="hint">{t.noAnswerYet}</p>}

      <div className="help" lang={p.uiLang}>
        {p.helpOffer ? (
          <>
            <p>{p.helpOffer.message}</p>
            <div className="button-row">
              {p.helpOffer.call_number && (
                <a className="button danger big" href={`tel:${p.helpOffer.call_number}`}>
                  {t.call(p.helpOffer.call_number)}
                </a>
              )}
              {p.helpOffer.sms_body && (
                <a className="button secondary" href={`sms:?body=${encodeURIComponent(p.helpOffer.sms_body)}`}>
                  {t.shareLocation}
                </a>
              )}
            </div>
          </>
        ) : (
          <button type="button" className="secondary" onClick={p.onHelp}>
            {t.getHelp}
          </button>
        )}
      </div>
    </section>
  );
}
