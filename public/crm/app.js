const STORAGE_KEY = 'teleapo-crm-leads-v1';
const VOICE_KEY = 'teleapo-crm-voice-enabled';
const THEME_KEY = 'teleapo-crm-theme-color';
const APPEARANCE_KEY = 'teleapo-ui-mode';

const statusLabels = {
  new: '未架電',
  prospect: '見込み',
  absent: '留守',
  recall: '再コール',
  appointment: 'アポ',
  banned: '禁止',
  called: '架電済',
  revisit: '再架電',
  ng: 'NG'
};

const form = document.querySelector('#leadForm');
const callForm = document.querySelector('#callForm');
const clearButton = document.querySelector('#clearButton');
const setCalledNowButton = document.querySelector('#setCalledNowButton');
const rows = document.querySelector('#leadRows');
const recordCount = document.querySelector('#recordCount');
const summary = document.querySelector('#summary');
const searchText = document.querySelector('#searchText');
const statusFilter = document.querySelector('#statusFilter');
const exportButton = document.querySelector('#exportButton');
const importButton = document.querySelector('#importButton');
const csvInput = document.querySelector('#csvInput');
const assistantMessage = document.querySelector('#assistantMessage');
const assistantTalk = document.querySelector('#assistantTalk');
const voiceToggle = document.querySelector('#voiceToggle');
const remChatForm = document.querySelector('#remChatForm');
const remChatInput = document.querySelector('#remChatInput');
const remChatLog = document.querySelector('#remChatLog');
const selectedName = document.querySelector('#selectedName');
const selectedPhone = document.querySelector('#selectedPhone');
const selectedAddress = document.querySelector('#selectedAddress');
const selectedStatus = document.querySelector('#selectedStatus');
const noteTimeline = document.querySelector('#noteTimeline');
const callCount = document.querySelector('#callCount');
const themeColor = document.querySelector('#themeColor');
const appearanceToggle = document.querySelector('#appearanceToggle');
const themeSwatches = document.querySelectorAll('.themeSwatches button');

let csrfToken = '';
let leads = normalizeLeads(loadLeads());
let selectedLeadId = leads[0]?.id || '';
let voiceEnabled = localStorage.getItem(VOICE_KEY) === 'true';
let currentVoiceAudio = null;
let currentVoiceUrl = '';
let voiceRequestId = 0;

saveLeads();
loadServerConfig();
applyTheme(localStorage.getItem(THEME_KEY) || '#38bdf8');
applyAppearance(localStorage.getItem(APPEARANCE_KEY) || 'dark');
render();
updateVoiceButton();
setTimeout(greetOnOpen, 450);

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const now = new Date().toISOString();
  const id = data.leadId || crypto.randomUUID();
  const existing = leads.find((lead) => lead.id === id);
  const next = normalizeLead({
    ...(existing || {}),
    id,
    name: data.name.trim(),
    phone: data.phone.trim(),
    address: data.address.trim(),
    updatedAt: now
  });
  leads = [next, ...leads.filter((lead) => lead.id !== id)];
  selectedLeadId = id;
  saveLeads();
  render();
  say(`${next.name}の顧客情報を保存しました。右側に架電メモを積み上げられます。`);
});

callForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const lead = selectedLead();
  if (!lead) {
    say('先に顧客を選択してください。', true);
    return;
  }
  const data = Object.fromEntries(new FormData(callForm));
  const now = new Date().toISOString();
  const note = {
    id: crypto.randomUUID(),
    person: data.person.trim(),
    calledAt: data.calledAt || formatDateTimeLocal(new Date()),
    status: normalizeStatus(data.status),
    nextCall: data.nextCall,
    memo: data.memo.trim(),
    createdAt: now
  };
  lead.notes = [note, ...(lead.notes || [])];
  lead.person = note.person;
  lead.calledAt = note.calledAt;
  lead.status = note.status;
  lead.nextCall = note.nextCall;
  lead.memo = note.memo;
  lead.updatedAt = now;
  leads = [lead, ...leads.filter((item) => item.id !== lead.id)];
  selectedLeadId = lead.id;
  saveLeads();
  callForm.reset();
  render();
  say(`${lead.name}に${statusLabels[note.status]}の記録を追加しました。履歴に積み上げています。`);
});

