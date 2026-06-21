let csrfToken = '';
let activeMode = 'shops';
const APPEARANCE_KEY = 'teleapo-ui-mode';

const pageTitle = document.querySelector('#pageTitle');
const statusBox = document.querySelector('#status');
const rows = document.querySelector('#rows');
const summary = document.querySelector('#summary');
const sheetName = document.querySelector('#sheetName');
const tabButtons = document.querySelectorAll('.tabButton');
const forms = document.querySelectorAll('.searchForm');
const shopHead = document.querySelector('#shopHead');
const eventHead = document.querySelector('#eventHead');
const jobHead = document.querySelector('#jobHead');
const appearanceToggle = document.querySelector('#appearanceToggle');

const shopForm = document.querySelector('#shopForm');
const eventForm = document.querySelector('#eventForm');
const jobForm = document.querySelector('#jobForm');
const shopButton = document.querySelector('#submitButton');
const eventButton = document.querySelector('#eventSubmitButton');
const jobButton = document.querySelector('#jobSubmitButton');
const shopIndustrySelect = document.querySelector('#shopIndustry');
const shopKeywordInput = document.querySelector('#keyword');
const shopPrefectureSelect = document.querySelector('#shopPrefecture');
const shopCitySelect = document.querySelector('#shopCity');
const shopAreaInput = document.querySelector('#area');
const resultsInput = document.querySelector('#results');
const startInput = document.querySelector('#start');
const eventResultsInput = document.querySelector('#eventResults');
const eventStartInput = document.querySelector('#eventStart');
const jobTargetSelect = document.querySelector('#jobTarget');
const jobKeywordInput = document.querySelector('#jobKeyword');
const jobResultsInput = document.querySelector('#jobResults');
const jobStartInput = document.querySelector('#jobStart');
const bulkCrmButton = document.querySelector('#bulkCrmButton');
let latestShopItems = [];
applyAppearance(localStorage.getItem(APPEARANCE_KEY) || 'dark');
const CRM_STORAGE_KEY = 'teleapo-crm-leads-v1';

const jobTargetKeywords = {
  custom: '',
  intangible: '法人営業 無形商材',
  saas: 'SaaS 法人営業',
  webMarketing: 'Web広告 マーケティング支援 営業',
  recruiting: '人材紹介 採用支援 営業',
  consulting: 'コンサルティング 営業',
  insurance: '保険 金融 営業',
  realEstate: '不動産 投資 営業',
  beauty: '美容室 美容サロン',
  clinic: '整体 整骨院'
};

const shopIndustryKeywords = {
  custom: '',
  beautySalon: '美容室',
  barber: '理容室',
  eyelash: 'アイラッシュ',
  nail: 'ネイルサロン',
  esthetic: 'エステサロン',
  relaxation: 'リラクゼーション',
  seitai: '整体',
  seikotsu: '整骨院',
  acupuncture: '鍼灸院',
  clinic: 'クリニック',
  dental: '歯科医院',
  dermatology: '美容皮膚科',
  personalGym: 'パーソナルジム',
  pilates: 'ピラティス',
  yoga: 'ヨガスタジオ',
  dance: 'ダンススクール',
  juku: '学習塾',
  english: '英会話スクール',
  programming: 'プログラミング教室',
  restaurant: '飲食店',
  izakaya: '居酒屋',
  yakiniku: '焼肉',
  ramen: 'ラーメン',
  cafe: 'カフェ',
  bar: 'バー',
  hotel: 'ホテル',
  realEstate: '不動産会社',
  renovation: 'リフォーム',
  carDealer: '中古車販売',
  carRepair: '自動車整備',
  petSalon: 'ペットサロン',
  veterinary: '動物病院',
  cleaning: 'ハウスクリーニング',
  funeral: '葬儀社',
  photoStudio: '写真館',
  wedding: '結婚相談所',
  nursery: '保育園',
  care: '介護施設',
  dayService: 'デイサービス'
};

