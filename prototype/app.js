(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const views = $$('.view');
  const navItems = $$('.nav-item');
  const modal = $('#quickModal');
  const toast = $('#toast');
  let activeTimer = null;
  let elapsed = 0;

  function showView(id) {
    const target = document.getElementById(id);
    if (!target) return;
    views.forEach(view => view.classList.toggle('active', view === target));
    navItems.forEach(item => item.classList.toggle('active', item.dataset.view === id));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function notify(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(notify.timeout);
    notify.timeout = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  $$('[data-view]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault();
      showView(button.dataset.view);
    });
  });

  const pcbData = [
    { serial: 'S1485-003', detail: 'S1485 · PCB V1.1', state: '处理中 · 3个未解决问题' },
    { serial: 'S1385-002', detail: 'S1385 · PCB V2.0', state: '等待中 · 1个未解决问题' },
    { serial: 'S1246-007', detail: 'S1246 · PCB V1.3', state: '已完成 · 无未解决问题' }
  ];

  const pcbLookup = $('#pcbLookup');
  const lookupMenu = $('#lookupMenu');

  function renderLookup(query) {
    const value = query.trim().toLowerCase();
    if (!value) {
      lookupMenu.classList.remove('show');
      return;
    }
    const matches = pcbData.filter(row => `${row.serial} ${row.detail}`.toLowerCase().includes(value)).slice(0, 10);
    lookupMenu.innerHTML = matches.length
      ? matches.map(row => `<button class="lookup-result" data-serial="${row.serial}"><span><strong>${row.serial}</strong><small>${row.detail}</small></span><small>${row.state}</small></button>`).join('')
      : '<div class="lookup-result"><small>没有匹配的 PCB 序列号</small></div>';
    lookupMenu.classList.add('show');
    $$('.lookup-result[data-serial]', lookupMenu).forEach(button => {
      button.addEventListener('click', () => {
        pcbLookup.value = button.dataset.serial;
        lookupMenu.classList.remove('show');
        showView('pcb-detail');
      });
    });
  }

  pcbLookup.addEventListener('input', event => renderLookup(event.target.value));
  document.addEventListener('click', event => {
    if (!event.target.closest('.pcb-lookup')) lookupMenu.classList.remove('show');
  });
  document.addEventListener('keydown', event => {
    if (event.altKey && event.key.toLowerCase() === 'p') {
      event.preventDefault();
      pcbLookup.focus();
    }
    if (event.key === 'Escape') {
      modal.classList.remove('show');
      lookupMenu.classList.remove('show');
    }
  });

  function openModal() {
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    setTimeout(() => $('#quickTitle').focus(), 30);
  }

  function closeModal() {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
  }

  $('#quickCreate').addEventListener('click', openModal);
  $('#pcbAddRecord').addEventListener('click', openModal);
  $('#closeModal').addEventListener('click', closeModal);
  $('#cancelModal').addEventListener('click', closeModal);
  modal.addEventListener('click', event => {
    if (event.target === modal) closeModal();
  });

  $$('.record-switch button').forEach(button => {
    button.addEventListener('click', () => {
      $$('.record-switch button').forEach(item => item.classList.toggle('active', item === button));
      $('#createRecord').textContent = `创建${button.dataset.kind}`;
    });
  });

  $('#createRecord').addEventListener('click', () => {
    const title = $('#quickTitle').value.trim();
    if (!title) {
      notify('请先填写标题');
      $('#quickTitle').focus();
      return;
    }
    closeModal();
    $('#quickTitle').value = '';
    notify('原型：记录已创建并归入 S1485-003');
    showView('issue-detail');
  });

  $('#timerButton').addEventListener('click', () => {
    const button = $('#timerButton');
    const label = $('#timerLabel');
    if (activeTimer) {
      clearInterval(activeTimer);
      activeTimer = null;
      button.classList.remove('running');
      label.textContent = '开始计时';
      notify(`本次计时 ${formatTime(elapsed)}，已生成工作记录草稿`);
      elapsed = 0;
      return;
    }
    button.classList.add('running');
    elapsed = 0;
    label.textContent = '00:00';
    activeTimer = setInterval(() => {
      elapsed += 1;
      label.textContent = formatTime(elapsed);
    }, 1000);
    notify('已开始计时：未命名工作');
  });

  function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${minutes}:${secs}`;
  }

  $('#globalSearch').addEventListener('click', () => {
    showView('search-view');
    setTimeout(() => $('#searchInput').focus(), 50);
  });

  const searchInput = $('#searchInput');
  function renderSearch(value) {
    const query = value.trim();
    const results = $('#searchResults');
    if (!query) {
      results.innerHTML = '';
      return;
    }
    results.innerHTML = `
      <article class="search-hit"><span>PCB 序列号</span><h3>S1485-003</h3><p>S1485 · PCB V1.1 · 3个未解决问题</p></article>
      <article class="search-hit"><span>问题</span><h3>S1485 大电流带载异常</h3><p>恢复原始走线后仍在约11 A触发保护，优先排查焊盘铜箔与采样链。</p></article>
      <article class="search-hit"><span>Cell · 今天 11:42</span><h3>测试记录</h3><p>关键词“${escapeHtml(query)}”匹配当前测试记录。原型默认只展示最相关结果。</p></article>`;
  }
  searchInput.addEventListener('input', event => renderSearch(event.target.value));

  function escapeHtml(value) {
    return value.replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  }

  const fileInput = $('#fileInput');
  const uploadPreview = $('#uploadPreview');
  function previewFiles(files) {
    [...files].filter(file => file.type.startsWith('image/')).slice(0, 6).forEach(file => {
      const image = document.createElement('img');
      image.src = URL.createObjectURL(file);
      image.alt = file.name;
      image.onload = () => URL.revokeObjectURL(image.src);
      uploadPreview.appendChild(image);
    });
  }
  fileInput.addEventListener('change', event => previewFiles(event.target.files));

  const composer = $('.composer');
  const cellInput = $('#cellInput');
  ['dragenter', 'dragover'].forEach(name => composer.addEventListener(name, event => {
    event.preventDefault();
    composer.classList.add('dragover');
  }));
  ['dragleave', 'drop'].forEach(name => composer.addEventListener(name, event => {
    event.preventDefault();
    composer.classList.remove('dragover');
  }));
  composer.addEventListener('drop', event => previewFiles(event.dataTransfer.files));
  cellInput.addEventListener('paste', event => {
    const files = [...event.clipboardData.items].filter(item => item.kind === 'file').map(item => item.getAsFile());
    if (files.length) previewFiles(files);
  });

  function wrapSelection(before, after = before) {
    const start = cellInput.selectionStart;
    const end = cellInput.selectionEnd;
    const selected = cellInput.value.slice(start, end) || '重点内容';
    cellInput.setRangeText(`${before}${selected}${after}`, start, end, 'end');
    cellInput.focus();
  }
  $('[data-format="bold"]').addEventListener('click', () => wrapSelection('**'));
  $('[data-format="highlight"]').addEventListener('click', () => wrapSelection('=='));
  $$('.color-dot').forEach(button => button.addEventListener('click', () => wrapSelection(`[${button.dataset.color}]`, `[/${button.dataset.color}]`)));

  $('#sendCell').addEventListener('click', () => {
    const value = cellInput.value.trim();
    if (!value && !uploadPreview.children.length) {
      notify('请输入内容或添加图片');
      return;
    }
    const article = document.createElement('article');
    article.className = 'chat-cell';
    const type = $('#cellType').value;
    article.innerHTML = `<div class="cell-avatar">R</div><div><div class="chat-meta"><strong>ROOT</strong><time>刚刚</time><span class="tag blue">${escapeHtml(type)}</span></div><div class="chat-bubble"><p>${escapeHtml(value || '上传了图片附件').replace(/\n/g, '<br>')}</p></div></div>`;
    $('#chatStream').appendChild(article);
    cellInput.value = '';
    uploadPreview.innerHTML = '';
    notify('Cell 已添加（原型数据不会持久保存）');
    article.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  $$('.segmented').forEach(group => {
    $$('button', group).forEach(button => button.addEventListener('click', () => {
      $$('button', group).forEach(item => item.classList.toggle('active', item === button));
      notify(`原型筛选：${button.textContent}`);
    }));
  });
})();