clearButton.addEventListener('click', () => {
  resetLeadForm();
  selectedLeadId = '';
  renderSelectedLead();
});
setCalledNowButton?.addEventListener('click', setCalledAtNow);
searchText.addEventListener('input', render);
statusFilter.addEventListener('change', render);
exportButton.addEventListener('click', exportCsv);
importButton.addEventListener('click', () => csvInput.click());
csvInput.addEventListener('change', importCsv);
assistantTalk.addEventListener('click', () => say(randomGreeting(), true));
remChatForm?.addEventListener('submit', handleRemChat);
selectedName.addEventListener('click', openSelectedLeadGoogleSearch);
selectedName.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    openSelectedLeadGoogleSearch();
  }
});

voiceToggle.addEventListener('click', () => {
  voiceEnabled = !voiceEnabled;
  localStorage.setItem(VOICE_KEY, String(voiceEnabled));
  updateVoiceButton();
  say(voiceEnabled ? '音声をオンにしました。必要な時は、レムが声でお知らせします。' : '音声をオフにしました。文字では引き続きそばにいます。', true);
});
themeColor.addEventListener('input', () => applyTheme(themeColor.value));
appearanceToggle?.addEventListener('click', toggleAppearance);
for (const swatch of themeSwatches) {
  swatch.addEventListener('click', () => applyTheme(swatch.dataset.color));
}


prepareBrowserVoices();

function openSelectedLeadGoogleSearch() {
  const lead = selectedLead();
  if (!lead || !lead.name) {
    say('先に顧客を選択してください。', true);
    return;
  }
  const query = [lead.name, lead.address].filter(Boolean).join(' ');
  const url = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
  window.open(url, '_blank', 'noopener,noreferrer');
  say(`${lead.name}をGoogle検索で開きます。`, false);
}

function applyAppearance(mode) {
  const nextMode = mode === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = nextMode;
  localStorage.setItem(APPEARANCE_KEY, nextMode);
  if (appearanceToggle) {
    appearanceToggle.textContent = nextMode === 'dark' ? 'ライトモード' : 'ダークモード';
    appearanceToggle.setAttribute('aria-pressed', String(nextMode === 'light'));
  }
}

function toggleAppearance() {
  applyAppearance(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

async function loadServerConfig() {
  try {
    const response = await fetch('/api/config');
    if (response.ok) {
      const config = await response.json();
      csrfToken = config.csrfToken || '';
    }
  } catch {
    csrfToken = '';
  }
}

async function handleRemChat(event) {
  event.preventDefault();
  const message = remChatInput.value.trim();
  if (!message) return;
  addChatMessage('user', message);
  remChatInput.value = '';
  setRemMood(message);
  const reply = await askRem(message);
  addChatMessage('rem', reply);
  say(reply, false);
}

async function askRem(message) {
  try {
    const lead = selectedLead();
    const response = await fetch('/api/rem-chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-csrf-token': csrfToken
      },
      body: JSON.stringify({
        message,
        customer: lead ? {
          name: lead.name,
          status: statusLabels[normalizeStatus(lead.status)] || lead.status,
          memo: lead.memo,
          notes: (lead.notes || []).slice(0, 5)
        } : null
      })
    });
    if (response.ok) {
      const data = await response.json();
      return data.reply || fallbackRemReply(message);
    }
  } catch {
    // Use local fallback when the AI endpoint is not configured.
  }
  return fallbackRemReply(message);
}