const areaOptions = {
  北海道: ['札幌市', '旭川市', '函館市', '帯広市'],
  宮城県: ['仙台市', '石巻市', '大崎市'],
  東京都: ['千代田区', '中央区', '港区', '新宿区', '渋谷区', '豊島区', '品川区', '目黒区', '世田谷区', '中野区', '杉並区', '文京区', '台東区', '墨田区', '江東区', '大田区', '練馬区', '板橋区', '北区', '荒川区', '足立区', '葛飾区', '江戸川区', '八王子市', '立川市', '町田市', '武蔵野市'],
  神奈川県: ['横浜市', '川崎市', '相模原市', '藤沢市', '鎌倉市', '厚木市', '横須賀市'],
  埼玉県: ['さいたま市', '川口市', '川越市', '越谷市', '所沢市', '大宮区', '浦和区'],
  千葉県: ['千葉市', '船橋市', '柏市', '松戸市', '市川市', '浦安市', '成田市'],
  茨城県: ['水戸市', 'つくば市', '土浦市'],
  栃木県: ['宇都宮市', '小山市', '足利市'],
  群馬県: ['前橋市', '高崎市', '太田市'],
  新潟県: ['新潟市', '長岡市', '上越市'],
  長野県: ['長野市', '松本市', '上田市', '佐久市', '飯田市'],
  静岡県: ['静岡市', '浜松市', '沼津市', '富士市'],
  愛知県: ['名古屋市', '豊橋市', '岡崎市', '一宮市', '豊田市', '春日井市'],
  岐阜県: ['岐阜市', '大垣市', '多治見市'],
  三重県: ['津市', '四日市市', '鈴鹿市'],
  石川県: ['金沢市', '小松市', '白山市'],
  京都府: ['京都市', '宇治市', '亀岡市'],
  大阪府: ['大阪市', '堺市', '東大阪市', '枚方市', '豊中市', '吹田市', '高槻市', '茨木市'],
  兵庫県: ['神戸市', '姫路市', '西宮市', '尼崎市', '明石市'],
  奈良県: ['奈良市', '橿原市', '生駒市'],
  岡山県: ['岡山市', '倉敷市', '津山市'],
  広島県: ['広島市', '福山市', '呉市'],
  香川県: ['高松市', '丸亀市'],
  愛媛県: ['松山市', '今治市'],
  福岡県: ['福岡市', '北九州市', '久留米市', '飯塚市'],
  熊本県: ['熊本市', '八代市'],
  鹿児島県: ['鹿児島市', '霧島市'],
  沖縄県: ['那覇市', '沖縄市', '浦添市']
};

const configResponse = await fetch('/api/config');
const appConfig = await configResponse.json();
csrfToken = appConfig.csrfToken;
resultsInput.max = appConfig.maxResultsPerRun;
eventResultsInput.max = appConfig.maxResultsPerRun;
jobResultsInput.max = appConfig.maxResultsPerRun;
sheetName.textContent = `追記先: ${appConfig.sheetName}`;

for (const button of tabButtons) {
  button.addEventListener('click', () => setMode(button.dataset.mode));
}

initializeAreaSelectors();
appearanceToggle?.addEventListener('click', toggleAppearance);

shopIndustrySelect.addEventListener('change', () => {
  const keyword = shopIndustryKeywords[shopIndustrySelect.value];
  if (keyword) {
    shopKeywordInput.value = keyword;
    startInput.value = '1';
  }
});

shopPrefectureSelect.addEventListener('change', () => {
  populateCityOptions(shopPrefectureSelect.value);
  updateAreaFromSelectors();
  startInput.value = '1';
});

shopCitySelect.addEventListener('change', () => {
  updateAreaFromSelectors();
  startInput.value = '1';
});

bulkCrmButton?.addEventListener('click', addVisibleShopsToCrm);

