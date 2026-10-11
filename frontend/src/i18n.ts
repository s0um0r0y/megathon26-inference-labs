// UI strings in English, Hindi and Telugu. Hindi/Telugu need native-speaker review.

import type { Language, Profile, Stage } from './services/api';
import type { FramingHint } from './workers/frameQuality.worker';

type Strings = {
  appName: string;
  tagline: string;
  chooseLanguage: string;
  chooseMode: string;
  modes: Record<Profile, { label: string; hint: string }>;
  start: string;
  permissionsTitle: string;
  permissionsIntro: string;
  camera: string;
  microphone: string;
  location: string;
  granted: string;
  denied: string;
  pending: string;
  cameraRequired: string;
  locationOptional: string;
  cameraSection: string;
  readSign: string;
  torchOn: string;
  torchOff: string;
  askSection: string;
  speak: string;
  stopSpeaking: string;
  listening: string;
  typeQuestion: string;
  send: string;
  commonQuestions: string;
  phrases: string[];
  answerSection: string;
  noAnswerYet: string;
  answerReady: string;
  repeat: string;
  simpler: string;
  showOriginal: string;
  moreDetails: string;
  lessDetails: string;
  nextStep: string;
  previousStep: string;
  stepOf: (i: number, n: number) => string;
  caution: string;
  speechSpeed: string;
  textSize: string;
  getHelp: string;
  call: (n: string) => string;
  shareLocation: string;
  cancel: string;
  retry: string;
  confirmYes: string;
  confirmNo: string;
  youAsked: string;
  confidence: Record<'high' | 'medium' | 'low', string>;
  compare: string;
  plainAssistant: string;
  signSaathi: string;
  whatWasRead: string;
  nearby: string;
  stages: Record<Stage, string>;
  framing: Record<FramingHint | 'raise_phone', string>;
  holdStill: string;
  offline: string;
  errorGeneric: string;
  suggestProfile: Record<Exclude<Profile, 'default'>, string>;
  yes: string;
  noThanks: string;
  speechOwnerLabel: string;
  speechOwnerApp: string;
  speechOwnerReader: string;
  settings: string;
  answerLanguage: string;
  sameAsSpoken: string;
};

