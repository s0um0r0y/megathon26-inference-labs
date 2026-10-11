import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { announcer } from './accessibility/announcer';
import { focusById } from './accessibility/focusManager';
import { getSpeechOwner, setSpeechOwner, watchAssistiveActivation, watchZoom } from './accessibility/talkback';
import type { SpeechOwner } from './accessibility/talkback';
import { CameraView } from './components/CameraView';
import { GuidanceOutput } from './components/GuidanceOutput';
import { PermissionScreen } from './components/PermissionScreen';
import { VoiceControl } from './components/VoiceControl';
import { LANGUAGE_NAMES, STRINGS } from './i18n';
import * as api from './services/api';
import type { AnalyzeResponse, HelpOffer, Language, Profile } from './services/api';
import { captureJpeg, FrameMonitor, openCamera, setTorch, stopCamera, torchSupported } from './services/camera';
import * as feedback from './services/feedback';
import { LocationTracker } from './services/location';
import { Recorder, requestMicrophone } from './services/microphone';
import { initialState, isBusy, reduce } from './state/interactionMachine';
import { REQUIRED_STABLE_FRAMES } from './workers/frameQuality.worker';
import type { FrameStats, FramingHint } from './workers/frameQuality.worker';

const CAPTURE_TIMEOUT_MS = 6000; // after this, send the best frame anyway and let the server judge
const MIC_START_DELAY_MS = 450; // let TalkBack finish "pressed" so it isn't recorded
const MIN_PITCH_DEG = 35; // below this the phone points at the ground

type Hint = FramingHint | 'raise_phone';

function loadPref<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}

function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked */
  }
}