jobTargetSelect.addEventListener('change', () => {
  const keyword = jobTargetKeywords[jobTargetSelect.value];
  if (keyword) {
    jobKeywordInput.value = keyword;
    jobStartInput.value = '1';
  }
});

shopForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(shopForm);
  const payload = {
    keyword: formData.get('keyword'),
    area: formData.get('area'),
    results: Number(formData.get('results')),
    start: Number(formData.get('start')),
    sort: formData.get('sort'),
    append: formData.get('append') === 'on'
  };
  await runSearch({
    endpoint: '/api/search-and-append',
    payload,
    button: shopButton,
    render: renderShopRows,
    afterSuccess: (data) => {
      summary.textContent = `${payload.start}件目から${data.count}件取得 / ${data.appended}件追記 / ${data.skipped}件スキップ`;
      startInput.value = String(payload.start + payload.results);
      setStatus(`完了しました。次は${startInput.value}件目から検索できます。`);
    }
  });
});

eventForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(eventForm);
  const payload = {
    keyword: formData.get('keyword'),
    area: formData.get('area'),
    source: formData.get('source'),
    results: Number(formData.get('results')),
    start: Number(formData.get('start')),
    futureOnly: formData.get('futureOnly') === 'on',
    append: formData.get('append') === 'on'
  };
  await runSearch({
    endpoint: '/api/events/search-and-append',
    payload,
    button: eventButton,
    render: renderEventRows,
    afterSuccess: (data) => {
      summary.textContent = `${payload.start}件目から${data.count}件取得 / ${data.appended}件追記 / ${data.skipped}件スキップ`;
      eventStartInput.value = String(payload.start + payload.results);
      setStatus(`完了しました。次は${eventStartInput.value}件目から検索できます。`);
    }
  });
});

jobForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(jobForm);
  const payload = {
    keyword: formData.get('keyword'),
    area: formData.get('area'),
    source: formData.get('source'),
    results: Number(formData.get('results')),
    start: Number(formData.get('start')),
    append: formData.get('append') === 'on'
  };
  await runSearch({
    endpoint: '/api/jobs/search-and-append',
    payload,
    button: jobButton,
    render: renderJobRows,
    afterSuccess: (data) => {
      summary.textContent = `${payload.start}件目から${data.count}件取得 / ${data.appended}件追記 / ${data.skipped}件スキップ`;
      jobStartInput.value = String(payload.start + payload.results);
      setStatus(`完了しました。次は${jobStartInput.value}件目から検索できます。`);
    }
  });
});

prepareBrowserVoices();

function setMode(mode) {
  activeMode = mode;
  for (const button of tabButtons) {
    button.classList.toggle('is-active', button.dataset.mode === mode);
  }
  for (const form of forms) {
    form.classList.toggle('is-hidden', form.dataset.mode !== mode);
  }

  const labels = {
    shops: {
      title: '店舗情報取得',
      sheet: appConfig.sheetName
    },
    events: {
      title: 'イベント情報取得',
      sheet: appConfig.eventSheetName
    },
    jobs: {
      title: '求人掲載店舗取得',
      sheet: appConfig.jobSheetName
    }
  };
  pageTitle.textContent = labels[mode].title;
  sheetName.textContent = `追記先: ${labels[mode].sheet}`;
  shopHead.classList.toggle('is-hidden', mode !== 'shops');
  eventHead.classList.toggle('is-hidden', mode !== 'events');
  jobHead.classList.toggle('is-hidden', mode !== 'jobs');
  if (bulkCrmButton) {
    bulkCrmButton.hidden = mode !== 'shops' || latestShopItems.length === 0;
  }
  rows.replaceChildren();
  summary.textContent = '';
  setStatus('');
}

function initializeAreaSelectors() {
  const prefectures = Object.keys(areaOptions);
  shopPrefectureSelect.replaceChildren(...prefectures.map((prefecture) => optionFor(prefecture, prefecture)));
  shopPrefectureSelect.value = '東京都';
  populateCityOptions('東京都');
  shopCitySelect.value = '新宿区';
  updateAreaFromSelectors();
}