const en: Strings = {
  appName: 'SignSaathi',
  tagline: 'Point your phone at a sign and ask about it.',
  chooseLanguage: 'Language',
  chooseMode: 'How should I give answers?',
  modes: {
    visual: { label: 'Speak everything', hint: 'Voice first, with camera aiming help' },
    hearing: { label: 'Captions and vibration', hint: 'No sound needed' },
    ageing: { label: 'Large and slow', hint: 'Big text, one step at a time' },
    default: { label: 'Standard', hint: 'Short spoken and written answers' },
  },
  start: 'Start',
  permissionsTitle: 'Allow access',
  permissionsIntro: 'SignSaathi needs the camera to read signs, the microphone to hear your question, and location to find nearby stops.',
  camera: 'Camera',
  microphone: 'Microphone',
  location: 'Location',
  granted: 'allowed',
  denied: 'blocked',
  pending: 'not yet asked',
  cameraRequired: 'The camera is needed to read signs. Allow it in Chrome site settings, then try again.',
  locationOptional: 'Location is optional. Without it I cannot say what is nearby.',
  cameraSection: 'Camera',
  readSign: 'Read sign',
  torchOn: 'Turn torch on',
  torchOff: 'Turn torch off',
  askSection: 'Ask',
  speak: 'Ask by voice',
  stopSpeaking: 'Stop and send',
  listening: 'Listening. Tap again when you finish.',
  typeQuestion: 'Type your question',
  send: 'Ask',
  commonQuestions: 'Common questions',
  phrases: [
    'What does this sign say?',
    'Which bus goes from here?',
    'Is this shop open?',
    'What is the signal showing?',
    'Where is the nearest bus stop?',
  ],
  answerSection: 'Answer',
  noAnswerYet: 'Ask a question or tap Read sign.',
  answerReady: 'Answer ready.',
  repeat: 'Repeat',
  simpler: 'Explain simpler',
  showOriginal: 'Show full answer',
  moreDetails: 'More details',
  lessDetails: 'Hide details',
  nextStep: 'Next step',
  previousStep: 'Previous step',
  stepOf: (i, n) => `Step ${i} of ${n}`,
  caution: 'Caution',
  speechSpeed: 'Speech speed',
  textSize: 'Text size',
  getHelp: 'Get help from a person',
  call: (n) => `Call ${n}`,
  shareLocation: 'Send my location by SMS',
  cancel: 'Cancel',
  retry: 'Try again',
  confirmYes: 'Yes, that is right',
  confirmNo: 'No, ask again',
  youAsked: 'I heard',
  confidence: { high: 'Sure', medium: 'Fairly sure', low: 'Not sure' },
  compare: 'Compare with a plain assistant',
  plainAssistant: 'Plain assistant',
  signSaathi: 'SignSaathi',
  whatWasRead: 'Text on the sign',
  nearby: 'Nearby',
  stages: {
    received: 'Sending',
    listening: 'Understanding your question',
    reading: 'Reading the sign',
    locating: 'Checking what is nearby',
    translating: 'Translating',
    thinking: 'Working out the answer',
    checking: 'Checking the answer',
    speaking: 'Preparing speech',
    done: 'Done',
  },
  framing: {
    good: 'Good. Hold still.',
    too_dark: 'Too dark. Turn on the torch or find more light.',
    too_bright: 'Too bright. Tilt the phone away from the light.',
    blurry: 'Blurry. Hold the phone steady.',
    moving: 'Hold still.',
    no_text: 'No sign found. Move the phone slowly.',
    move_up: 'Move the phone up. The top is cut off.',
    move_down: 'Move the phone down. The bottom is cut off.',
    move_left: 'Move the phone left.',
    move_right: 'Move the phone right.',
    move_closer: 'Move closer to the sign.',
    raise_phone: 'Raise the phone. It is pointing at the ground.',
  },
  holdStill: 'Hold still, taking the photo.',
  offline: 'No internet connection. I will try again when you are back online.',
  errorGeneric: 'Something went wrong. Please try again.',
  suggestProfile: {
    visual: 'Shall I speak everything and help you aim the camera?',
    hearing: 'Shall I show captions and vibrate instead of using sound?',
    ageing: 'Shall I use bigger text and speak slower?',
  },
  yes: 'Yes',
  noThanks: 'No, thanks',
  speechOwnerLabel: 'Who reads answers aloud',
  speechOwnerApp: 'SignSaathi voice',
  speechOwnerReader: 'My screen reader',
  settings: 'Settings',
  answerLanguage: 'Answer language',
  sameAsSpoken: 'Same as my language',
};