function fallbackRemReply(message) {
  const text = message.toLowerCase();
  if (/(疲|しんど|無理|つら|不安|怖)/.test(text)) {
    return '大丈夫です。まずは一件だけでいいので、短く区切って進めましょう。レムが横で整理します。';
  }
  if (/(何から|優先|どれ|順番)/.test(text)) {
    return '再コール、見込み、未架電の順で見るのがおすすめです。迷ったら、次回連絡日が近い顧客からいきましょう。';
  }
  if (/(トーク|話し方|断ら|営業)/.test(text)) {
    return '最初は「お忙しいところ恐れ入ります。30秒だけ要件をお伝えしてもよろしいでしょうか」と短く入ると、会話が作りやすいです。';
  }
  if (/(ありがとう|助か|いいね|最高)/.test(text)) {
    return 'えへへ、ありがとうございます。次の一件も一緒に片付けましょう。';
  }
  return 'はい。内容をメモに残しながら、次の一手を一緒に整理しましょう。必要なら、優先順位やトーク案も考えます。';
}

function addChatMessage(role, message) {
  if (!remChatLog) return;
  const item = document.createElement('p');
  item.className = `chatLine ${role === 'user' ? 'is-user' : 'is-rem'}`;
  item.textContent = role === 'user' ? `あなた: ${message}` : `レム: ${message}`;
  remChatLog.append(item);
  remChatLog.scrollTop = remChatLog.scrollHeight;
}

function setRemMood(message) {
  const text = String(message || '').toLowerCase();
  let image = './rem-calm-face.jpg';
  if (/(おはよう|眠|疲|つら|不安|心配|だめ|無理)/.test(text)) {
    image = './rem-morning.webp';
  } else if (/(ありがとう|嬉|最高|できた|いいね|笑|ｗ|ww)/.test(text)) {
    image = './rem-happy.webp';
  }
  document.documentElement.style.setProperty('--rem-image', `url('${image}')`);
}

function render() {
  const visible = filteredLeads();
  recordCount.textContent = `${leads.length}件`;
  const counts = countByStatus();
  summary.textContent = `未架電 ${counts.new} / 見込み ${counts.prospect} / 再コール ${counts.recall} / アポ ${counts.appointment} / 禁止 ${counts.banned}`;

  const fragment = document.createDocumentFragment();
  for (const lead of visible) {
    const tr = document.createElement('tr');
    tr.className = lead.id === selectedLeadId ? 'is-selected' : '';
    tr.innerHTML = `
      <td data-label="顧客名">${escapeHtml(lead.name)}<small>${escapeHtml(lead.address)}</small></td>
      <td data-label="電話番号">${phoneLinkHtml(lead.phone)}</td>
      <td data-label="最新結果"><span class="status status-${normalizeStatus(lead.status)}">${statusLabels[normalizeStatus(lead.status)] || lead.status}</span></td>
      <td data-label="最終架電">${formatDateTimeInput(lead.calledAt) || '-'}</td>
      <td data-label="担当者">${escapeHtml(lead.person || '-')}</td>
      <td data-label="次回連絡">${escapeHtml(lead.nextCall || '-')}</td>
      <td data-label="記録">${lead.notes?.length || 0}</td>
    `;
    tr.addEventListener('click', () => selectLead(lead.id));
    fragment.append(tr);
  }
  rows.replaceChildren(fragment);
  renderSelectedLead();
}

