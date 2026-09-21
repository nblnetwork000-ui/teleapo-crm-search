let csrfToken = '';
const APPEARANCE_KEY = 'teleapo-ui-mode';
const eventForm = document.querySelector('#eventForm');
const eventButton = document.querySelector('#eventSubmitButton');
const eventResultsInput = document.querySelector('#eventResults');
const eventPrefecture = document.querySelector('#eventPrefecture');
const eventAreaDetail = document.querySelector('#eventAreaDetail');
const eventWebSource = document.querySelector('#eventWebSource');
const appearanceToggle = document.querySelector('#appearanceToggle');
const rows = document.querySelector('#rows');
const summary = document.querySelector('#summary');
const statusBox = document.querySelector('#status');
const sheetName = document.querySelector('#sheetName');
const adminUsersLink = document.querySelector('#adminUsersLink');
const guideOpenButton = document.querySelector('#guideOpenButton');
const onboardingDialog = document.querySelector('#onboardingDialog');
const onboardingProgress = document.querySelector('#onboardingProgress');
const onboardingSection = document.querySelector('#onboardingSection');
const onboardingTitle = document.querySelector('#onboardingTitle');
const onboardingDescription = document.querySelector('#onboardingDescription');
const onboardingTip = document.querySelector('#onboardingTip');
const onboardingSkip = document.querySelector('#onboardingSkip');
const onboardingBack = document.querySelector('#onboardingBack');
const onboardingNext = document.querySelector('#onboardingNext');

const ONBOARDING_STEPS = [
  {
    section: 'はじめに',
    title: 'SIGNALへようこそ',
    description: 'イベント検索から候補の比較まで、この画面で行えます。最初に基本操作を4つの手順で確認します。',
    tip: '検索だけならデータは保存されません。まずはシートへの追記をオフのままお試しください。'
  },
  {
    section: '検索条件',
    title: '条件を指定して検索',
    description: '左側でキーワード、地域、掲載元、開催期間、参加費を指定し、「イベント検索」を押します。',
    tip: '条件を増やし過ぎると結果が少なくなります。まずはキーワードと地域から始めるのがおすすめです。'
  },
  {
    section: '検索結果',
    title: '詳細は掲載元で確認',
    description: '右側にイベント名、開催場所、時間、参加費が表示されます。「詳細を見る」で掲載元のページを開けます。',
    tip: '「要確認」は情報を取得できなかった項目です。日時・料金・申込条件は掲載元で最終確認してください。'
  },
  {
    section: '結果の保存',
    title: '必要な結果だけシートへ',
    description: 'Googleシートに記録する場合のみ「シートへ追記」をオンにして、もう一度検索します。',
    tip: '検索後は「取得・追記・スキップ」の件数を確認してください。この案内は「使い方」からいつでも見直せます。'
  }
];
let onboardingStepIndex = 0;
let onboardingStorageKey = '';

