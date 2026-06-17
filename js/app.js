(async function () {
  const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  const currentMonth = new Date().getMonth() + 1; // 1-indexed

  const monthLabel = document.getElementById('current-month');
  const grid = document.getElementById('plant-grid');
  const noResults = document.getElementById('no-results');
  const slider = document.getElementById('month-slider');

  let plants;
  try {
    const resp = await fetch('data/plants.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    plants = await resp.json();
  } catch (err) {
    console.error('Failed to load plant data:', err);
    grid.innerHTML =
      '<p class="error">Unable to load plant data. Please try again later.</p>';
    return;
  }

  function render(month) {
    monthLabel.textContent =
      `Showing plants blooming in ${MONTH_NAMES[month - 1]}`;

    const blooming = plants.filter(p => p.bloom_months.includes(month));

    grid.innerHTML = '';
    noResults.hidden = blooming.length !== 0;

    for (const plant of blooming) {
      const photoHtml = plant.photo_url
        ? `<img src="${plant.photo_url}" alt="${escapeHtml(plant.common_name)}" loading="lazy">`
        : '<div class="photo-missing">No photo available</div>';

      const card = document.createElement('article');
      card.className = 'plant-card';
      card.innerHTML = `
        <div class="plant-photo-wrap">${photoHtml}</div>
        <div class="plant-info">
          <h2 class="common-name">${escapeHtml(plant.common_name)}</h2>
          <p class="scientific-name"><em>${escapeHtml(plant.scientific_name)}</em></p>
          <div class="plant-links">
            <a href="${plant.calflora_url}" target="_blank" rel="noopener">Calflora</a>
            <a href="${plant.calscape_url}" target="_blank" rel="noopener">Calscape</a>
          </div>
          ${plant.photo_attribution
            ? `<p class="photo-credit">${escapeHtml(plant.photo_attribution)}</p>`
            : ''}
        </div>
      `;

      const img = card.querySelector('img');
      if (img) {
        img.addEventListener('error', () => {
          img.closest('.plant-photo-wrap').innerHTML =
            '<div class="photo-missing">No photo available</div>';
        });
      }

      grid.appendChild(card);
    }
  }

  slider.value = currentMonth;
  slider.addEventListener('input', () => render(Number(slider.value)));
  render(currentMonth);

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