function applyAppearance(mode) {
  const nextMode = mode === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = nextMode;
  localStorage.setItem(APPEARANCE_KEY, nextMode);
  if (appearanceToggle) {
    appearanceToggle.textContent = nextMode === 'dark' ? 'ライト' : 'ダーク';
    appearanceToggle.setAttribute('aria-pressed', String(nextMode === 'light'));
  }
}

function toggleAppearance() {
  applyAppearance(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

function populateCityOptions(prefecture) {
  const cities = areaOptions[prefecture] || [];
  const options = [
    optionFor('', '指定なし'),
    ...cities.map((city) => optionFor(city, city))
  ];
  shopCitySelect.replaceChildren(...options);
}

function updateAreaFromSelectors() {
  const prefecture = shopPrefectureSelect.value;
  const city = shopCitySelect.value;
  shopAreaInput.value = city ? `${prefecture}${city}` : prefecture;
}

function optionFor(value, label) {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  return option;
}

async function runSearch({ endpoint, payload, button, render, afterSuccess }) {
  setBusy(button, true);
  setStatus('検索中です...');
  rows.replaceChildren();
  summary.textContent = '';

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-csrf-token': csrfToken
      },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || '処理に失敗しました。');
    }

    render(data.items);
    afterSuccess(data);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function renderShopRows(items) {
  const labels = ['会社名', '電話番号', '住所'];
  latestShopItems = items;
  if (bulkCrmButton) {
    bulkCrmButton.hidden = items.length === 0;
  }
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const tr = rowFor([item.name, phoneLinkHtml(item.tel), item.address], labels);
    const td = document.createElement('td');
    td.dataset.label = 'CRM';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'miniButton';
    button.textContent = isShopInCrm(item) ? '追加済み' : 'CRM追加';
    button.disabled = isShopInCrm(item);
    button.addEventListener('click', () => {
      addShopToCrm(item);
      button.textContent = '追加済み';
      button.disabled = true;
    });
    td.append(button);
    tr.append(td);
    fragment.append(tr);
  }
  rows.replaceChildren(fragment);
}

function addVisibleShopsToCrm() {
  const result = addShopsToCrm(latestShopItems);
  if (result.added > 0) {
    renderShopRows(latestShopItems);
  }
  setStatus(`表示中の店舗をCRMへ反映しました。追加 ${result.added}件 / 重複スキップ ${result.skipped}件`);
}

function addShopsToCrm(items) {
  const leads = loadCrmLeads();
  const seen = new Set(leads.map((lead) => lead.sourceKey).filter(Boolean));
  const seenNamePhones = new Set(leads.map((lead) => `${lead.name}|${lead.phone}`));
  const now = new Date().toISOString();
  const additions = [];
  let skipped = 0;
  for (const item of items) {
    const key = crmShopKey(item);
    const namePhone = `${item.name}|${item.tel}`;
    if (seen.has(key) || seenNamePhones.has(namePhone)) {
      skipped += 1;
      continue;
    }
    seen.add(key);
    seenNamePhones.add(namePhone);
    additions.push(shopToCrmLead(item, now));
  }
  if (additions.length > 0) {
    localStorage.setItem(CRM_STORAGE_KEY, JSON.stringify([...additions, ...leads]));
  }
  return { added: additions.length, skipped };
}


function addShopToCrm(item) {
  const leads = loadCrmLeads();
  const key = crmShopKey(item);
  if (leads.some((lead) => lead.sourceKey === key || (lead.name === item.name && lead.phone === item.tel))) {
    setStatus(`${item.name} はすでにCRMに入っています。`);
    return;
  }
  const now = new Date().toISOString();
  leads.unshift(shopToCrmLead(item, now));
  localStorage.setItem(CRM_STORAGE_KEY, JSON.stringify(leads));
  setStatus(`${item.name} をCRMに追加しました。右上の「CRMを開く」から確認できます。`);
}

