import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { announcer } from '../accessibility/announcer';
import { focusElement } from '../accessibility/focusManager';
import { LANGUAGE_NAMES, STRINGS } from '../i18n';
import type { Language, Profile } from '../services/api';

type PermState = 'pending' | 'granted' | 'denied';

interface Props {
  language: Language;
  profile: Profile;
  onLanguage: (l: Language) => void;
  onProfile: (p: Profile) => void;
  requestCamera: () => Promise<boolean>;
  requestMicrophone: () => Promise<boolean>;
  requestLocation: () => Promise<boolean>;
  onDone: () => void;
}

const PROFILES: Profile[] = ['visual', 'hearing', 'ageing', 'default'];

export function PermissionScreen(props: Props) {
  const t = STRINGS[props.language];
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [perms, setPerms] = useState<Record<'camera' | 'microphone' | 'location', PermState>>({
    camera: 'pending',
    microphone: 'pending',
    location: 'pending',
  });
  const [working, setWorking] = useState(false);

  useEffect(() => focusElement(headingRef.current), []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setWorking(true);
    // Ask one at a time: stacked Chrome prompts are confusing with TalkBack.
    const steps = [
      ['camera', props.requestCamera],
      ['microphone', props.requestMicrophone],
      ['location', props.requestLocation],
    ] as const;
    const results: Partial<Record<(typeof steps)[number][0], boolean>> = {};
    for (const [name, request] of steps) {
      const ok = await request().catch(() => false);
      results[name] = ok;
      setPerms((p) => ({ ...p, [name]: ok ? 'granted' : 'denied' }));
      announcer.say(`${t[name]}: ${ok ? t.granted : t.denied}`);
    }
    setWorking(false);
    if (results.camera) props.onDone();
    else announcer.say(t.cameraRequired, { assertive: true });
  }

  return (
    <main className="onboarding" aria-labelledby="onboarding-title">
      <h1 id="onboarding-title" ref={headingRef} tabIndex={-1}>
        {t.appName}
      </h1>
      <p className="lead">{t.tagline}</p>

      <form onSubmit={onSubmit}>
        <fieldset>
          <legend>{t.chooseLanguage}</legend>
          <div className="choice-row">
            {(Object.keys(LANGUAGE_NAMES) as Language[]).map((l) => (
              <label key={l} className="choice" lang={l}>
                <input
                  type="radio"
                  name="language"
                  value={l}
                  checked={props.language === l}
                  onChange={() => props.onLanguage(l)}
                />
                <span>{LANGUAGE_NAMES[l]}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>{t.chooseMode}</legend>
          <div className="choice-column">
            {PROFILES.map((p) => (
              <label key={p} className="choice">
                <input
                  type="radio"
                  name="profile"
                  value={p}
                  checked={props.profile === p}
                  onChange={() => props.onProfile(p)}
                  aria-describedby={`mode-hint-${p}`}
                />
                <span>
                  <strong>{t.modes[p].label}</strong>
                  <span id={`mode-hint-${p}`} className="hint">
                    {t.modes[p].hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <section aria-labelledby="perm-title" className="permissions">
          <h2 id="perm-title">{t.permissionsTitle}</h2>
          <p>{t.permissionsIntro}</p>
          <ul>
            {(['camera', 'microphone', 'location'] as const).map((name) => (
              <li key={name} data-state={perms[name]}>
                {t[name]}: {t[perms[name]]}
              </li>
            ))}
          </ul>
          {perms.camera === 'denied' && (
            <p role="alert" className="error">
              {t.cameraRequired}
            </p>
          )}
          {perms.location === 'denied' && <p className="hint">{t.locationOptional}</p>}
        </section>

        <button type="submit" className="primary big" disabled={working} aria-busy={working}>
          {t.start}
        </button>
      </form>
    </main>
  );
}
