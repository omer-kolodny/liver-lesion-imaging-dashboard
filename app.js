const grid = document.querySelector('#lesionGrid');
const dialog = document.querySelector('#lesionDialog');
const dialogContent = document.querySelector('#dialogContent');
const search = document.querySelector('#lesionSearch');
let lesions = [];
let activeFilter = 'all';

const fmt = (n, digits = 1) => n == null ? '—' : Number(n).toFixed(digits);
const delta = n => n == null ? '—' : `${n >= 0 ? '+' : ''}${Number(n).toFixed(1)}%`;

function classification(row) {
  if (row.lesion_id === 'L13') return {key:'caution', cls:'unreliable', label:'Unreliable match', note:'The apparent reduction is most likely a segmentation or matching inconsistency and should not be read as true regression.'};
  if (row.lesion_id === 'U01') return {key:'caution', cls:'caution', label:'Unmatched', note:'No distinct corresponding automated component was found on the January scan.'};
  if (['L14','L15','L16'].includes(row.lesion_id)) return {key:'caution', cls:'caution', label:'Sub-centimeter', note:'Too small for dependable percentage volume or attenuation change.'};
  if (Math.abs(row.long_change_pct) <= 5) return {key:'stable', cls:'stable', label:'Broadly stable', note:Math.abs(row.volume_change_pct) > 15 ? 'Stable by diameter; the volume percentage is contour-sensitive.' : 'Measurements are broadly stable within expected technical variation.'};
  return {key:'caution', cls:'caution', label:row.long_change_pct < 0 ? 'Measured decrease' : 'Measured increase', note:'A measured change is present, but protocol and contour variability limit certainty.'};
}

function imageFor(row) {
  return `assets/lesions/${row.lesion_id === 'U01' ? 'old_only_U01' : `lesion_${row.lesion_id}`}.webp`;
}

function renderCards() {
  const term = search.value.trim().toLowerCase();
  const visible = lesions.filter(row => {
    const status = classification(row);
    const major = row.jan_volume_ml >= 2 || row.dec_volume_ml >= 2;
    const filterMatch = activeFilter === 'all' || activeFilter === status.key || (activeFilter === 'major' && major);
    const textMatch = !term || `${row.lesion_id} ${row.segment}`.toLowerCase().includes(term);
    return filterMatch && textMatch;
  });
  grid.innerHTML = visible.map(row => {
    const status = classification(row);
    return `<article class="lesion-card" tabindex="0" data-id="${row.lesion_id}" aria-label="Open ${row.lesion_id} details">
      <img loading="lazy" src="${imageFor(row)}" alt="${row.lesion_id} CT comparison">
      <div class="lesion-body">
        <div class="lesion-top"><h3>${row.lesion_id} · Segment ${row.segment || '—'}</h3><span class="status ${status.cls}">${status.label}</span></div>
        <div class="lesion-metrics">
          <div><span>Long axis</span><b>${fmt(row.dec_long_mm)} → ${fmt(row.jan_long_mm)} mm</b></div>
          <div><span>Volume</span><b>${fmt(row.dec_volume_ml,2)} → ${fmt(row.jan_volume_ml,2)} mL</b></div>
          <div><span>Diameter change</span><b>${delta(row.long_change_pct)}</b></div>
          <div><span>Volume change</span><b>${delta(row.volume_change_pct)}</b></div>
        </div>
      </div>
    </article>`;
  }).join('') || '<p class="muted">No lesions match this filter.</p>';
}