function shopToCrmLead(item, updatedAt) {
  return {
    id: crypto.randomUUID(),
    name: item.name || '',
    phone: item.tel || '',
    address: item.address || '',
    person: '',
    status: 'new',
    nextCall: '',
    memo: `店舗取得から追加 / ジャンル: ${item.genre || '-'} / 最寄り駅: ${item.nearestStation || '-'}`,
    sourceKey: crmShopKey(item),
    source: '店舗情報取得',
    updatedAt
  };
}

function isShopInCrm(item) {

  const leads = loadCrmLeads();
  const key = crmShopKey(item);
  return leads.some((lead) => lead.sourceKey === key || (lead.name === item.name && lead.phone === item.tel));
}

function loadCrmLeads() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CRM_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function crmShopKey(item) {
  return [item.uid, item.gid, item.name, item.tel, item.address].filter(Boolean).join('|');
}

function renderEventRows(items) {
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    fragment.append(rowFor([item.title, formatDate(item.startedAt), item.place, item.address, `${item.accepted || 0}/${item.limit || '-'}`], ['イベント名', '開催開始', '会場', '住所', '参加']));
  }
  rows.replaceChildren(fragment);
}

function renderJobRows(items) {
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    fragment.append(rowFor([item.businessName, item.listingCompany, item.title, item.workArea, item.payment], ['店舗名・会社名', '掲載企業', '求人タイトル', '勤務地', '給与']));
  }
  rows.replaceChildren(fragment);
}

function rowFor(values, labels = []) {
  const tr = document.createElement('tr');
  values.forEach((value, index) => {
    const td = document.createElement('td');
    td.dataset.label = labels[index] || '';
    if (typeof value === 'string' && value.startsWith('<a ')) {
      td.innerHTML = value;
    } else {
      td.textContent = value || '-';
    }
    tr.append(td);
  });
  return tr;
}

function phoneLinkHtml(phone) {
  const raw = String(phone || '').trim();
  if (!raw) return '-';
  const tel = raw.replace(/[^0-9+]/g, '');
  if (!tel) return raw;
  return `<a class="phoneLink" href="tel:${tel}">${escapeHtml(raw)}</a>`;
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatDate(value) {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function setBusy(button, isBusy) {
  button.disabled = isBusy;
  button.textContent = isBusy
    ? '処理中...'
    : button.dataset.label || defaultButtonLabel();
}

function defaultButtonLabel() {
  if (activeMode === 'events') {
    return 'イベント検索して追記';
  }
  if (activeMode === 'jobs') {
    return '求人掲載店舗を検索して追記';
  }
  return '検索して追記';
}

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.dataset.state = isError ? 'error' : 'normal';
}

const SEARCH_VOICE_KEY = 'teleapo-search-rem-voice-enabled';
const searchAssistantMessage = document.querySelector('#searchAssistantMessage');
const searchAssistantTalk = document.querySelector('#searchAssistantTalk');
const searchVoiceToggle = document.querySelector('#searchVoiceToggle');
let searchVoiceEnabled = localStorage.getItem(SEARCH_VOICE_KEY) === 'true';
let currentSearchVoiceAudio = null;
let currentSearchVoiceUrl = '';
let searchVoiceRequestId = 0;

if (searchAssistantMessage && searchAssistantTalk && searchVoiceToggle) {
  updateSearchVoiceButton();
  setTimeout(() => saySearchGreeting(randomSearchGreeting()), 450);
  searchAssistantTalk.addEventListener('click', () => saySearchGreeting(randomSearchGreeting(), true));
  searchVoiceToggle.addEventListener('click', () => {
    searchVoiceEnabled = !searchVoiceEnabled;
    localStorage.setItem(SEARCH_VOICE_KEY, String(searchVoiceEnabled));
    updateSearchVoiceButton();
    saySearchGreeting(searchVoiceEnabled ? '音声をオンにしました。検索からCRM追加まで、レムが案内します。' : '音声をオフにしました。文字では引き続きそばにいます。', true);
  });
}

function randomSearchGreeting() {
  if (activeMode === 'events') {
    return 'イベント検索ですね。ビジネス交流会っぽいものは、シート側で色も付きます。';
  }
  if (activeMode === 'jobs') {
    return '求人掲載店舗の検索ですね。気になる会社はあとでCRMにまとめましょう。';
  }
  return '店舗検索ですね。検索結果のCRM追加ボタンで、見込み客リストへ送れます。';
}

function saySearchGreeting(message, forceVoice = false) {
  if (!searchAssistantMessage) return;
  searchAssistantMessage.textContent = message;
  if (searchVoiceEnabled || forceVoice) {
    stopCurrentSearchVoice();
    const requestId = ++searchVoiceRequestId;
    speakSearchWithVoicevox(message, requestId).catch(() => {
      if (requestId === searchVoiceRequestId) speakSearchWithBrowserVoice(message);
    });
  }
}

async function speakSearchWithVoicevox(message, requestId) {
  if (!csrfToken) throw new Error('csrf token is not ready');
  const response = await fetch('/api/voicevox', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-csrf-token': csrfToken
    },
    body: JSON.stringify({ text: message })
  });
  if (!response.ok) throw new Error('VOICEVOX failed');
  const blob = await response.blob();
  if (requestId !== searchVoiceRequestId) return;
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentSearchVoiceAudio = audio;
  currentSearchVoiceUrl = url;
  const cleanup = () => {
    if (currentSearchVoiceAudio === audio) currentSearchVoiceAudio = null;
    if (currentSearchVoiceUrl === url) currentSearchVoiceUrl = '';
    URL.revokeObjectURL(url);
  };
  audio.addEventListener('ended', cleanup, { once: true });
  audio.addEventListener('error', cleanup, { once: true });
  await audio.play();
}


