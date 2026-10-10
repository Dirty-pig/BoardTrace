// Reading view for prose-heavy knowledge tables; stored Markdown stays untouched.
document.querySelectorAll('.knowledge-detail-body .rich-content table').forEach((table, index) => {
  const headers = Array.from(table.querySelectorAll('thead th'));
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  const columns = headers.length;
  if (columns < 3 || columns > 5 || !rows.length || rows.some(row => row.cells.length !== columns)) return;
  const cells = rows.flatMap(row => Array.from(row.cells));
  if (!cells.some(cell => cell.textContent.trim().length > 70)) return;

  const wrapper = document.createElement('section');
  wrapper.className = 'knowledge-table-reader';
  const toolbar = document.createElement('div');
  toolbar.className = 'knowledge-view-toolbar';
  const label = document.createElement('span');
  label.textContent = `${rows.length} 项 · 按条目阅读或横向对照`;
  const controls = document.createElement('div');
  const cards = document.createElement('div');
  cards.className = 'knowledge-reading-cards';
  cards.id = `knowledge-cards-${index}`;
  const scroll = document.createElement('div');
  scroll.className = 'knowledge-table-scroll';
  scroll.id = `knowledge-table-${index}`;
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', '知识表格对照，可横向滚动');
  const buttons = ['条目阅读', '表格对照'].map((text, view) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.setAttribute('aria-controls', view ? scroll.id : cards.id);
    button.addEventListener('click', () => select(view));
    controls.append(button);
    return button;
  });
  function select(view) {
    cards.hidden = Boolean(view);
    scroll.hidden = !view;
    buttons.forEach((button, position) => button.setAttribute('aria-pressed', String(position === view)));
  }
  rows.forEach((row, rowIndex) => {
    const card = document.createElement('article');
    card.className = 'knowledge-reading-card';
    const title = document.createElement('h3');
    const number = document.createElement('span');
    number.className = 'knowledge-item-number';
    number.textContent = String(rowIndex + 1).padStart(2, '0');
    title.append(number);
    Array.from(row.cells[0].childNodes).forEach(node => title.append(node.cloneNode(true)));
    const fields = document.createElement('dl');
    Array.from(row.cells).slice(1).forEach((cell, fieldIndex) => {
      const field = document.createElement('div');
      const term = document.createElement('dt');
      term.textContent = headers[fieldIndex + 1].textContent;
      const description = document.createElement('dd');
      Array.from(cell.childNodes).forEach(node => description.append(node.cloneNode(true)));
      field.append(term, description);
      fields.append(field);
    });
    card.append(title, fields);
    cards.append(card);
  });
  toolbar.append(label, controls);
  table.before(wrapper);
  scroll.append(table);
  wrapper.append(toolbar, cards, scroll);
  select(0);
});