const hi: Strings = {
  ...en,
  tagline: 'फ़ोन को किसी बोर्ड की तरफ़ करें और उसके बारे में पूछें।',
  chooseLanguage: 'भाषा',
  chooseMode: 'मैं जवाब कैसे दूँ?',
  modes: {
    visual: { label: 'सब कुछ बोलकर', hint: 'आवाज़ से, कैमरा सही दिशा में रखने में मदद' },
    hearing: { label: 'लिखकर और कंपन से', hint: 'आवाज़ की ज़रूरत नहीं' },
    ageing: { label: 'बड़ा और धीमा', hint: 'बड़े अक्षर, एक बार में एक कदम' },
    default: { label: 'सामान्य', hint: 'छोटे बोले और लिखे जवाब' },
  },
  start: 'शुरू करें',
  permissionsTitle: 'अनुमति दें',
  permissionsIntro: 'बोर्ड पढ़ने के लिए कैमरा, सवाल सुनने के लिए माइक्रोफ़ोन, और पास के स्टॉप ढूँढने के लिए लोकेशन चाहिए।',
  camera: 'कैमरा',
  microphone: 'माइक्रोफ़ोन',
  location: 'लोकेशन',
  granted: 'अनुमति है',
  denied: 'बंद है',
  pending: 'अभी नहीं पूछा',
  cameraRequired: 'बोर्ड पढ़ने के लिए कैमरा ज़रूरी है। Chrome की साइट सेटिंग में अनुमति दें और फिर कोशिश करें।',
  locationOptional: 'लोकेशन ज़रूरी नहीं है। इसके बिना मैं पास की जगहें नहीं बता पाऊँगा।',
  cameraSection: 'कैमरा',
  readSign: 'बोर्ड पढ़ें',
  torchOn: 'टॉर्च चालू करें',
  torchOff: 'टॉर्च बंद करें',
  askSection: 'पूछें',
  speak: 'बोलकर पूछें',
  stopSpeaking: 'रोकें और भेजें',
  listening: 'सुन रहा हूँ। बोलने के बाद फिर से दबाएँ।',
  typeQuestion: 'अपना सवाल लिखें',
  send: 'पूछें',
  commonQuestions: 'आम सवाल',
  phrases: [
    'इस बोर्ड पर क्या लिखा है?',
    'यहाँ से कौन सी बस जाती है?',
    'क्या यह दुकान खुली है?',
    'सिग्नल क्या दिखा रहा है?',
    'सबसे पास का बस स्टॉप कहाँ है?',
  ],
  answerSection: 'जवाब',
  noAnswerYet: 'सवाल पूछें या बोर्ड पढ़ें दबाएँ।',
  answerReady: 'जवाब तैयार है।',
  repeat: 'फिर से सुनें',
  simpler: 'आसान भाषा में',
  showOriginal: 'पूरा जवाब दिखाएँ',
  moreDetails: 'और जानकारी',
  lessDetails: 'जानकारी छिपाएँ',
  nextStep: 'अगला कदम',
  previousStep: 'पिछला कदम',
  stepOf: (i, n) => `कदम ${i} / ${n}`,
  caution: 'सावधानी',
  speechSpeed: 'बोलने की गति',
  textSize: 'अक्षरों का आकार',
  getHelp: 'किसी व्यक्ति से मदद लें',
  call: (n) => `${n} पर कॉल करें`,
  shareLocation: 'SMS से मेरी लोकेशन भेजें',
  cancel: 'रद्द करें',
  retry: 'फिर से कोशिश करें',
  confirmYes: 'हाँ, सही है',
  confirmNo: 'नहीं, फिर से पूछें',
  youAsked: 'मैंने सुना',
  confidence: { high: 'पक्का', medium: 'लगभग पक्का', low: 'पक्का नहीं' },
  compare: 'सामान्य असिस्टेंट से तुलना',
  plainAssistant: 'सामान्य असिस्टेंट',
  whatWasRead: 'बोर्ड पर लिखा है',
  nearby: 'आसपास',
  stages: {
    received: 'भेज रहा हूँ',
    listening: 'आपका सवाल समझ रहा हूँ',
    reading: 'बोर्ड पढ़ रहा हूँ',
    locating: 'आसपास देख रहा हूँ',
    translating: 'अनुवाद कर रहा हूँ',
    thinking: 'जवाब सोच रहा हूँ',
    checking: 'जवाब जाँच रहा हूँ',
    speaking: 'आवाज़ तैयार कर रहा हूँ',
    done: 'हो गया',
  },
  framing: {
    good: 'ठीक है। स्थिर रखें।',
    too_dark: 'बहुत अँधेरा है। टॉर्च चालू करें।',
    too_bright: 'बहुत रोशनी है। फ़ोन को रोशनी से हटाएँ।',
    blurry: 'धुंधला है। फ़ोन स्थिर रखें।',
    moving: 'स्थिर रखें।',
    no_text: 'कोई बोर्ड नहीं दिखा। फ़ोन धीरे-धीरे घुमाएँ।',
    move_up: 'फ़ोन ऊपर करें। ऊपर का हिस्सा कट रहा है।',
    move_down: 'फ़ोन नीचे करें। नीचे का हिस्सा कट रहा है।',
    move_left: 'फ़ोन बाईं ओर करें।',
    move_right: 'फ़ोन दाईं ओर करें।',
    move_closer: 'बोर्ड के पास जाएँ।',
    raise_phone: 'फ़ोन उठाएँ। यह ज़मीन की तरफ़ है।',
  },
  holdStill: 'स्थिर रखें, फ़ोटो ले रहा हूँ।',
  offline: 'इंटरनेट नहीं है। कनेक्शन आने पर फिर कोशिश करूँगा।',
  errorGeneric: 'कुछ गड़बड़ हुई। कृपया फिर कोशिश करें।',
  suggestProfile: {
    visual: 'क्या मैं सब कुछ बोलकर बताऊँ और कैमरा सही दिशा में रखने में मदद करूँ?',
    hearing: 'क्या मैं आवाज़ की जगह लिखकर और कंपन से बताऊँ?',
    ageing: 'क्या मैं बड़े अक्षर और धीमी आवाज़ इस्तेमाल करूँ?',
  },
  yes: 'हाँ',
  noThanks: 'नहीं, धन्यवाद',
  speechOwnerLabel: 'जवाब कौन पढ़े',
  speechOwnerApp: 'SignSaathi की आवाज़',
  speechOwnerReader: 'मेरा स्क्रीन रीडर',
  settings: 'सेटिंग',
  answerLanguage: 'जवाब की भाषा',
  sameAsSpoken: 'मेरी भाषा में',
};