function getPreferredJapaneseVoice() {
  if (!('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const isJapanese = (voice) => /^ja[-_]/i.test(voice.lang || '') || /Japanese|日本語|Kyoko|Nanami|Haruka|Sayaka|Hina/i.test(voice.name || '');
  const avoidMale = (voice) => !/Otoya|Ichiro|Keita|男性|male/i.test(voice.name || '');
  const candidates = voices.filter((voice) => isJapanese(voice) && avoidMale(voice));
  const preferredNames = ['Kyoko', 'Nanami', 'Haruka', 'Sayaka', 'Hina', 'Google 日本語', 'Japanese'];
  for (const name of preferredNames) {
    const found = candidates.find((voice) => (voice.name || '').includes(name));
    if (found) return found;
  }
  return candidates[0] || voices.find(isJapanese) || null;
}

function prepareBrowserVoices() {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

function stopCurrentSearchVoice() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (currentSearchVoiceAudio) {
    currentSearchVoiceAudio.pause();
    currentSearchVoiceAudio.currentTime = 0;
    currentSearchVoiceAudio = null;
  }
  if (currentSearchVoiceUrl) {
    URL.revokeObjectURL(currentSearchVoiceUrl);
    currentSearchVoiceUrl = '';
  }
}

function speakSearchWithBrowserVoice(message) {
  if (!('speechSynthesis' in window)) return;
  stopCurrentSearchVoice();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = 'ja-JP';
  const preferredVoice = getPreferredJapaneseVoice();
  if (preferredVoice) utterance.voice = preferredVoice;
  utterance.rate = 0.94;
  utterance.pitch = 1.42;
  utterance.volume = 1;
  window.speechSynthesis.speak(utterance);
}

function updateSearchVoiceButton() {
  if (searchVoiceToggle) {
    searchVoiceToggle.textContent = searchVoiceEnabled ? 'WhiteCUL 音声オフ' : 'WhiteCUL 音声オン';
  }
}