const AREA_DETAILS = {
  '北海道': ['札幌市', '函館市', '旭川市', '帯広市', '釧路市', '小樽市'],
  '青森県': ['青森市', '弘前市', '八戸市'], '岩手県': ['盛岡市', '一関市', '北上市'],
  '宮城県': ['仙台市', '石巻市', '名取市'], '秋田県': ['秋田市', '横手市'],
  '山形県': ['山形市', '米沢市', '鶴岡市'], '福島県': ['福島市', '郡山市', 'いわき市', '会津若松市'],
  '茨城県': ['水戸市', 'つくば市', '土浦市', '日立市'], '栃木県': ['宇都宮市', '小山市', '足利市'],
  '群馬県': ['前橋市', '高崎市', '太田市'], '埼玉県': ['さいたま市', '川口市', '川越市', '越谷市', '所沢市', '大宮'],
  '千葉県': ['千葉市', '船橋市', '柏市', '松戸市', '市川市', '浦安市'],
  '東京都': ['千代田区', '中央区', '港区', '新宿区', '文京区', '台東区', '墨田区', '江東区', '品川区', '目黒区', '大田区', '世田谷区', '渋谷区', '中野区', '杉並区', '豊島区', '北区', '荒川区', '板橋区', '練馬区', '足立区', '葛飾区', '江戸川区', '八王子市', '立川市', '武蔵野市', '町田市'],
  '神奈川県': ['横浜市', '川崎市', '相模原市', '横須賀市', '藤沢市', '鎌倉市'],
  '新潟県': ['新潟市', '長岡市', '上越市'], '富山県': ['富山市', '高岡市'],
  '石川県': ['金沢市', '小松市'], '福井県': ['福井市', '敦賀市'],
  '山梨県': ['甲府市', '富士吉田市'], '長野県': ['長野市', '松本市', '上田市', '軽井沢町'],
  '岐阜県': ['岐阜市', '大垣市', '高山市'], '静岡県': ['静岡市', '浜松市', '沼津市', '三島市'],
  '愛知県': ['名古屋市', '豊田市', '岡崎市', '一宮市', '豊橋市'], '三重県': ['津市', '四日市市', '伊勢市'],
  '滋賀県': ['大津市', '草津市'], '京都府': ['京都市', '宇治市', '福知山市'],
  '大阪府': ['大阪市', '堺市', '東大阪市', '豊中市', '吹田市', '高槻市', '梅田', '難波'],
  '兵庫県': ['神戸市', '姫路市', '西宮市', '尼崎市', '明石市'], '奈良県': ['奈良市', '橿原市'],
  '和歌山県': ['和歌山市', '田辺市'], '鳥取県': ['鳥取市', '米子市'],
  '島根県': ['松江市', '出雲市'], '岡山県': ['岡山市', '倉敷市'],
  '広島県': ['広島市', '福山市', '呉市'], '山口県': ['山口市', '下関市', '周南市'],
  '徳島県': ['徳島市', '鳴門市'], '香川県': ['高松市', '丸亀市'],
  '愛媛県': ['松山市', '今治市'], '高知県': ['高知市'],
  '福岡県': ['福岡市', '北九州市', '久留米市', '飯塚市'], '佐賀県': ['佐賀市', '唐津市'],
  '長崎県': ['長崎市', '佐世保市'], '熊本県': ['熊本市', '八代市'],
  '大分県': ['大分市', '別府市'], '宮崎県': ['宮崎市', '都城市'],
  '鹿児島県': ['鹿児島市', '霧島市'], '沖縄県': ['那覇市', '沖縄市', '浦添市', '石垣市']
};

applyAppearance(localStorage.getItem(APPEARANCE_KEY) || 'dark');
appearanceToggle.addEventListener('click', () => {
  applyAppearance(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
});

eventPrefecture.addEventListener('change', () => {
  populateAreaDetails(eventPrefecture.value);
});

const configResponse = await fetch('/api/config');
if (!configResponse.ok) {
  window.location.assign('/login');
  throw new Error('ログインが必要です。');
}
const appConfig = await configResponse.json();
csrfToken = appConfig.csrfToken;
eventResultsInput.max = appConfig.maxResultsPerRun;
sheetName.textContent = `追記先: ${appConfig.eventSheetName}`;
if (appConfig.webSearchAvailable) {
  eventWebSource.hidden = false;
  eventWebSource.disabled = false;
}
if (appConfig.isAdmin) {
  adminUsersLink.hidden = false;
}
onboardingStorageKey = `signal-event-onboarding-v1:${String(appConfig.memberEmail || '').trim().toLowerCase()}`;
guideOpenButton.addEventListener('click', () => openOnboarding());
onboardingSkip.addEventListener('click', () => closeOnboarding());
onboardingBack.addEventListener('click', () => {
  onboardingStepIndex = Math.max(0, onboardingStepIndex - 1);
  renderOnboardingStep();
});
onboardingNext.addEventListener('click', () => {
  if (onboardingStepIndex === ONBOARDING_STEPS.length - 1) {
    closeOnboarding();
    return;
  }
  onboardingStepIndex += 1;
  renderOnboardingStep();
});
onboardingDialog.addEventListener('cancel', (event) => {
  event.preventDefault();
  closeOnboarding();
});
if (localStorage.getItem(onboardingStorageKey) !== 'done') {
  openOnboarding();
}

function openOnboarding() {
  onboardingStepIndex = 0;
  renderOnboardingStep();
  if (!onboardingDialog.open) onboardingDialog.showModal();
  onboardingNext.focus();
}

function closeOnboarding() {
  localStorage.setItem(onboardingStorageKey, 'done');
  onboardingDialog.close();
  guideOpenButton.focus();
}

function renderOnboardingStep() {
  const step = ONBOARDING_STEPS[onboardingStepIndex];
  onboardingProgress.textContent = `${onboardingStepIndex + 1} / ${ONBOARDING_STEPS.length}`;
  onboardingSection.textContent = step.section;
  onboardingTitle.textContent = step.title;
  onboardingDescription.textContent = step.description;
  onboardingTip.textContent = step.tip;
  onboardingBack.hidden = onboardingStepIndex === 0;
  onboardingNext.textContent = onboardingStepIndex === ONBOARDING_STEPS.length - 1 ? '検索画面へ' : '次へ';
}

eventForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(eventForm);
  const payload = {
    keyword: formData.get('keyword'),
    area: [formData.get('prefecture'), formData.get('areaDetail')].filter(Boolean).join(' '),
    source: formData.get('source'),
    dateFrom: formData.get('dateFrom'),
    dateTo: formData.get('dateTo'),
    feeBand: formData.get('feeBand'),
    feeSort: formData.get('feeSort'),
    results: Number(formData.get('results')),
    start: 1,
    futureOnly: formData.get('futureOnly') === 'on',
    append: formData.get('append') === 'on'
  };

  setBusy(true);
  setStatus('検索中です...');
  rows.replaceChildren();
  summary.textContent = '';
  try {
    const response = await fetch('/api/events/search-and-append', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-csrf-token': csrfToken
      },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '処理に失敗しました。');
    renderEventRows(data.items);
    summary.textContent = `${data.count}件取得 / ${data.appended}件追記 / ${data.skipped}件スキップ`;
    const warnings = Array.isArray(data.warnings) ? data.warnings.filter(Boolean) : [];
    if (warnings.length) {
      setStatus(`検索は完了しました。${warnings.join(' / ')}`);
    } else {
      setStatus('検索が完了しました。');
    }
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
});

