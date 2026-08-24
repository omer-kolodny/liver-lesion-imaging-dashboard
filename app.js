const grid = document.querySelector('#lesionGrid');
const dialog = document.querySelector('#lesionDialog');
const dialogContent = document.querySelector('#dialogContent');
const search = document.querySelector('#lesionSearch');
const fromSelect = document.querySelector('#fromStudy');
const toSelect = document.querySelector('#toStudy');
let studies = [];
let studyMap = {};
let lesions = [];
let comparisons = {};
let activeFilter = 'all';
let fromDate;
let toDate;

const fmt = (value, digits = 1) => value == null ? '—' : Number(value).toFixed(digits);
const signed = (value, suffix = '%') => value == null ? '—' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(1)}${suffix}`;
const change = (from, to) => from == null || !from || to == null ? null : (to - from) / from * 100;
const measurement = (row, date) => row.measurements[date] || { detected:false };
const comparisonKey = (first, second) => `${first}__${second}`;
const selectedComparison = () => comparisons[comparisonKey(fromDate, toDate)] || {
  level:'limited', label:'Attenuation comparability not established', score_pct:null,
  explanation:'Matched contrast timing and internal-reference measurements are not available for this pair.'
};
const metricPair = (first, second, key, suffix = '', digits = 1) =>
  `${fmt(first[key], digits)}${first[key] == null ? '' : suffix} → ${fmt(second[key], digits)}${second[key] == null ? '' : suffix}`;

function classification(row) {
  const first = measurement(row, fromDate);
  const second = measurement(row, toDate);
  const volumeChange = change(first.volume_ml, second.volume_ml);
  const small = Math.max(first.volume_ml || 0, second.volume_ml || 0) < 0.5;
  if (first.detected && !second.detected) return { key:'stable', cls:'stable', label:'Not separately detected', note:'No separate residual focus was identified by the automated later-scan model. This does not prove complete resolution.' };
  if (small) return { key:'caution', cls:'caution', label:'Small / uncertain', note:'Sub-centimeter lesion measurements and attenuation fractions are highly contour-sensitive.' };
  if (second.confidence === 'low') return { key:'caution', cls:'unreliable', label:'Low-confidence match', note:'Registration and independent-model agreement are limited for this match.' };
  if (volumeChange != null && volumeChange <= -30) return { key:'stable', cls:'stable', label:'Marked decrease', note:'The automated segmented volume decreased substantially over the selected interval.' };
  if (volumeChange != null && volumeChange <= -10) return { key:'stable', cls:'stable', label:'Measured decrease', note:'The automated segmented volume decreased over the selected interval.' };
  if (volumeChange != null && volumeChange >= 20) return { key:'caution', cls:'caution', label:'Measured increase', note:'The automated segmented volume increased and should be reviewed on the source images.' };
  return { key:'stable', cls:'stable', label:'Broadly stable', note:'No large automated volume change was measured over the selected interval.' };
}

function imageFor(row) {
  return `assets/timeline/${row.lesion_id}_${fromDate}_${toDate}.webp?v=5`;
}

function renderSelectors() {
  const options = studies.map(study => `<option value="${study.date}">${study.label}</option>`).join('');
  fromSelect.innerHTML = options;
  toSelect.innerHTML = options;
  fromSelect.value = fromDate;
  toSelect.value = toDate;
}

function renderTimelineTrack() {
  document.querySelector('#timelineTrack').innerHTML = studies.map((study, index) => {
    const selected = study.date === fromDate || study.date === toDate;
    const latest = index === studies.length - 1;
    return `<div class="timeline-point ${selected ? 'selected' : ''} ${latest ? 'latest' : ''}">
      <span>${index + 1}</span><b>${study.label}</b><small>${fmt(study.tumor_burden_pct,2)}% burden</small>
    </div>`;
  }).join('');
}

function renderOverview() {
  const first = studyMap[fromDate];
  const second = studyMap[toDate];
  const volumeChange = change(first.tumor_volume_ml, second.tumor_volume_ml);
  const burdenChange = second.tumor_burden_pct - first.tumor_burden_pct;
  const lead = lesions[0];
  const leadFirst = measurement(lead, fromDate);
  const leadSecond = measurement(lead, toDate);
  const diameterChange = change(leadFirst.long_mm, leadSecond.long_mm);
  const detected = lesions.filter(row => measurement(row, toDate).detected).length;
  const quality = selectedComparison();

  document.querySelector('#comparisonLabel').textContent = `CT comparison · ${first.label} → ${second.label}`;
  document.querySelector('#latestBurden').textContent = `${fmt(studies.at(-1).tumor_burden_pct,2)}%`;
  document.querySelector('#volumeDelta').textContent = signed(volumeChange);
  document.querySelector('#volumeValues').textContent = `${fmt(first.tumor_volume_ml,2)} → ${fmt(second.tumor_volume_ml,2)} mL`;
  document.querySelector('#burdenDelta').textContent = signed(burdenChange, ' pp');
  document.querySelector('#burdenValues').textContent = `${fmt(first.tumor_burden_pct,2)}% → ${fmt(second.tumor_burden_pct,2)}%`;
  document.querySelector('#diameterDelta').textContent = signed(diameterChange);
  document.querySelector('#diameterValues').textContent = `${fmt(leadFirst.long_mm)} → ${fmt(leadSecond.long_mm)} mm`;
  document.querySelector('#trackedCount').textContent = `${detected} / 16`;

  const fromDonut = document.querySelector('#fromDonut');
  const toDonut = document.querySelector('#toDonut');
  fromDonut.style.setProperty('--value', `${first.tumor_burden_pct}%`);
  toDonut.style.setProperty('--value', `${second.tumor_burden_pct}%`);
  document.querySelector('#fromBurden').textContent = `${fmt(first.tumor_burden_pct,2)}%`;
  document.querySelector('#toBurden').textContent = `${fmt(second.tumor_burden_pct,2)}%`;
  document.querySelector('#fromLabel').textContent = first.label;
  document.querySelector('#toLabel').textContent = second.label;
  document.querySelector('#fromBurdenDetail').innerHTML = `<b>${fmt(first.tumor_volume_ml,2)} mL</b> of ${fmt(first.liver_volume_ml,2)} mL`;
  document.querySelector('#toBurdenDetail').innerHTML = `<b>${fmt(second.tumor_volume_ml,2)} mL</b> of ${fmt(second.liver_volume_ml,2)} mL`;
  document.querySelector('#burdenChangeLine').innerHTML = `<span>Change</span><b>${signed(second.tumor_volume_ml-first.tumor_volume_ml,' mL')}</b><b>${signed(burdenChange,' percentage points')}</b>`;

  const assessment = volumeChange <= -30
    ? 'substantially lower automated tumor burden on the later scan; compatible with response, pending radiologist confirmation.'
    : volumeChange >= 20
      ? 'higher automated tumor burden on the later scan; specialist review is recommended.'
      : 'no large automated change in total tumor burden.';
  document.querySelector('#overallAssessment').textContent = assessment;

  const l01 = lesions.find(row => row.lesion_id === 'L01');
  const l02 = lesions.find(row => row.lesion_id === 'L02');
  const l01Change = change(measurement(l01, fromDate).volume_ml, measurement(l01, toDate).volume_ml);
  const l02Later = measurement(l02, toDate);
  const distances = l02Later.proximity_mm ? Object.values(l02Later.proximity_mm).filter(value => value != null) : [];
  const nearest = distances.length ? Math.min(...distances) : null;
  document.querySelector('#findingsList').innerHTML = `
    <li><span>01</span><div><b>Total segmented burden</b><p>${signed(volumeChange)} volume change and ${signed(burdenChange,' percentage points')} burden change.</p></div></li>
    <li><span>02</span><div><b>Dominant segment 3 lesion</b><p>${signed(l01Change)} automated volume change over the selected interval.</p></div></li>
    <li class="quality-${quality.level}"><span>03</span><div><b>${quality.label}${quality.score_pct == null ? '' : ` · ${fmt(quality.score_pct)}% internal-reference similarity`}</b><p>${quality.explanation}</p></div></li>
    <li><span>04</span><div><b>Vessel proximity</b><p>${nearest == null ? 'Available on the latest segmented scan.' : `L02 is approximately ${fmt(nearest)} mm from the nearest automated major-vessel mask.`}</p></div></li>
    <li class="warning-item"><span>!</span><div><b>Viability limitation</b><p>Low attenuation and enhancement ratios are proxies; single-phase CT cannot determine whether tumor cells are alive.</p></div></li>`;
}

function renderCards() {
  const term = search.value.trim().toLowerCase();
  const visible = lesions.filter(row => {
    const status = classification(row);
    const first = measurement(row, fromDate);
    const second = measurement(row, toDate);
    const major = Math.max(first.volume_ml || 0, second.volume_ml || 0) >= 2;
    const filterMatch = activeFilter === 'all' || activeFilter === status.key || (activeFilter === 'major' && major);
    const textMatch = !term || `${row.lesion_id} ${row.reference_segment}`.toLowerCase().includes(term);
    return filterMatch && textMatch;
  });
  grid.innerHTML = visible.map(row => {
    const status = classification(row);
    const first = measurement(row, fromDate);
    const second = measurement(row, toDate);
    return `<article class="lesion-card" tabindex="0" data-id="${row.lesion_id}" aria-label="Open ${row.lesion_id} details">
      <img loading="lazy" src="${imageFor(row)}" alt="${row.lesion_id} CT comparison">
      <div class="lesion-body">
        <div class="lesion-top"><h3>${row.lesion_id} · Segment ${row.reference_segment}</h3><span class="status ${status.cls}">${status.label}</span></div>
        <div class="lesion-metrics">
          <div><span>Long axis</span><b>${fmt(first.long_mm)} → ${fmt(second.long_mm)} mm</b></div>
          <div><span>Volume</span><b>${fmt(first.volume_ml,2)} → ${fmt(second.volume_ml,2)} mL</b></div>
          <div><span>Diameter change</span><b>${signed(change(first.long_mm,second.long_mm))}</b></div>
          <div><span>Volume change</span><b>${signed(change(first.volume_ml,second.volume_ml))}</b></div>
        </div>
      </div>
    </article>`;
  }).join('') || '<p class="muted">No lesions match this filter.</p>';
}

function renderVolumeChart() {
  const rows = lesions.slice(0, 12);
  const values = rows.flatMap(row => [measurement(row, fromDate).volume_ml || 0, measurement(row, toDate).volume_ml || 0]);
  const max = Math.max(...values, 1);
  const width = value => Math.max(value ? 1.5 : 0, Math.sqrt((value || 0) / max) * 100);
  document.querySelector('#volumeChart').innerHTML = `<div class="chart-legend"><span><i class="legend-from"></i>${studyMap[fromDate].label}</span><span><i class="legend-to"></i>${studyMap[toDate].label}</span><span>Square-root scale</span></div>` + rows.map(row => {
    const first = measurement(row, fromDate).volume_ml || 0;
    const second = measurement(row, toDate).volume_ml || 0;
    return `<div class="chart-row"><div class="chart-label">${row.lesion_id}</div><div class="bars"><div class="bar from" style="width:${width(first)}%"></div><div class="bar to" style="width:${width(second)}%"></div></div><div class="chart-values">${fmt(first,2)} / ${fmt(second,2)} mL</div></div>`;
  }).join('');
}

function openLesion(id) {
  const row = lesions.find(item => item.lesion_id === id);
  const first = measurement(row, fromDate);
  const second = measurement(row, toDate);
  const status = classification(row);
  const quality = selectedComparison();
  const proximity = second.proximity_mm && Object.keys(second.proximity_mm).length
    ? `<div class="proximity"><h3>Approximate edge-to-edge proximity on ${studyMap[toDate].label}</h3><div class="proximity-grid">${Object.entries(second.proximity_mm).map(([name,distance]) => `<div class="${distance < 5 ? 'near' : ''}"><span>${name.replaceAll('_',' ')}</span><b>${fmt(distance)} mm</b></div>`).join('')}</div><small>Automated masks only. These distances are not suitable for operative planning.</small></div>` : '';
  const hasAttenuation = first.median_hu != null || second.median_hu != null;
  const hasNormalized = first.vnc_corrected_enhancement_hu != null || second.vnc_corrected_enhancement_hu != null;
  const attenuation = !hasAttenuation ? '' : `<div class="proxy-panel"><div class="proxy-heading"><div><h3>Hemodynamic-aware attenuation</h3><p>${studyMap[fromDate].label} → ${studyMap[toDate].label}</p></div><span class="quality-badge ${quality.level}">${quality.label}${quality.score_pct == null ? '' : ` · ${fmt(quality.score_pct)}% reference similarity`}</span></div><div class="dialog-stats">
    <div><span>Contrast CT median</span><b>${metricPair(first,second,'median_hu',' HU')}</b></div>
    <div><span>VNC baseline median</span><b>${metricPair(first,second,'vnc_median_hu',' HU')}</b></div>
    <div><span>VNC-corrected enhancement</span><b>${metricPair(first,second,'vnc_corrected_enhancement_hu',' HU')}</b></div>
    <div><span>Enhancement vs local liver</span><b>${metricPair(first,second,'enhancement_vs_liver_pct','%')}</b></div>
    <div><span>Enhancement vs portal vein</span><b>${metricPair(first,second,'enhancement_vs_portal_pct','%')}</b></div>
    <div><span>Minimal enhancement (&lt;10 HU)</span><b>${metricPair(first,second,'minimal_enhancement_pct','%')}</b></div>
    <div><span>Absolute core below 40 HU</span><b>${metricPair(first,second,'below_40hu_pct','%')}</b></div>
    <div><span>Local liver median</span><b>${metricPair(first,second,'local_liver_median_hu',' HU')}</b></div>
    </div><small>${quality.explanation} ${hasNormalized ? 'The normalized values reduce—but do not eliminate—differences in contrast delivery and circulation.' : 'VNC-based correction is unavailable for at least one selected scan.'} These are appearance proxies, not a measurement of living tumor or pathologic necrosis.</small></div>`;
  const trend = studies.map(study => {
    const value = measurement(row, study.date);
    return `<div><span>${study.label}</span><b>${value.detected ? `${fmt(value.volume_ml,2)} mL` : 'Not detected'}</b><small>${value.long_mm == null ? '—' : `${fmt(value.long_mm)} mm long axis`}</small></div>`;
  }).join('');
  dialogContent.innerHTML = `<div class="dialog-inner">
    <div class="dialog-header"><div><div class="eyebrow">Lesion timeline</div><h2>${row.lesion_id} · Reference segment ${row.reference_segment}</h2></div><span class="status ${status.cls}">${status.label}</span></div>
    <img src="${imageFor(row)}" alt="${row.lesion_id} full CT comparison">
    <div class="dialog-stats">
      <div><span>Long axis</span><b>${fmt(first.long_mm)} → ${fmt(second.long_mm)} mm (${signed(change(first.long_mm,second.long_mm))})</b></div>
      <div><span>Perpendicular</span><b>${fmt(first.short_mm)} → ${fmt(second.short_mm)} mm</b></div>
      <div><span>Craniocaudal</span><b>${fmt(first.cc_mm)} → ${fmt(second.cc_mm)} mm</b></div>
      <div><span>Volume</span><b>${fmt(first.volume_ml,2)} → ${fmt(second.volume_ml,2)} mL (${signed(change(first.volume_ml,second.volume_ml))})</b></div>
    </div>
    <div class="trend-strip">${trend}</div>
    ${attenuation}${proximity}
    <div class="dialog-note"><b>Automated trend:</b> ${row.trend}<br><b>Selected-pair assessment:</b> ${status.note}<br><b>Latest segment-mask overlap:</b> ${second.segment || row.reference_segment}.<br><b>Match confidence:</b> ${second.confidence || 'historical automated match'}.</div>
  </div>`;
  dialog.showModal();
}

function updateComparison() {
  if (studies.findIndex(study => study.date === fromDate) >= studies.findIndex(study => study.date === toDate)) {
    const toIndex = studies.findIndex(study => study.date === toDate);
    fromDate = studies[Math.max(0, toIndex - 1)].date;
    fromSelect.value = fromDate;
  }
  renderTimelineTrack();
  renderOverview();
  renderVolumeChart();
  renderCards();
}

fetch('assets/timeline.json?v=3').then(response => response.json()).then(data => {
  studies = data.studies;
  studyMap = Object.fromEntries(studies.map(study => [study.date, study]));
  lesions = data.lesions;
  comparisons = data.comparisons || {};
  toDate = studies.at(-1).date;
  fromDate = studies.at(-2).date;
  renderSelectors();
  updateComparison();
});

fromSelect.addEventListener('change', () => { fromDate = fromSelect.value; updateComparison(); });
toSelect.addEventListener('change', () => { toDate = toSelect.value; updateComparison(); });
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  button.classList.add('active'); activeFilter = button.dataset.filter; renderCards();
}));
search.addEventListener('input', renderCards);
grid.addEventListener('click', event => { const card = event.target.closest('.lesion-card'); if (card) openLesion(card.dataset.id); });
grid.addEventListener('keydown', event => { if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('.lesion-card')) openLesion(event.target.dataset.id); });
document.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });

const reportUrl = new URL('assets/Liver_Lesion_CT_Comparison.pdf?v=5', window.location.href).href;
const shareStatus = document.querySelector('#shareStatus');
async function shareReport(event) {
  const button = event.currentTarget;
  const originalLabel = button.textContent;
  try {
    if (navigator.share) {
      await navigator.share({ title:'RadioLens Liver Imaging Report', text:'Interactive liver imaging analysis and lesion comparison report.', url:reportUrl });
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
