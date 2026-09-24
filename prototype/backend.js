(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    setTimeout(() => modal.querySelector('input:not([type=hidden]), textarea, select')?.focus(), 20);
  }
  function closeModal(modal) {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
  }
  $$('[data-modal-open]').forEach(button => button.addEventListener('click', () => openModal(button.dataset.modalOpen)));
  $$('[data-modal-close]').forEach(button => button.addEventListener('click', () => closeModal(button.closest('.modal-backdrop'))));
  $$('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) closeModal(modal); }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') $$('.modal-backdrop.show').forEach(closeModal);
    if (event.altKey && event.key.toLowerCase() === 'p') { event.preventDefault(); $('#pcbLookup')?.focus(); }
  });

  $$('.flash').forEach((flash, index) => setTimeout(() => flash.remove(), 4500 + index * 500));
  $$('[data-toggle]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.toggle)?.classList.toggle('hidden')));
  $$('select[data-auto-submit]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
  $$('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));

  const kindHints = {
    '现象': '发送后进入「处理中」。', '测试记录': '发送后进入「处理中」。',
    '当前判断': '发送后进入「处理中」。', '等待原因': '发送后进入「等待中」。',
    '阶段结论': '发送后进入「待验证」。', '结论及复盘': '发送后自动标记「已解决」，历时停止。',
    '知识积累': '保存为独立知识条目，并在问题时间线保留入口；不改变问题状态。'
  };
  const kindSelect = document.querySelector('.backend-composer select[name="kind"]');
  const kindHint = $('#cellKindHint');
  const knowledgeTitleField = $('#knowledgeTitleField');
  const knowledgeTitle = $('#knowledgeTitle');
  const refreshKind = () => {
    const isKnowledge = kindSelect?.value === '知识积累';
    if (kindHint) kindHint.textContent = kindHints[kindSelect.value] || '此类型不改变问题状态。';
    if (knowledgeTitleField) knowledgeTitleField.hidden = !isKnowledge;
    if (knowledgeTitle) knowledgeTitle.required = isKnowledge;
  };
  kindSelect?.addEventListener('change', refreshKind);
  if (kindSelect) refreshKind();

  const issueElapsed = $('#issueElapsed');
  if (issueElapsed) {
    const start = Date.parse(issueElapsed.dataset.startUtc);
    const fixedEnd = issueElapsed.dataset.endUtc ? Date.parse(issueElapsed.dataset.endUtc) : null;
    const formatDuration = seconds => {
      const days = Math.floor(seconds / 86400), hours = Math.floor(seconds % 86400 / 3600), minutes = Math.floor(seconds % 3600 / 60);
      return days ? `${days}天 ${hours}小时` : hours ? `${hours}小时 ${minutes}分钟` : minutes ? `${minutes}分钟` : '不足1分钟';
    };
    const refresh = () => { if (Number.isFinite(start)) issueElapsed.textContent = formatDuration(Math.max(0, Math.floor(((fixedEnd ?? Date.now()) - start) / 1000))); };
    refresh();
    if (fixedEnd === null) setInterval(refresh, 30000);
  }

  const lookup = $('#pcbLookup');
  const menu = $('#lookupMenu');
  let lookupController;
  if (lookup && menu) {
    lookup.addEventListener('input', async () => {
      const q = lookup.value.trim();
      if (q.length < 2) { menu.classList.remove('show'); return; }
      lookupController?.abort();
      lookupController = new AbortController();
      try {
        const rows = await fetch(`/api/v1/pcbs?q=${encodeURIComponent(q)}&limit=10`, {signal: lookupController.signal}).then(r => r.json());
        menu.innerHTML = rows.length ? rows.map(row => `<a class="lookup-result" href="/pcbs/${row.id}"><span><strong>${escapeHtml(row.model || '未填写型号')}</strong><small>${escapeHtml(row.revision || '未填写版本')} · ${escapeHtml(row.serial)}</small></span><small>${escapeHtml(row.status)}</small></a>`).join('') : '<div class="lookup-result"><small>没有匹配的PCB</small></div>';
        menu.classList.add('show');
      } catch (error) { if (error.name !== 'AbortError') menu.classList.remove('show'); }
    });
    document.addEventListener('click', event => { if (!event.target.closest('.pcb-lookup')) menu.classList.remove('show'); });
  }

  function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }

  // Keep PCB pickers small: request at most 30 matching values when a field is used.
  $$('form[data-pcb-cascade]').forEach(form => {
    const fields = Object.fromEntries($$('[data-pcb-option]', form).map(input => [input.dataset.pcbOption, input]));
    const timers = new Map();
    const controllers = new Map();
    function clearField(name, clearValue = false) {
      const input = fields[name];
      if (!input) return;
      clearTimeout(timers.get(name));
      controllers.get(name)?.abort();
      input.list?.replaceChildren();
      if (clearValue) input.value = '';
    }
    async function loadOptions(name) {
      const input = fields[name];
      const model = fields.model?.value.trim() || '';
      const revision = fields.revision?.value.trim() || '';
      if (!input || (name !== 'model' && !model) || (name === 'serial' && !revision)) {
        clearField(name);
        return;
      }
      controllers.get(name)?.abort();
      const controller = new AbortController();
      controllers.set(name, controller);
      const params = new URLSearchParams({field: name, q: input.value.trim()});
      if (name !== 'model') params.set('model', model);
      if (name === 'serial') params.set('revision', revision);
      try {
        const response = await fetch(`/pcbs/options?${params}`, {signal: controller.signal});
        if (!response.ok) return;
        const {options} = await response.json();
        if (controller.signal.aborted) return;
        input.list?.replaceChildren(...options.map(value => {
          const option = document.createElement('option');
          option.value = value;
          return option;
        }));
      } catch (error) { if (error.name !== 'AbortError') input.list?.replaceChildren(); }
    }
    Object.entries(fields).forEach(([name, input]) => {
      input.addEventListener('focus', () => loadOptions(name));
      input.addEventListener('input', () => {
        if (name === 'model') { clearField('revision', true); clearField('serial', true); }
        if (name === 'revision') clearField('serial', true);
        clearTimeout(timers.get(name));
        controllers.get(name)?.abort();
        timers.set(name, setTimeout(() => loadOptions(name), 180));
      });
    });
  });

  const editor = $('#cellEditor');
  function wrapSelection(before, after = before) {
    if (!editor) return;
    const start = editor.selectionStart, end = editor.selectionEnd;
    const selected = editor.value.slice(start, end) || '重点内容';
    editor.setRangeText(`${before}${selected}${after}`, start, end, 'end');
    editor.focus();
  }
  $$('[data-editor-wrap]').forEach(button => button.addEventListener('click', () => wrapSelection(button.dataset.editorWrap)));
  $$('[data-editor-color]').forEach(button => button.addEventListener('click', () => wrapSelection(`[${button.dataset.editorColor}]`, `[/${button.dataset.editorColor}]`)));

  const attachmentInput = $('#attachmentInput');
  const preview = $('#uploadPreview');
  function markdownCell(value) {
    return String(value ?? '').replace(/\r?\n/g, '<br>').replace(/\|/g, '\\|').trim();
  }
  function tableMarkdown(rows) {
    const width = Math.max(...rows.map(row => row.length));
    if (!width || !rows.length) return '';
    const line = row => `| ${Array.from({length: width}, (_, index) => markdownCell(row[index])).join(' | ')} |`;
    return [line(rows[0]), `| ${Array(width).fill('---').join(' | ')} |`, ...rows.slice(1).map(line)].join('\n');
  }
  function excelTable(clipboard) {
    const html = clipboard.getData('text/html');
    if (html) {
      const documentFragment = new DOMParser().parseFromString(html, 'text/html');
      const table = documentFragment.querySelector('table');
      if (table) {
        const rows = [...table.rows].map(row => [...row.cells].map(cell => cell.innerText || cell.textContent || ''));
        if (rows.length && (rows.length > 1 || rows.some(row => row.length > 1)) && rows.length < 1000) return tableMarkdown(rows);
      }
    }
    const text = clipboard.getData('text/plain').replace(/\r\n?/g, '\n').replace(/\n$/, '');
    if (!text.includes('\t')) return '';
    const rows = text.split('\n').map(row => row.split('\t'));
    if (rows.length > 1000 || Math.max(...rows.map(row => row.length)) > 100) return '';
    return tableMarkdown(rows);
  }
  function addAttachmentFiles(files) {
    if (!attachmentInput || !files.length) return;
    const dt = new DataTransfer();
    [...attachmentInput.files, ...files].filter(Boolean).forEach(file => dt.items.add(file));
    attachmentInput.files = dt.files;
    previewFiles(dt.files);
  }
  function previewFiles(files) {
    if (!preview) return;
    preview.innerHTML = '';
    [...files].slice(0, 10).forEach(file => {
      if (file.type.startsWith('image/')) {
        const image = document.createElement('img'); image.src = URL.createObjectURL(file); image.alt = file.name;
        image.onload = () => URL.revokeObjectURL(image.src); preview.appendChild(image);
      } else { const span = document.createElement('span'); span.textContent = file.name; preview.appendChild(span); }
    });
  }
  attachmentInput?.addEventListener('change', event => previewFiles(event.target.files));
  editor?.addEventListener('paste', event => {
    const clipboard = event.clipboardData;
    const files = [...clipboard.items].filter(item => item.kind === 'file').map(item => item.getAsFile()).filter(Boolean);
    const table = excelTable(clipboard);
    if (table) {
      event.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      const before = start > 0 && editor.value[start - 1] !== '\n' ? '\n\n' : '';
      const after = end < editor.value.length && editor.value[end] !== '\n' ? '\n\n' : '';
      editor.setRangeText(`${before}${table}${after}`, start, end, 'end');
    }
    addAttachmentFiles(files);
  });
  editor?.addEventListener('dragover', event => event.preventDefault());
  editor?.addEventListener('drop', event => {
    event.preventDefault(); if (!attachmentInput) return;
    addAttachmentFiles([...event.dataTransfer.files]);
  });

  const imageViewer = $('#imageViewer');
  const viewerImage = $('#imageViewerImage');
  const viewerDownload = $('#imageViewerDownload');
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-preview-url]');
    if (!link || !imageViewer || !viewerImage || !viewerDownload) return;
    event.preventDefault();
    viewerImage.src = link.dataset.previewUrl;
    viewerImage.alt = link.querySelector('img')?.alt || '图片预览';
    viewerDownload.href = link.href;
    imageViewer.showModal();
  });
  imageViewer?.addEventListener('click', event => { if (event.target === imageViewer) imageViewer.close(); });
  imageViewer?.addEventListener('close', () => { viewerImage.removeAttribute('src'); });

  $$('[data-timer-start]').forEach(label => {
    const start = new Date(`${label.dataset.timerStart}Z`).getTime();
    const update = () => { const seconds = Math.max(Math.floor((Date.now()-start)/1000),0); label.textContent = `结束 ${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`; };
    update(); setInterval(update, 1000);
  });
})();