function renderSelectedLead() {
  const lead = selectedLead();
  if (!lead) {
    selectedName.textContent = '顧客を選択';
    selectedName.removeAttribute('tabindex');
    selectedName.removeAttribute('role');
    selectedName.removeAttribute('title');
    selectedPhone.textContent = '電話番号 -';
    selectedAddress.textContent = '住所 -';
    selectedStatus.className = 'status status-new';
    selectedStatus.textContent = '未選択';
    callCount.textContent = '0件';
    noteTimeline.innerHTML = '<p class="emptyState">左のリストから顧客を選ぶと、ここに架電履歴が表示されます。</p>';
    return;
  }
  selectedName.textContent = lead.name || '名称未設定';
  selectedName.tabIndex = 0;
  selectedName.setAttribute('role', 'button');
  selectedName.title = 'クリックするとGoogleで検索します';
  selectedPhone.innerHTML = `電話番号 ${phoneLinkHtml(lead.phone)}`;
  selectedAddress.textContent = `住所 ${lead.address || '-'}`;
  selectedStatus.className = `status status-${normalizeStatus(lead.status)}`;
  selectedStatus.textContent = statusLabels[normalizeStatus(lead.status)] || lead.status;
  callCount.textContent = `${lead.notes?.length || 0}件`;
  fillLeadForm(lead);
  renderNotes(lead);
}

function renderNotes(lead) {
  const notes = lead.notes || [];
  if (!notes.length) {
    noteTimeline.innerHTML = '<p class="emptyState">まだ記録がありません。右側のフォームから1件目を追加できます。</p>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const note of notes) {
    const article = document.createElement('article');
    article.className = 'noteCard';
    article.innerHTML = `
      <div class="noteMeta">
        <span class="status status-${normalizeStatus(note.status)}">${statusLabels[normalizeStatus(note.status)] || note.status}</span>
        <time>${formatDateTimeInput(note.calledAt) || formatDate(note.createdAt)}</time>
      </div>
      <p>${escapeHtml(note.memo || 'メモなし')}</p>
      <dl>
        <div><dt>担当者</dt><dd>${escapeHtml(note.person || '-')}</dd></div>
        <div><dt>次回連絡</dt><dd>${escapeHtml(note.nextCall || '-')}</dd></div>
      </dl>
    `;
    fragment.append(article);
  }
  noteTimeline.replaceChildren(fragment);
}

function selectLead(id) {
  selectedLeadId = id;
  render();
  const lead = selectedLead();
  if (lead) say(`${lead.name}を開きました。右側に架電記録を追加できます。`);
}

function selectedLead() {
  return leads.find((lead) => lead.id === selectedLeadId) || null;
}

function filteredLeads() {
  const query = searchText.value.trim().toLowerCase();
  const status = statusFilter.value;
  return leads.filter((lead) => {
    const notes = (lead.notes || []).map((note) => `${note.person} ${note.memo} ${statusLabels[note.status] || note.status} ${note.calledAt} ${note.nextCall}`).join(' ');
    const haystack = `${lead.name} ${lead.phone} ${lead.address} ${lead.person} ${lead.memo} ${statusLabels[lead.status] || lead.status} ${lead.calledAt || ''} ${lead.nextCall || ''} ${notes}`.toLowerCase();
    return (!query || haystack.includes(query)) && (status === 'all' || normalizeStatus(lead.status) === status || (lead.notes || []).some((note) => normalizeStatus(note.status) === status));
  });
}