function populateAreaDetails(prefecture) {
  const options = AREA_DETAILS[prefecture] || [];
  eventAreaDetail.replaceChildren();
  const emptyOption = document.createElement('option');
  emptyOption.value = '';
  emptyOption.textContent = prefecture ? '指定なし' : '都道府県を選択';
  eventAreaDetail.append(emptyOption);
  for (const area of options) {
    const option = document.createElement('option');
    option.value = area;
    option.textContent = area;
    eventAreaDetail.append(option);
  }
  eventAreaDetail.disabled = !prefecture;
}

function renderEventRows(items) {
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const tr = document.createElement('tr');
    tr.append(
      textCell(item.title, 'イベント名'),
      textCell(formatLocation(item), '開催場所'),
      textCell(formatEventTime(item), '時間'),
      textCell(item.fee || '要確認', '参加費'),
      detailCell(item)
    );
    fragment.append(tr);
  }
  rows.replaceChildren(fragment);
}

function textCell(value, label) {
  const td = document.createElement('td');
  td.dataset.label = label;
  td.textContent = value || '-';
  return td;
}

function detailCell(item) {
  const td = document.createElement('td');
  td.dataset.label = '詳細';
  td.classList.add('detailCell');
  if (!item.url) {
    td.textContent = item.source || '-';
    return td;
  }
  const link = document.createElement('a');
  link.href = item.url;
  link.target = '_blank';
  link.rel = 'noopener';
  link.textContent = '詳細を見る';
  link.title = `${item.source || '掲載元'}のページを開く`;
  td.append(link);
  return td;
}

function formatLocation(item) {
  const place = String(item.place || '').trim();
  const address = String(item.address || '').trim();
  if (!place) return address || '要確認';
  if (!address || address === place || address.includes(place)) return place;
  if (address.length > 120) return place;
  return `${place}（${address}）`;
}

function formatEventTime(item) {
  const start = formatDate(item.startedAt);
  const end = formatDate(item.endedAt);
  if (!end || end === start) return start || '要確認';
  return `${start} 〜 ${end}`;
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function setBusy(isBusy) {
  eventButton.disabled = isBusy;
  eventButton.textContent = isBusy ? '処理中...' : 'イベント検索';
}

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.dataset.state = isError ? 'error' : 'normal';
}

function applyAppearance(mode) {
  const nextMode = mode === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = nextMode;
  localStorage.setItem(APPEARANCE_KEY, nextMode);
  appearanceToggle.textContent = nextMode === 'dark' ? 'ライト' : 'ダーク';
  appearanceToggle.setAttribute('aria-pressed', String(nextMode === 'light'));
}