function openLesion(id) {
  const row = lesions.find(item => item.lesion_id === id);
  const status = classification(row);
  dialogContent.innerHTML = `<div class="dialog-inner">
    <div class="dialog-header"><div><div class="eyebrow">Lesion detail</div><h2>${row.lesion_id} · Liver segment ${row.segment || '—'}</h2></div><span class="status ${status.cls}">${status.label}</span></div>
    <img src="${imageFor(row)}" alt="${row.lesion_id} full CT comparison">
    <div class="dialog-stats">
      <div><span>Long axis</span><b>${fmt(row.dec_long_mm)} → ${fmt(row.jan_long_mm)} mm (${delta(row.long_change_pct)})</b></div>
      <div><span>Perpendicular</span><b>${fmt(row.dec_short_mm)} → ${fmt(row.jan_short_mm)} mm</b></div>
      <div><span>Craniocaudal</span><b>${fmt(row.dec_cc_mm)} → ${fmt(row.jan_cc_mm)} mm</b></div>
      <div><span>Volume</span><b>${fmt(row.dec_volume_ml,2)} → ${fmt(row.jan_volume_ml,2)} mL (${delta(row.volume_change_pct)})</b></div>
      <div><span>Median attenuation</span><b>${fmt(row.dec_median_hu)} → ${fmt(row.jan_median_hu)} HU</b></div>
      <div><span>Core below 40 HU</span><b>${fmt(row.dec_fraction_below_40hu_pct)}% → ${fmt(row.jan_fraction_below_40hu_pct)}%</b></div>
    </div>
    ${row.proximity_mm ? `<div class="proximity"><h3>Approximate edge-to-edge proximity</h3><div class="proximity-grid">${Object.entries(row.proximity_mm).map(([name,distance]) => `<div><span>${name.replaceAll('_',' ')}</span><b>${fmt(distance)} mm</b></div>`).join('')}</div><small>Distances come from automated masks and are not suitable for operative planning.</small></div>` : ''}
    <div class="dialog-note"><b>Assessment:</b> ${status.note}<br><b>Confidence:</b> ${row.confidence}<br><small>The below-40-HU value is a low-attenuation proxy and does not establish necrosis.</small></div>
  </div>`;
  dialog.showModal();
}

function renderVolumeChart() {
  const rows = lesions.filter(r => r.lesion_id !== 'U01').slice(0, 12);
  const max = Math.max(...rows.flatMap(r => [r.dec_volume_ml || 0, r.jan_volume_ml || 0]));
  const width = value => Math.max(1.5, Math.sqrt(value / max) * 100);
  document.querySelector('#volumeChart').innerHTML = `<div class="chart-legend"><span><i style="background:#38bdf8"></i>25 Dec</span><span><i style="background:#5eead4"></i>19 Jan</span><span>Square-root scale</span></div>` + rows.map(row => `<div class="chart-row"><div class="chart-label">${row.lesion_id}</div><div class="bars"><div class="bar dec" style="width:${width(row.dec_volume_ml)}%"></div><div class="bar jan" style="width:${width(row.jan_volume_ml)}%"></div></div><div class="chart-values">${fmt(row.dec_volume_ml,2)} / ${fmt(row.jan_volume_ml,2)} mL</div></div>`).join('');
}

fetch('lesions.json').then(r => r.json()).then(data => { lesions = data; renderCards(); renderVolumeChart(); });

document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  button.classList.add('active'); activeFilter = button.dataset.filter; renderCards();
}));
search.addEventListener('input', renderCards);
grid.addEventListener('click', event => { const card = event.target.closest('.lesion-card'); if (card) openLesion(card.dataset.id); });
grid.addEventListener('keydown', event => { if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('.lesion-card')) openLesion(event.target.dataset.id); });
document.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });

const reportUrl = new URL('assets/Liver_Lesion_CT_Comparison.pdf', window.location.href).href;
const shareStatus = document.querySelector('#shareStatus');

async function shareReport(event) {
  const button = event.currentTarget;
  const originalLabel = button.textContent;
  try {
    if (navigator.share) {
      await navigator.share({
        title: 'RadioLens Liver Imaging Report',
        text: 'Interactive liver imaging analysis and lesion comparison report.',
        url: reportUrl,
      });
      if (shareStatus) shareStatus.textContent = 'Report shared.';
      return;
    }
    await navigator.clipboard.writeText(reportUrl);
    button.textContent = 'Link copied';
    if (shareStatus) shareStatus.textContent = 'The public PDF link was copied to your clipboard.';
    setTimeout(() => { button.textContent = originalLabel; }, 1800);
  } catch (error) {
    if (error.name === 'AbortError') return;
    window.open(reportUrl, '_blank', 'noopener');
    if (shareStatus) shareStatus.textContent = 'The PDF opened. Use your browser Share button to send it or save it.';
  }
}

document.querySelectorAll('.share-report').forEach(button => button.addEventListener('click', shareReport));