function countByStatus() {
  return leads.reduce((acc, lead) => {
    const status = normalizeStatus(lead.status);
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, { new: 0, prospect: 0, absent: 0, recall: 0, appointment: 0, banned: 0 });
}

function fillLeadForm(lead) {
  form.elements.leadId.value = lead.id;
  form.elements.name.value = lead.name || '';
  form.elements.phone.value = lead.phone || '';
  form.elements.address.value = lead.address || '';
}

function setCalledAtNow() {
  callForm.elements.calledAt.value = formatDateTimeLocal(new Date());
  say('現在の時刻を、かけた時間に入力しました。');
}

function resetLeadForm() {
  form.reset();
  form.elements.leadId.value = '';
}

function normalizeLeads(items) {
  return items.map(normalizeLead).sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
}

function normalizeLead(lead) {
  const normalized = {
    id: lead.id || crypto.randomUUID(),
    name: lead.name || '',
    phone: lead.phone || '',
    address: lead.address || '',
    person: lead.person || '',
    calledAt: lead.calledAt || '',
    status: normalizeStatus(lead.status),
    nextCall: lead.nextCall || '',
    memo: lead.memo || '',
    updatedAt: lead.updatedAt || new Date().toISOString(),
    sourceKey: lead.sourceKey || '',
    source: lead.source || '',
    notes: Array.isArray(lead.notes) ? lead.notes.map(normalizeNote) : []
  };
  if (!normalized.notes.length && (normalized.memo || normalized.calledAt || normalized.person || normalizeStatus(normalized.status) !== 'new')) {
    normalized.notes = [normalizeNote({
      person: normalized.person,
      calledAt: normalized.calledAt,
      status: normalized.status,
      nextCall: normalized.nextCall,
      memo: normalized.memo,
      createdAt: normalized.updatedAt
    })];
  }
  return normalized;
}

function normalizeNote(note) {
  return {
    id: note.id || crypto.randomUUID(),
    person: note.person || '',
    calledAt: note.calledAt || '',
    status: normalizeStatus(note.status),
    nextCall: note.nextCall || '',
    memo: note.memo || '',
    createdAt: note.createdAt || new Date().toISOString()
  };
}

function loadLeads() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLeads() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(leads));
}

