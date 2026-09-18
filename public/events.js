let csrfToken = '';
const APPEARANCE_KEY = 'teleapo-ui-mode';
const eventForm = document.querySelector('#eventForm');
const eventButton = document.querySelector('#eventSubmitButton');
const eventResultsInput = document.querySelector('#eventResults');
const eventStartInput = document.querySelector('#eventStart');
const appearanceToggle = document.querySelector('#appearanceToggle');
const rows = document.querySelector('#rows');
const summary = document.querySelector('#summary');
const statusBox = document.querySelector('#status');
const sheetName = document.querySelector('#sheetName');

applyAppearance(localStorage.getItem(APPEARANCE_KEY) || 'dark');
appearanceToggle.addEventListener('click', () => {
  applyAppearance(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
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
    summary.textContent = `${payload.start}件目から${data.count}件取得 / ${data.appended}件追記 / ${data.skipped}件スキップ`;
    eventStartInput.value = String(payload.start + payload.results);
    setStatus(`完了しました。次は${eventStartInput.value}件目から検索できます。`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(false);
  }
});

function renderEventRows(items) {
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const tr = document.createElement('tr');
    tr.append(
      cellWithLink(item.title, item.url, 'イベント名'),
      textCell(formatDate(item.startedAt), '開催開始'),
      textCell(item.place, '会場'),
      textCell(item.address, '住所'),
      textCell(`${item.accepted || 0}/${item.limit || '-'}`, '参加')
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

function cellWithLink(label, url, heading) {
  const td = textCell('', heading);
  if (!url) {
    td.textContent = label || '-';
    return td;
  }
  const link = document.createElement('a');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener';
  link.textContent = label || url;
  td.append(link);
  return td;
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
  eventButton.textContent = isBusy ? '処理中...' : 'イベント検索して追記';
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
