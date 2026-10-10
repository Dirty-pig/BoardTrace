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
        menu.innerHTML = rows.length ? rows.map(row => `<a class="lookup-result" href="/pcbs/${row.id}"><span><strong>${escapeHtml(row.model || '未填写型号')}</strong><small>${escapeHtml([row.revision, row.serial].map(value => value?.trim() || '\u00a0\u00a0\u00a0').join(' - '))}</small></span><small>${escapeHtml(row.status)}</small></a>`).join('') : '<div class="lookup-result"><small>没有匹配的PCB</small></div>';
        menu.classList.add('show');
      } catch (error) { if (error.name !== 'AbortError') menu.classList.remove('show'); }
    });
    document.addEventListener('click', event => { if (!event.target.closest('.pcb-lookup')) menu.classList.remove('show'); });
  }

  function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }

  $$('[data-knowledge-issue-picker]').forEach(input => {
    let timer;
    let controller;
    async function loadIssues() {
      controller?.abort();
      controller = new AbortController();
      try {
        const q = encodeURIComponent(input.value.trim());
        const response = await fetch(`/knowledge/issue-options?q=${q}`, {signal: controller.signal});
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
    input.addEventListener('focus', loadIssues);
    input.addEventListener('input', () => {
      clearTimeout(timer);
      controller?.abort();
      timer = setTimeout(loadIssues, 180);
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
  const viewerStage = $('#imageViewerStage');
  const viewerScale = $('[data-image-zoom="reset"]', imageViewer || document);
  let imageScale = 1;
  let imageX = 0;
  let imageY = 0;
  let imageDrag = null;
  function updateImageTransform() {
    if (!viewerImage || !viewerStage || !viewerStage.clientWidth || !viewerStage.clientHeight) return;
    const fit = Math.min(viewerStage.clientWidth / (viewerImage.naturalWidth || viewerStage.clientWidth), viewerStage.clientHeight / (viewerImage.naturalHeight || viewerStage.clientHeight));
    const width = (viewerImage.naturalWidth || viewerStage.clientWidth) * fit;
    const height = (viewerImage.naturalHeight || viewerStage.clientHeight) * fit;
    imageX = Math.max(-Math.max(0, (width * imageScale - viewerStage.clientWidth) / 2), Math.min(imageX, Math.max(0, (width * imageScale - viewerStage.clientWidth) / 2)));
    imageY = Math.max(-Math.max(0, (height * imageScale - viewerStage.clientHeight) / 2), Math.min(imageY, Math.max(0, (height * imageScale - viewerStage.clientHeight) / 2)));
    viewerImage.style.transform = `translate(${imageX}px, ${imageY}px) scale(${imageScale})`;
    viewerStage.classList.toggle('is-zoomed', imageScale > 1);
    viewerScale.textContent = `${Math.round(imageScale * 100)}%`;
  }
  function zoomImage(nextScale, clientX, clientY) {
    if (!viewerStage) return;
    const scale = Math.max(1, Math.min(8, nextScale));
    const bounds = viewerStage.getBoundingClientRect();
    const x = clientX - bounds.left - bounds.width / 2;
    const y = clientY - bounds.top - bounds.height / 2;
    const ratio = scale / imageScale;
    imageX = x - (x - imageX) * ratio;
    imageY = y - (y - imageY) * ratio;
    imageScale = scale;
    updateImageTransform();
  }
  function resetImage() {
    imageScale = 1; imageX = 0; imageY = 0;
    updateImageTransform();
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-preview-url]');
    if (!link || !imageViewer || !viewerImage || !viewerDownload || !viewerStage) return;
    event.preventDefault();
    resetImage();
    viewerImage.src = link.dataset.previewUrl;
    viewerImage.alt = link.querySelector('img')?.alt || '图片预览';
    viewerDownload.href = link.href;
    imageViewer.showModal();
    resetImage();
  });
  viewerImage?.addEventListener('load', updateImageTransform);
  imageViewer?.addEventListener('wheel', event => {
    event.preventDefault();
    if (!viewerStage.contains(event.target)) return;
    const delta = Math.max(-240, Math.min(240, event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewerStage.clientHeight : 1)));
    zoomImage(imageScale * Math.exp(-delta * 0.0015), event.clientX, event.clientY);
  }, { passive: false });
  $$('[data-image-zoom]', imageViewer || document).forEach(button => button.addEventListener('click', () => {
    if (button.dataset.imageZoom === 'reset') { resetImage(); return; }
    const bounds = viewerStage.getBoundingClientRect();
    zoomImage(imageScale * (button.dataset.imageZoom === 'in' ? 1.25 : 0.8), bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
  }));
  viewerStage?.addEventListener('pointerdown', event => {
    if (imageScale <= 1 || event.button !== 0) return;
    imageDrag = { x: event.clientX, y: event.clientY, imageX, imageY };
    viewerStage.setPointerCapture(event.pointerId);
    viewerStage.classList.add('is-dragging');
  });
  viewerStage?.addEventListener('pointermove', event => {
    if (!imageDrag) return;
    imageX = imageDrag.imageX + event.clientX - imageDrag.x;
    imageY = imageDrag.imageY + event.clientY - imageDrag.y;
    updateImageTransform();
  });
  function stopImageDrag() { imageDrag = null; viewerStage?.classList.remove('is-dragging'); }
  viewerStage?.addEventListener('pointerup', stopImageDrag);
  viewerStage?.addEventListener('pointercancel', stopImageDrag);
  window.addEventListener('resize', () => { if (imageViewer?.open) updateImageTransform(); });
  imageViewer?.addEventListener('click', event => { if (event.target === imageViewer) imageViewer.close(); });
  imageViewer?.addEventListener('close', () => { stopImageDrag(); viewerImage.removeAttribute('src'); resetImage(); });

  $$('[data-timer-start]').forEach(label => {
    const start = new Date(`${label.dataset.timerStart}Z`).getTime();
    const update = () => { const seconds = Math.max(Math.floor((Date.now()-start)/1000),0); label.textContent = `结束 ${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`; };
    update(); setInterval(update, 1000);
  });
})();