function exportCsv() {
  const headers = ['会社名・店舗名', '電話番号', '住所', '最新担当者', '最新架電時間', '最新結果', '次回連絡', '最新メモ', '記録履歴JSON', 'ID', '更新日時'];
  const lines = [headers, ...leads.map((lead) => [
    lead.name,
    lead.phone,
    lead.address,
    lead.person,
    lead.calledAt,
    statusLabels[normalizeStatus(lead.status)] || lead.status,
    lead.nextCall,
    lead.memo,
    JSON.stringify(lead.notes || []),
    lead.id,
    lead.updatedAt
  ])];
  const csv = lines.map((line) => line.map(csvCell).join(',')).join('\n');
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `teleapo-crm-${formatFileDate(new Date())}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  say('CSVを書き出しました。履歴も一緒にバックアップしています。');
}

function importCsv(event) {
  const file = event.target.files[0];
  if (!file) return;
  file.text().then((text) => {
    const rows = parseCsv(text.replace(/^\ufeff/, ''));
    const [headers, ...body] = rows;
    if (!headers) return;
    const indexes = Object.fromEntries(headers.map((header, index) => [header, index]));
    const imported = body.filter((row) => row.some(Boolean)).map((row) => {
      let notes = [];
      try {
        notes = JSON.parse(row[indexes['記録履歴JSON']] || '[]');
      } catch {
        notes = [];
      }
      return normalizeLead({
        id: row[indexes.ID] || crypto.randomUUID(),
        name: row[indexes['会社名・店舗名']] || row[indexes['顧客名']] || '',
        phone: row[indexes['電話番号']] || '',
        address: row[indexes['住所']] || '',
        person: row[indexes['最新担当者']] || row[indexes['かけた担当者']] || row[indexes['担当者']] || '',
        calledAt: row[indexes['最新架電時間']] || row[indexes['かけた時間']] || '',
        status: labelToStatus(row[indexes['最新結果']] || row[indexes['結果']] || row[indexes['ステータス']] || row[indexes['訪問状況']]),
        nextCall: row[indexes['次回連絡']] || row[indexes['次回訪問']] || '',
        memo: row[indexes['最新メモ']] || row[indexes['メモ']] || '',
        notes,
        updatedAt: row[indexes['更新日時']] || new Date().toISOString()
      });
    }).filter((lead) => lead.name);
    const merged = new Map(leads.map((lead) => [lead.id, lead]));
    for (const lead of imported) merged.set(lead.id, lead);
    leads = normalizeLeads([...merged.values()]);
    selectedLeadId = imported[0]?.id || selectedLeadId;
    saveLeads();
    render();
    say(`${imported.length}件を取り込みました。履歴も反映しています。`, true);
    event.target.value = '';
  });
}

function labelToStatus(label = '') {
  const hit = Object.entries(statusLabels).find(([, value]) => value === label);
  return hit ? hit[0] : ['new', 'prospect', 'absent', 'recall', 'appointment', 'banned', 'called', 'revisit', 'ng'].includes(label) ? normalizeStatus(label) : 'new';
}

function normalizeStatus(status = 'new') {
  const legacy = { called: 'prospect', revisit: 'recall', ng: 'banned' };
  return legacy[status] || status || 'new';
}

function formatDateTimeLocal(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDateTimeInput(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function csvCell(value = '') {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (quoted && char === '"' && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (!quoted && char === ',') {
      row.push(cell);
      cell = '';
    } else if (!quoted && (char === '\n' || char === '\r')) {
      if (char === '\r' && next === '\n') i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += char;
    }
  }
  row.push(cell);
  rows.push(row);
  return rows;
}

function greetOnOpen() {
  say(randomGreeting(), false);
}

function randomGreeting() {
  const hour = new Date().getHours();
  const timeWord = hour < 11 ? 'おはようございます' : hour < 18 ? 'こんにちは' : 'おつかれさまです';
  const counts = countByStatus();
  const options = [
    `${timeWord}。見込みは${counts.prospect}件、再コールは${counts.recall}件です。優先順位を決めていきましょう。`,
    `${timeWord}。顧客を選択すると、右側にメモ履歴を積み上げられます。`,
    `${timeWord}。レムが今日の架電整理をお手伝いします。まずは一社選びましょう。`
  ];
  return options[Math.floor(Math.random() * options.length)];
}

function say(message, forceVoice = false) {
  setRemMood(message);
  assistantMessage.textContent = message;
  if (voiceEnabled || forceVoice) {
    stopCurrentVoice();
    const requestId = ++voiceRequestId;
    speakWithVoicevox(message, requestId).catch(() => {
      if (requestId === voiceRequestId) speakWithBrowserVoice(message);
    });
  }
}

async function speakWithVoicevox(message, requestId) {
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
  if (requestId !== voiceRequestId) return;
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentVoiceAudio = audio;
  currentVoiceUrl = url;
  const cleanup = () => {
    if (currentVoiceAudio === audio) currentVoiceAudio = null;
    if (currentVoiceUrl === url) currentVoiceUrl = '';
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

function stopCurrentVoice() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (currentVoiceAudio) {
    currentVoiceAudio.pause();
    currentVoiceAudio.currentTime = 0;
    currentVoiceAudio = null;
  }
  if (currentVoiceUrl) {
    URL.revokeObjectURL(currentVoiceUrl);
    currentVoiceUrl = '';
  }
}

function speakWithBrowserVoice(message) {
  if (!('speechSynthesis' in window)) return;
  stopCurrentVoice();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = 'ja-JP';
  const preferredVoice = getPreferredJapaneseVoice();
  if (preferredVoice) utterance.voice = preferredVoice;
  utterance.rate = 0.94;
  utterance.pitch = 1.42;
  utterance.volume = 1;
  window.speechSynthesis.speak(utterance);
}

function updateVoiceButton() {
  voiceToggle.textContent = voiceEnabled ? 'WhiteCUL 音声オフ' : 'WhiteCUL 音声オン';
}

function applyTheme(color) {
  document.documentElement.style.setProperty('--accent', color);
  themeColor.value = color;
  localStorage.setItem(THEME_KEY, color);
}

function phoneLinkHtml(phone) {
  const raw = String(phone || '').trim();
  if (!raw) return '-';
  const tel = raw.replace(/[^0-9+]/g, '');
  if (!tel) return escapeHtml(raw);
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
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat('ja-JP', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatFileDate(date) {
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`;
}