export default function App() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const [language, setLanguage] = useState<Language>(() => loadPref<Language>('signsaathi.lang', 'en'));
  const [profile, setProfile] = useState<Profile>(() => loadPref<Profile>('signsaathi.profile', 'default'));
  const [answerLanguage, setAnswerLanguage] = useState<Language | ''>('');
  const [speechRate, setSpeechRate] = useState(1);
  const [textScale, setTextScale] = useState(1);
  const [speechOwner, setOwner] = useState<SpeechOwner>(getSpeechOwner);
  const [hint, setHint] = useState<Hint | null>(null);
  const [stableFrames, setStableFrames] = useState(0);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [micAvailable, setMicAvailable] = useState(false);
  const [helpOffer, setHelpOffer] = useState<HelpOffer | null>(null);
  const [flashOn, setFlashOn] = useState(false);

  const t = STRINGS[language];
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStream = useRef<MediaStream | null>(null);
  const micStream = useRef<MediaStream | null>(null);
  const recorder = useRef<Recorder | null>(null);
  const monitor = useRef<FrameMonitor | null>(null);
  const tracker = useRef(new LocationTracker());
  const socket = useRef<api.SessionSocket | null>(null);
  const latestStats = useRef<FrameStats | null>(null);
  const abort = useRef<AbortController | null>(null);
  const lastAudio = useRef<{ b64: string; mime: string } | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  // ---- global wiring -------------------------------------------------------------
  useEffect(() => {
    announcer.mount();
    if ('serviceWorker' in navigator && import.meta.env.PROD) {
      void navigator.serviceWorker.register('/sw.js');
    }
    const offAT = watchAssistiveActivation(() => dispatch({ type: 'SIGNAL', signal: 'assistiveActivations' }));
    const offZoom = watchZoom(() => dispatch({ type: 'SIGNAL', signal: 'zooms' }));
    const onFlash = () => {
      setFlashOn(true);
      window.setTimeout(() => setFlashOn(false), 450);
    };
    window.addEventListener('signsaathi:flash', onFlash);
    return () => {
      offAT();
      offZoom();
      window.removeEventListener('signsaathi:flash', onFlash);
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
    savePref('signsaathi.lang', language);
  }, [language]);

  useEffect(() => {
    savePref('signsaathi.profile', profile);
    if (profile === 'ageing') {
      setSpeechRate((r) => Math.min(r, 0.85));
      setTextScale((s) => Math.max(s, 1.5));
    }
  }, [profile]);

  // Keep the server session in sync with language/profile.
  useEffect(() => {
    const s = stateRef.current.session;
    if (!s || (s.language === language && s.profile === profile)) return;
    api
      .updateSession(s.session_id, { language, profile, speech_rate: speechRate })
      .then((session) => dispatch({ type: 'SESSION_READY', session }))
      .catch(() => {});
  }, [language, profile, speechRate]);

  // ---- session + socket ----------------------------------------------------------
  const startSession = useCallback(async () => {
    const session = await api.createSession({ language, profile, speech_rate: speechRate });
    socket.current?.close();
    socket.current = new api.SessionSocket(session.session_id, (ev) =>
      dispatch({ type: 'PROGRESS', requestId: ev.request_id, stage: ev.stage }),
    );
    dispatch({ type: 'SESSION_READY', session });
    return session;
  }, [language, profile, speechRate]);

  useEffect(() => () => socket.current?.close(), []);

  // ---- camera + frame quality ----------------------------------------------------
  const onStats = useCallback(
    (s: FrameStats) => {
      latestStats.current = s;
      const pitch = tracker.current.pitch();
      const h: Hint = pitch !== undefined && pitch < MIN_PITCH_DEG && s.hint !== 'good' ? 'raise_phone' : s.hint;
      setHint(h);
      setStableFrames(s.stable_frames);
      const phase = stateRef.current.phase;
      // Spoken aiming help: always while capturing; while idle only for the visual profile.
      if (phase === 'capturing' || (phase === 'aiming' && profile === 'visual')) {
        if (announcer.cue(STRINGS[language].framing[h], language) && phase === 'capturing') {
          feedback.vibrate(feedback.VIBRATE.tick);
        }
      }
    },
    [language, profile],
  );

  useEffect(() => {
    if (state.phase === 'onboarding' || !videoRef.current) return;
    let cancelled = false;
    const video = videoRef.current;
    openCamera(video)
      .then((stream) => {
        if (cancelled) return stopCamera(stream);
        cameraStream.current = stream;
        setTorchAvailable(torchSupported(stream));
      })
      .catch(() => announcer.say(STRINGS[language].cameraRequired, { assertive: true }));
    return () => {
      cancelled = true;
      stopCamera(cameraStream.current);
      cameraStream.current = null;
    };
    // Re-open only when leaving onboarding, not on every phase change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase === 'onboarding']);

  useEffect(() => {
    if (state.phase === 'onboarding' || !videoRef.current) return;
    const m = new FrameMonitor(videoRef.current, (s) => onStatsRef.current(s));
    monitor.current = m;
    return () => {
      m.dispose();
      monitor.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase === 'onboarding']);

  const onStatsRef = useRef(onStats);
  onStatsRef.current = onStats;

  // Analyse frames only while it matters (saves battery while reading an answer).
  useEffect(() => {
    const m = monitor.current;
    if (!m) return;
    if (['aiming', 'capturing', 'retake', 'listening'].includes(state.phase)) m.start();
    else m.stop();
  }, [state.phase]);

  // ---- capture -> analyze ---------------------------------------------------------
  const runAnalyze = useCallback(
    async (image: Blob, requestId: string, retried = false): Promise<AnalyzeResponse> => {
      const s = stateRef.current;
      const session = s.session!;
      const q = s.question ?? {};
      const stats = latestStats.current;
      abort.current = new AbortController();
      try {
        return await api.analyze(
          {
            session_id: session.session_id,
            request_id: requestId,
            query_text: q.text,
            confirmed: q.confirmed,
            answer_language: answerLanguage || undefined,
            location: tracker.current.current(),
            frame_quality: stats
              ? {
                  brightness: stats.brightness,
                  blur_score: stats.blur_score,
                  motion: Math.min(stats.motion, 99),
                  stable_frames: stats.stable_frames,
                }
              : undefined,
            include_audio: speechOwner === 'app' && profile !== 'hearing',
          },
          image,
          q.text ? null : (q.audio ?? null),
          abort.current.signal,
        );
      } catch (e) {
        // Session expired server-side (restart, TTL): recreate once and retry.
        if (e instanceof api.ApiError && e.status === 404 && !retried) {
          await startSession();
          return runAnalyze(image, requestId, true);
        }
        throw e;
      }
    },
    [answerLanguage, profile, speechOwner, startSession],
  );

  useEffect(() => {
    if (state.phase !== 'capturing') return;
    let done = false;
    announcer.resetCues();
    announcer.say(t.holdStill);
    const started = Date.now();

    const poll = window.setInterval(async () => {
      const s = latestStats.current;
      const pitch = tracker.current.pitch();
      const pitchOk = pitch === undefined || pitch >= MIN_PITCH_DEG;
      const timedOut = Date.now() - started > CAPTURE_TIMEOUT_MS;
      if (done || !videoRef.current || videoRef.current.readyState < 2) return;
      if (!((s?.ready && pitchOk) || timedOut)) return;
      done = true;
      window.clearInterval(poll);
      try {
        const image = await captureJpeg(videoRef.current);
        feedback.earcon('captured');
        feedback.vibrate(feedback.VIBRATE.captured);
        const requestId = api.newRequestId();
        dispatch({ type: 'CAPTURED', requestId });
        const res = await runAnalyze(image, requestId);
        dispatch({ type: 'RESULT', response: res });
      } catch (e) {
        if ((e as Error).name === 'AbortError') return;
        dispatch({ type: 'FAILED', error: navigator.onLine ? STRINGS[language].errorGeneric : STRINGS[language].offline });
      }
    }, 100);

    return () => {
      done = true;
      window.clearInterval(poll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase]);

  // ---- progress + result delivery -------------------------------------------------
  useEffect(() => {
    if (state.phase === 'processing' && state.stage && state.stage !== 'done') {
      announcer.say(t.stages[state.stage]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.stage]);

  const speakText = useCallback(
    async (text: string, lang: Language, audio?: { b64: string; mime: string } | null) => {
      if (profile === 'hearing') return;
      if (speechOwner === 'screen_reader') {
        announcer.say(text, { assertive: true, lang, force: true });
        return;
      }
      if (audio) return feedback.playAudio(audio.b64, audio.mime, speechRate);
      return feedback.speakLocally(text, lang, speechRate);
    },
    [profile, speechOwner, speechRate],
  );

  useEffect(() => {
    const r = state.response;
    if (!r || !['answer', 'retake', 'confirm', 'error'].includes(state.phase)) return;
    lastAudio.current = r.audio_b64 && r.audio_mime ? { b64: r.audio_b64, mime: r.audio_mime } : null;
    if (r.help) setHelpOffer(r.help);

    const urgent = r.intent === 'emergency' || r.intent === 'traffic_signal' || r.status !== 'ok';
    feedback.vibrate(r.status === 'ok' ? (urgent ? feedback.VIBRATE.alert : feedback.VIBRATE.answer) : feedback.VIBRATE.error);
    if (profile === 'hearing' || urgent) feedback.flash();
    if (r.status !== 'ok') feedback.earcon('error');

    focusById('answer-heading');
    if (speechOwner === 'app' && profile !== 'hearing') announcer.say(t.answerReady);
    const text = r.spoken_text || r.error || '';
    if (text) void speakText(text, r.language, lastAudio.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.response]);

  useEffect(() => {
    if (state.phase === 'error' && !state.response && state.error) {
      announcer.say(state.error, { assertive: true });
      feedback.earcon('error');
      focusById('answer-heading');
    }
  }, [state.phase, state.error, state.response]);

  // Profile proposals: announce and move focus so the user can answer.
  useEffect(() => {
    if (!state.proposedProfile) return;
    announcer.say(t.suggestProfile[state.proposedProfile], { assertive: true });
    focusById('profile-proposal');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.proposedProfile]);

  // ---- handlers -------------------------------------------------------------------
  async function requestCamera(): Promise<boolean> {
    feedback.unlockAudio();
    const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    stopCamera(s); // CameraView opens the real stream; this only obtains permission
    return true;
  }

  async function requestMic(): Promise<boolean> {
    micStream.current = await requestMicrophone();
    setMicAvailable(true);
    return true;
  }

  async function requestLocation(): Promise<boolean> {
    // iOS needs an explicit motion permission; Android grants orientation silently.
    const DOE = DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<string> };
    await DOE.requestPermission?.().catch(() => undefined);
    await tracker.current.start();
    return true;
  }

  async function onOnboarded() {
    try {
      await startSession();
    } catch {
      announcer.say(t.offline, { assertive: true });
    }
  }

  async function startVoice() {
    if (!micStream.current) return;
    feedback.stopSpeech();
    dispatch({ type: 'START_LISTENING' });
    feedback.earcon('listening');
    feedback.vibrate(feedback.VIBRATE.tick);
    await new Promise((r) => setTimeout(r, MIC_START_DELAY_MS));
    if (stateRef.current.phase !== 'listening') return;
    recorder.current ??= new Recorder(micStream.current);
    const wav = await recorder.current.start();
    if (wav) dispatch({ type: 'QUESTION', question: { audio: wav } });
    else if (stateRef.current.phase === 'listening') dispatch({ type: 'RESET' });
  }

  function stopVoice() {
    recorder.current?.stop();
  }

  function ask(text: string) {
    feedback.stopSpeech();
    dispatch({ type: 'QUESTION', question: { text } });
  }

  function readSign() {
    feedback.stopSpeech();
    dispatch({ type: 'QUESTION', question: {} });
  }

  function cancel() {
    if (state.phase === 'listening') recorder.current?.cancel();
    if (state.requestId) socket.current?.cancel(state.requestId);
    abort.current?.abort();
    feedback.stopSpeech();
    dispatch({ type: 'CANCEL' });
  }

  function repeat() {
    const r = state.response;
    if (!r) return;
    dispatch({ type: 'SIGNAL', signal: 'replays' });
    const a = r.answer;
    const text = state.showSimpler && a?.simpler ? a.simpler : r.spoken_text;
    void speakText(text, r.language, state.showSimpler ? null : lastAudio.current);
  }

  async function toggleSimpler() {
    const r = state.response;
    const turningOn = !state.showSimpler;
    dispatch({ type: 'TOGGLE_SIMPLER' });
    if (!r?.answer) return;
    const text = turningOn && r.answer.simpler ? r.answer.simpler : r.spoken_text;
    let audio = turningOn ? null : lastAudio.current;
    if (turningOn && speechOwner === 'app' && profile !== 'hearing' && state.session) {
      const res = await api.speak(state.session.session_id, text, r.language).catch(() => null);
      if (res?.audio_b64 && res.audio_mime) audio = { b64: res.audio_b64, mime: res.audio_mime };
    }
    void speakText(text, r.language, audio);
  }

  function confirm(yes: boolean) {
    const transcript = state.response?.transcript;
    if (yes && transcript) dispatch({ type: 'QUESTION', question: { text: transcript, confirmed: true } });
    else void startVoice();
  }

  function retry() {
    if (state.question) dispatch({ type: 'QUESTION', question: state.question, retry: true });
    else dispatch({ type: 'RESET' });
  }

  async function getHelp() {
    if (!state.session) return;
    const offer = await api
      .requestHelp(state.session.session_id, 'user_requested', tracker.current.current())
      .catch(() => ({ message: t.call('112'), call_number: '112' }));
    setHelpOffer(offer);
    announcer.say(offer.message, { assertive: true });
  }

  function resolveProposal(accepted: boolean) {
    const p = state.proposedProfile;
    dispatch({ type: 'RESOLVE_PROPOSAL', accepted });
    if (accepted && p) setProfile(p);
    focusById('answer-heading');
  }

  async function toggleTorch() {
    const next = !torchOn;
    await setTorch(cameraStream.current, next).catch(() => {});
    setTorchOn(next);
  }

  function changeOwner(o: SpeechOwner) {
    setOwner(o);
    setSpeechOwner(o);
  }

  // ---- render ---------------------------------------------------------------------
  if (state.phase === 'onboarding') {
    return (
      <div className={`app profile-${profile}`}>
        <PermissionScreen
          language={language}
          profile={profile}
          onLanguage={setLanguage}
          onProfile={setProfile}
          requestCamera={requestCamera}
          requestMicrophone={requestMic}
          requestLocation={requestLocation}
          onDone={onOnboarded}
        />
      </div>
    );
  }

  return (
    <div className={`app profile-${profile}`} data-busy={isBusy(state.phase)}>
      {flashOn && <div className="flash" aria-hidden="true" />}

      <header className="topbar">
        <h1>{t.appName}</h1>
        <details className="settings">
          <summary>{t.settings}</summary>
          <div className="settings-body">
            <label>
              {t.chooseLanguage}
              <select value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
                {(Object.keys(LANGUAGE_NAMES) as Language[]).map((l) => (
                  <option key={l} value={l} lang={l}>
                    {LANGUAGE_NAMES[l]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t.answerLanguage}
              <select value={answerLanguage} onChange={(e) => setAnswerLanguage(e.target.value as Language | '')}>
                <option value="">{t.sameAsSpoken}</option>
                {(Object.keys(LANGUAGE_NAMES) as Language[]).map((l) => (
                  <option key={l} value={l} lang={l}>
                    {LANGUAGE_NAMES[l]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t.chooseMode}
              <select value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
                {(['visual', 'hearing', 'ageing', 'default'] as Profile[]).map((p) => (
                  <option key={p} value={p}>
                    {t.modes[p].label}
                  </option>
                ))}
              </select>
            </label>
            <fieldset>
              <legend>{t.speechOwnerLabel}</legend>
              <label className="choice">
                <input
                  type="radio"
                  name="owner"
                  checked={speechOwner === 'app'}
                  onChange={() => changeOwner('app')}
                />
                {t.speechOwnerApp}
              </label>
              <label className="choice">
                <input
                  type="radio"
                  name="owner"
                  checked={speechOwner === 'screen_reader'}
                  onChange={() => changeOwner('screen_reader')}
                />
                {t.speechOwnerReader}
              </label>
            </fieldset>
          </div>
        </details>
      </header>

      {state.proposedProfile && (
        <div className="proposal" role="region" aria-labelledby="profile-proposal">
          <p id="profile-proposal" tabIndex={-1}>
            {t.suggestProfile[state.proposedProfile]}
          </p>
          <div className="button-row">
            <button type="button" className="primary big" onClick={() => resolveProposal(true)}>
              {t.yes}
            </button>
            <button type="button" className="secondary big" onClick={() => resolveProposal(false)}>
              {t.noThanks}
            </button>
          </div>
        </div>
      )}

      <main>
        <GuidanceOutput
          t={t}
          uiLang={language}
          profile={profile}
          phase={state.phase}
          stage={state.stage}
          response={state.response}
          error={state.error}
          stepIndex={state.stepIndex}
          showSimpler={state.showSimpler}
          speechRate={speechRate}
          textScale={textScale}
          helpOffer={helpOffer}
          onRepeat={repeat}
          onToggleSimpler={toggleSimpler}
          onNextStep={() => dispatch({ type: 'NEXT_STEP' })}
          onPrevStep={() => dispatch({ type: 'PREV_STEP' })}
          onConfirm={confirm}
          onRetry={retry}
          onCancel={cancel}
          onHelp={getHelp}
          onSpeechRate={setSpeechRate}
          onTextScale={setTextScale}
        />
        <CameraView
          videoRef={videoRef}
          t={t}
          phase={state.phase}
          hint={hint}
          stableFrames={stableFrames}
          requiredStable={REQUIRED_STABLE_FRAMES}
          torchAvailable={torchAvailable}
          torchOn={torchOn}
          onTorch={toggleTorch}
          onReadSign={readSign}
          onCancel={cancel}
        />
        <VoiceControl
          t={t}
          lang={language}
          phase={state.phase}
          micAvailable={micAvailable}
          onStartVoice={startVoice}
          onStopVoice={stopVoice}
          onAsk={ask}
        />
      </main>
    </div>
  );
}
