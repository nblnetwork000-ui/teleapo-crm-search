const form = document.querySelector('#customerForm');
const status = document.querySelector('#status');
const rows = document.querySelector('#customerRows');
const filter = document.querySelector('#filter');
const csvInput = document.querySelector('#csvInput');
let csrfToken = '';
let customers = [];

function say(message, error = false) {
  status.textContent = message;
  status.dataset.state = error ? 'error' : '';
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '処理に失敗しました。');
  return data;
}

try {
  const config = await api('/api/config');
  csrfToken = config.csrfToken;
  document.querySelector('#account').textContent = `${config.memberEmail} の専用リスト`;
  if (config.isAdmin) document.querySelector('#adminUsersLink').hidden = false;
  await reload();
} catch (error) {
  say(error.message, true);
}

async function reload() {
  const result = await api('/api/customers');
  customers = result.items;
  render();
}

function render() {
  const word = filter.value.trim().toLowerCase();
  const selected = customers.filter((item) => [item.name, item.phone, item.address, item.memo].some((value) => String(value || '').toLowerCase().includes(word)));
  document.querySelector('#count').textContent = `${customers.length}件`;
  rows.replaceChildren();
  for (const item of selected) {
    const row = document.createElement('tr');
    for (const key of ['name', 'phone', 'address', 'person', 'status', 'nextCall', 'memo']) {
      const cell = document.createElement('td');
      cell.textContent = item[key] || '';
      row.append(cell);
    }
    const cell = document.createElement('td');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'miniButton';
    button.textContent = '編集';
    button.addEventListener('click', () => edit(item));
    cell.append(button);
    row.append(cell);
    rows.append(row);
  }
  if (!selected.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 8;
    cell.textContent = '顧客がありません。上のフォームから登録するか、CSVを取り込んでください。';
    row.append(cell);
    rows.append(row);
  }
}

function edit(item) {
  for (const key of ['id', 'name', 'phone', 'address', 'person', 'status', 'nextCall', 'memo']) form.elements[key].value = item[key] || '';
  form.scrollIntoView({behavior: 'smooth'});
  form.elements.name.focus();
}

filter.addEventListener('input', render);
document.querySelector('#clearForm').addEventListener('click', () => form.reset());
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const old = customers.find((item) => item.id === data.id);
  data.notes = old?.notes || [];
  try {
    await save([data]);
    form.reset();
    await reload();
    say('顧客情報を保存しました。');
  } catch (error) { say(error.message, true); }
});

async function save(items) {
  return api('/api/customers', {method: 'POST', headers: {'Content-Type': 'application/json', 'x-csrf-token': csrfToken}, body: JSON.stringify({items})});
}

csvInput.addEventListener('change', async () => {
  const file = csvInput.files?.[0];
  if (!file) return;
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error('CSVは5MB以下にしてください。');
    const parsed = parseCsv((await file.text()).replace(/^\ufeff/, ''));
    const [headers, ...body] = parsed;
    if (!headers?.includes('会社名・店舗名') && !headers?.includes('顧客名')) throw new Error('会社名・店舗名の列がありません。');
    const index = Object.fromEntries(headers.map((value, i) => [value.trim(), i]));
    const value = (row, ...keys) => keys.map((key) => row[index[key]] || '').find(Boolean) || '';
    const items = body.filter((row) => row.some(Boolean)).map((row) => {
      let notes = [];
      try { notes = JSON.parse(value(row, '記録履歴JSON') || '[]'); } catch { notes = []; }
      const oldId = value(row, 'ID');
      return {
        id: /^[A-Za-z0-9_-]{1,80}$/.test(oldId) ? oldId : crypto.randomUUID(),
        name: value(row, '会社名・店舗名', '顧客名'), phone: value(row, '電話番号'), address: value(row, '住所'),
        person: value(row, '最新担当者', '担当者'), status: value(row, '最新結果', 'ステータス'),
        nextCall: value(row, '次回連絡'), memo: value(row, '最新メモ', 'メモ'), notes: Array.isArray(notes) ? notes : []
      };
    }).filter((item) => item.name);
    if (!items.length) throw new Error('取り込める顧客がありません。');
    for (let i = 0; i < items.length; i += 100) await save(items.slice(i, i + 100));
    await reload();
    say(`${items.length}件を取り込みました。`);
  } catch (error) { say(error.message, true); }
  csvInput.value = '';
});

document.querySelector('#exportButton').addEventListener('click', () => {
  const headers = ['会社名・店舗名', '電話番号', '住所', '最新担当者', '最新結果', '次回連絡', '最新メモ', '記録履歴JSON', 'ID', '更新日時'];
  const data = [headers, ...customers.map((item) => [item.name, item.phone, item.address, item.person, item.status, item.nextCall, item.memo, JSON.stringify(item.notes || []), item.id, item.updatedAt])];
  const csv = '\ufeff' + data.map((line) => line.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'signal-customers.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function parseCsv(text) {
  const result = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { row.push(field); field = ''; }
    else if (char === '\n') { row.push(field.replace(/\r$/, '')); result.push(row); row = []; field = ''; }
    else field += char;
  }
  if (field || row.length) { row.push(field); result.push(row); }
  return result;
}