const te: Strings = {
  ...en,
  tagline: 'ఫోన్‌ను బోర్డు వైపు చూపించి దాని గురించి అడగండి.',
  chooseLanguage: 'భాష',
  chooseMode: 'సమాధానాలు ఎలా ఇవ్వాలి?',
  modes: {
    visual: { label: 'అన్నీ మాటల్లో', hint: 'వాయిస్‌తో, కెమెరాను సరిగ్గా చూపడంలో సహాయం' },
    hearing: { label: 'రాతలో, వైబ్రేషన్‌తో', hint: 'శబ్దం అవసరం లేదు' },
    ageing: { label: 'పెద్దగా, నెమ్మదిగా', hint: 'పెద్ద అక్షరాలు, ఒక్కో అడుగు' },
    default: { label: 'సాధారణం', hint: 'చిన్న మాట, రాత సమాధానాలు' },
  },
  start: 'ప్రారంభించండి',
  permissionsTitle: 'అనుమతి ఇవ్వండి',
  permissionsIntro: 'బోర్డులు చదవడానికి కెమెరా, మీ ప్రశ్న వినడానికి మైక్రోఫోన్, దగ్గరి స్టాప్‌లు కనుగొనడానికి లొకేషన్ కావాలి.',
  camera: 'కెమెరా',
  microphone: 'మైక్రోఫోన్',
  location: 'లొకేషన్',
  granted: 'అనుమతి ఉంది',
  denied: 'బ్లాక్ అయింది',
  pending: 'ఇంకా అడగలేదు',
  cameraRequired: 'బోర్డులు చదవడానికి కెమెరా తప్పనిసరి. Chrome సైట్ సెట్టింగ్స్‌లో అనుమతించి మళ్లీ ప్రయత్నించండి.',
  locationOptional: 'లొకేషన్ తప్పనిసరి కాదు. అది లేకుండా దగ్గర ఏముందో చెప్పలేను.',
  cameraSection: 'కెమెరా',
  readSign: 'బోర్డు చదవండి',
  torchOn: 'టార్చ్ ఆన్ చేయండి',
  torchOff: 'టార్చ్ ఆఫ్ చేయండి',
  askSection: 'అడగండి',
  speak: 'మాటతో అడగండి',
  stopSpeaking: 'ఆపి పంపండి',
  listening: 'వింటున్నాను. పూర్తయ్యాక మళ్లీ నొక్కండి.',
  typeQuestion: 'మీ ప్రశ్న టైప్ చేయండి',
  send: 'అడగండి',
  commonQuestions: 'సాధారణ ప్రశ్నలు',
  phrases: [
    'ఈ బోర్డుపై ఏమి రాసి ఉంది?',
    'ఇక్కడి నుండి ఏ బస్ వెళ్తుంది?',
    'ఈ షాపు తెరిచి ఉందా?',
    'సిగ్నల్ ఏమి చూపిస్తోంది?',
    'దగ్గరలో బస్ స్టాప్ ఎక్కడ ఉంది?',
  ],
  answerSection: 'సమాధానం',
  noAnswerYet: 'ప్రశ్న అడగండి లేదా బోర్డు చదవండి నొక్కండి.',
  answerReady: 'సమాధానం సిద్ధం.',
  repeat: 'మళ్లీ వినండి',
  simpler: 'సులభంగా చెప్పండి',
  showOriginal: 'పూర్తి సమాధానం చూపండి',
  moreDetails: 'మరిన్ని వివరాలు',
  lessDetails: 'వివరాలు దాచండి',
  nextStep: 'తదుపరి అడుగు',
  previousStep: 'మునుపటి అడుగు',
  stepOf: (i, n) => `అడుగు ${i} / ${n}`,
  caution: 'జాగ్రత్త',
  speechSpeed: 'మాట వేగం',
  textSize: 'అక్షరాల పరిమాణం',
  getHelp: 'ఒక వ్యక్తి సహాయం తీసుకోండి',
  call: (n) => `${n}కు కాల్ చేయండి`,
  shareLocation: 'SMS ద్వారా నా లొకేషన్ పంపండి',
  cancel: 'రద్దు చేయండి',
  retry: 'మళ్లీ ప్రయత్నించండి',
  confirmYes: 'అవును, సరైనదే',
  confirmNo: 'కాదు, మళ్లీ అడుగుతాను',
  youAsked: 'నేను విన్నది',
  confidence: { high: 'ఖచ్చితం', medium: 'దాదాపు ఖచ్చితం', low: 'ఖచ్చితం కాదు' },
  compare: 'సాధారణ అసిస్టెంట్‌తో పోల్చండి',
  plainAssistant: 'సాధారణ అసిస్టెంట్',
  whatWasRead: 'బోర్డుపై ఉన్నది',
  nearby: 'దగ్గరలో',
  stages: {
    received: 'పంపుతున్నాను',
    listening: 'మీ ప్రశ్న అర్థం చేసుకుంటున్నాను',
    reading: 'బోర్డు చదువుతున్నాను',
    locating: 'దగ్గర ఏముందో చూస్తున్నాను',
    translating: 'అనువదిస్తున్నాను',
    thinking: 'సమాధానం ఆలోచిస్తున్నాను',
    checking: 'సమాధానం సరిచూస్తున్నాను',
    speaking: 'మాట సిద్ధం చేస్తున్నాను',
    done: 'పూర్తయింది',
  },
  framing: {
    good: 'బాగుంది. కదలకుండా ఉంచండి.',
    too_dark: 'చాలా చీకటిగా ఉంది. టార్చ్ ఆన్ చేయండి.',
    too_bright: 'చాలా వెలుతురు. ఫోన్‌ను వెలుతురు నుండి తిప్పండి.',
    blurry: 'మసకగా ఉంది. ఫోన్‌ను కదలకుండా పట్టుకోండి.',
    moving: 'కదలకుండా ఉంచండి.',
    no_text: 'బోర్డు కనిపించలేదు. ఫోన్‌ను నెమ్మదిగా తిప్పండి.',
    move_up: 'ఫోన్‌ను పైకి జరపండి. పై భాగం కట్ అవుతోంది.',
    move_down: 'ఫోన్‌ను కిందికి జరపండి. కింది భాగం కట్ అవుతోంది.',
    move_left: 'ఫోన్‌ను ఎడమ వైపు జరపండి.',
    move_right: 'ఫోన్‌ను కుడి వైపు జరపండి.',
    move_closer: 'బోర్డుకు దగ్గరగా వెళ్లండి.',
    raise_phone: 'ఫోన్‌ను పైకి ఎత్తండి. అది నేల వైపు ఉంది.',
  },
  holdStill: 'కదలకుండా ఉంచండి, ఫోటో తీస్తున్నాను.',
  offline: 'ఇంటర్నెట్ లేదు. కనెక్షన్ వచ్చాక మళ్లీ ప్రయత్నిస్తాను.',
  errorGeneric: 'ఏదో తప్పు జరిగింది. దయచేసి మళ్లీ ప్రయత్నించండి.',
  suggestProfile: {
    visual: 'అన్నీ మాటల్లో చెప్పి, కెమెరా చూపడంలో సహాయం చేయనా?',
    hearing: 'శబ్దానికి బదులు రాతలో, వైబ్రేషన్‌తో చూపించనా?',
    ageing: 'పెద్ద అక్షరాలు, నెమ్మదైన మాట వాడనా?',
  },
  yes: 'అవును',
  noThanks: 'వద్దు, ధన్యవాదాలు',
  speechOwnerLabel: 'సమాధానాలు ఎవరు చదవాలి',
  speechOwnerApp: 'SignSaathi గొంతు',
  speechOwnerReader: 'నా స్క్రీన్ రీడర్',
  settings: 'సెట్టింగ్స్',
  answerLanguage: 'సమాధాన భాష',
  sameAsSpoken: 'నా భాషలోనే',
};

export const STRINGS: Record<Language, Strings> = { en, hi, te };
export const LANGUAGE_NAMES: Record<Language, string> = { en: 'English', hi: 'हिन्दी', te: 'తెలుగు' };
export type { Strings };
