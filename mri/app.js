const fmt = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
const signed = (value, suffix = '%') => value == null ? '—' : `${value >= 0 ? '+' : ''}${fmt(value, 1)}${suffix}`;

let data;
let filter = 'all';
let fromDate;
let toDate;
const grid = document.querySelector('#lesionGrid');
const dialog = document.querySelector('#lesionDialog');
const content = document.querySelector('#dialogContent');
const measurement = (row, date) => row.measurements[date];
const dateLabel = date => data.studies.find(item => item.date === date)?.label || date;
const change = (first, second) => first && second ? (second.volume_ml / first.volume_ml - 1) * 100 : null;

function relevant(row) {
  return Boolean(measurement(row, fromDate) || measurement(row, toDate));
}

function classification(row) {
  if (row.kind === 'node') return {key: 'node', label: 'Extrahepatic target', cls: 'node'};
  const first = measurement(row, fromDate);
  const second = measurement(row, toDate);
  const values = [first, second].filter(Boolean);
  const maxVolume = Math.max(...values.map(item => item.volume_ml));
  if (!first || !second) return {key: 'review', label: 'Unmatched · review', cls: 'review'};
  if (maxVolume < .5) return {key: 'review', label: 'Small focus · review', cls: 'review'};
  if (Object.values(row.validation).filter(Boolean).some(item => item.status !== 'supported')) return {key: 'review', label: 'Validation review', cls: 'review'};
  return {key: 'matched', label: 'Tracked liver focus', cls: 'supported'};
}

function metric(item, key) {
  if (!item) return '—';
  if (key === 'volume') return `${fmt(item.volume_ml, 2)} mL`;
  if (key === 'size') return `${fmt(item.long_mm)} × ${fmt(item.short_mm)} mm`;
  if (key === 'adc') return item.features.adc_median == null ? 'Not available' : `${fmt(item.features.adc_median, 2)} ×10⁻³`;
  return '—';
}

function renderTimeline() {
  const options = data.studies.map(item => `<option value="${item.date}">${item.label}</option>`).join('');
  const from = document.querySelector('#fromStudy');
  const to = document.querySelector('#toStudy');
  from.innerHTML = options;
  to.innerHTML = options;
  from.value = fromDate;
  to.value = toDate;
  document.querySelector('#timelineTrack').innerHTML = data.studies.map((study, index) => `
    <div class="timeline-point ${[fromDate, toDate].includes(study.date) ? 'selected' : ''} ${index === data.studies.length - 1 ? 'latest' : ''}">
      <span>${index + 1}</span><b>${study.label}</b><small>${study.lesion_count} automatic contours</small>
    </div>`).join('');
}

function renderOverview() {
  const first = data.studies.find(item => item.date === fromDate);
  const second = data.studies.find(item => item.date === toDate);
  const hepaticRows = data.lesions.filter(row => row.kind !== 'node' && relevant(row));
  const matched = hepaticRows.filter(row => measurement(row, fromDate) && measurement(row, toDate)).length;
  const latest = data.studies.at(-1);
  const volumeChange = (second.tumor_volume_ml / first.tumor_volume_ml - 1) * 100;
  const burdenChange = second.tumor_burden_pct - first.tumor_burden_pct;
  const node = data.lesions.find(row => row.kind === 'node');
  const nodeFirst = node && measurement(node, fromDate);
  const nodeSecond = node && measurement(node, toDate);

  document.querySelector('#heroBurden').textContent = data.ct_crosscheck.ct_hepatic_candidates;
  document.querySelector('#volumeDelta').textContent = 'QC only';
  document.querySelector('#volumeValues').textContent = `${fmt(first.tumor_volume_ml, 2)} → ${fmt(second.tumor_volume_ml, 2)} mL automatically contoured`;
  document.querySelector('#burdenDelta').textContent = 'Not valid';
  document.querySelector('#burdenValues').textContent = 'MRI contour fraction is not total disease burden';
  document.querySelector('#matchCount').textContent = `${matched} / ${hepaticRows.length}`;
  document.querySelector('#repeatDice').textContent = `${fmt(first.repeat_dice, 3)} / ${fmt(second.repeat_dice, 3)}`;
  document.querySelector('#latestCount').textContent = data.ct_crosscheck.ct_hepatic_candidates;
  document.querySelector('#latestLiver').textContent = `${fmt(latest.liver_volume_ml, 1)} mL`;
  document.querySelector('#latestTumor').textContent = `${fmt(latest.tumor_volume_ml, 1)} mL`;
  document.querySelector('#latestNode').textContent = latest.extrahepatic_target_volume_ml == null ? '—' : `${fmt(latest.extrahepatic_target_volume_ml, 1)} mL`;

  document.querySelector('#findings').innerHTML = `
    <li><b>Known working inventory: 8 liver targets</b><p>This inventory is anchored to the near-date CT. The MRI model contours only some targets on each sequence; targets without a contour are not called absent.</p></li>
    <li><b>Aggregate MRI “burden” withdrawn</b><p>The model outlined different portions of lesions on different dates, so ${fmt(first.tumor_volume_ml, 1)} to ${fmt(second.tumor_volume_ml, 1)} mL must not be interpreted as total disease-volume change.</p></li>
    <li><b>${matched} automatic contour tracks are present on both dates</b><p>Small or weakly overlapping regions are left unmatched rather than assigned to the wrong lesion.</p></li>
    <li><b>August contour agreement is only ${fmt(latest.repeat_dice, 3)}</b><p>The phase-4 and true-late MRI model outputs differ substantially. This is why automatic contour volume is now treated as quality-control data, not total tumor burden.</p></li>
    <li><b>The nodal target is reported separately</b><p>${nodeFirst && nodeSecond ? `${fmt(nodeFirst.volume_ml, 1)} to ${fmt(nodeSecond.volume_ml, 1)} mL (${signed(change(nodeFirst, nodeSecond))}).` : 'It is not included in liver tumor burden.'}</p></li>`;

  const january = data.studies.find(item => item.date === '2026-01-22');
  const major = data.lesions.filter(row => row.kind !== 'node').slice(0, 2);
  const trend = major.map(row => {
    const jan = measurement(row, '2026-01-22');
    const aug = measurement(row, '2026-08-26');
    return jan && aug ? `${row.id}: ${signed(change(jan, aug))}` : null;
  }).filter(Boolean).join(' · ');
  document.querySelector('#clinicalInterpretation').innerHTML = `
    <div><b>The direction is favorable, but the old MRI percentage was not defensible</b><p>The two dominant tracked regions are smaller (${trend}), but the aggregate automatic-mask decrease cannot be treated as the percentage of disease eliminated.</p></div>
    <div><b>The extrahepatic nodal target also became much smaller</b><p>${node ? `Its automated volume changed from ${fmt(measurement(node, '2026-01-22')?.volume_ml, 1)} to ${fmt(measurement(node, '2026-08-26')?.volume_ml, 1)} mL.` : 'It is tracked outside the liver totals.'}</p></div>
    <div><b>“Alive versus dead” cannot be reduced to one trustworthy percentage</b><p>The complete August DWI and ADC are now included. They add evidence about diffusion restriction, but size, enhancement, DWI, and ADC must be interpreted together and still do not directly measure living cells.</p></div>
    <div class="caution"><b>Best working inventory: 8 liver targets, not 5</b><p>The near-date CT identifies 8 hepatic targets plus 1 separate nodal target. The number 5 describes automatic MRI contours only—not the number of lesions present.</p></div>`;

  const cross = data.ct_crosscheck;
  document.querySelector('#ctLiverCount').textContent = cross.ct_hepatic_candidates;
  document.querySelector('#mriLiverCount').textContent = cross.mri_hepatic_foci;
  document.querySelector('#confirmedCrossMatches').textContent = cross.automatic_mri_supported_hepatic_targets ?? cross.confirmed_mask_matches;
  document.querySelector('#crosscheckNote').textContent = cross.note;
  const targetGrid = document.querySelector('#ctTargetGrid');
  if (targetGrid) targetGrid.innerHTML = (cross.targets || []).map(target => `
    <button class="target-card" type="button" data-panel="${target.panel}">
      <img loading="lazy" src="${target.panel}" alt="${target.id} complete August multiparametric MRI review">
      <span><b>${target.id} · ${target.kind === 'node' ? 'Portocaval node' : `Segment ${target.ct_segment}`}</b><em>${target.status}</em><small>CT anchor ${fmt(target.ct_volume_ml, 2)} mL · MRI support: ${target.supported_by_sequences.join(', ') || 'no confident automatic contour'}</small></span>
    </button>`).join('');
  targetGrid?.querySelectorAll('.target-card').forEach(button => button.addEventListener('click', () => window.open(button.dataset.panel.replace('.webp', '.png'), '_blank', 'noopener')));
}

function panel(row, date) {
  return `assets/panels/${row.id}_${date}.webp`;
}

function card(row) {
  const state = classification(row);
  const first = measurement(row, fromDate);
  const second = measurement(row, toDate);
  return `<article class="lesion-card" data-id="${row.id}">
    <div class="card-pair"><img loading="lazy" src="${panel(row, fromDate)}" alt="${row.id} ${dateLabel(fromDate)}"><img loading="lazy" src="${panel(row, toDate)}" alt="${row.id} ${dateLabel(toDate)}"></div>
    <div class="lesion-body"><div class="lesion-top"><h3>${row.id} · ${row.segment_label}</h3><span class="status ${state.cls}">${state.label}</span></div>
    <div class="lesion-metrics"><div><span>Auto-mask volume</span><b>${metric(first, 'volume')} → ${metric(second, 'volume')}</b></div><div><span>Auto-mask axes</span><b>${metric(first, 'size')} → ${metric(second, 'size')}</b></div><div><span>ADC median</span><b>${metric(first, 'adc')} → ${metric(second, 'adc')}</b></div><div><span>Mask-volume change</span><b>${signed(change(first, second))}</b></div></div></div>
  </article>`;
}

function render() {
  const query = document.querySelector('#search').value.trim().toLowerCase();
  grid.innerHTML = data.lesions.filter(relevant).filter(row => {
    const state = classification(row);
    const major = Math.max(...Object.values(row.measurements).map(item => item.volume_ml)) >= 1;
    const matchesFilter = filter === 'all' || filter === state.key || (filter === 'major' && major);
    return matchesFilter && `${row.id} ${row.segment_label}`.toLowerCase().includes(query);
  }).map(card).join('');
  grid.querySelectorAll('.lesion-card').forEach(element => element.addEventListener('click', () => openLesion(data.lesions.find(row => row.id === element.dataset.id))));
}

function metricRows(item) {
  if (!item) return '<div><span>Status</span><b>No accepted corresponding focus</b></div>';
  const features = item.features;
  return `<div><span>Longest axial × perpendicular</span><b>${fmt(item.long_mm)} × ${fmt(item.short_mm)} mm</b></div>
    <div><span>3D dimensions</span><b>${item.dimensions_3d_mm.map(value => fmt(value)).join(' × ')} mm</b></div>
    <div><span>Volume</span><b>${fmt(item.volume_ml, 2)} mL</b></div>
    <div><span>ADC median</span><b>${features.adc_median == null ? 'Not available' : fmt(features.adc_median, 2) + ' ×10⁻³ mm²/s'}</b></div>
    <div><span>Low ADC &lt;1.0</span><b>${features.low_adc_fraction_pct == null ? 'Not available' : fmt(features.low_adc_fraction_pct) + '%'}</b></div>
    <div><span>DWI / liver</span><b>${features.dwi_b800.ratio == null ? 'Not available' : fmt(features.dwi_b800.ratio, 2) + '×'}</b></div>
    <div><span>T2 / liver</span><b>${fmt(features.t2_fatsat.ratio, 2)}×</b></div>
    <div><span>Late / liver</span><b>${fmt(features.late.ratio, 2)}×</b></div>
    <div><span>Low late-signal proxy</span><b>${fmt(features.low_late_signal_fraction_pct)}%</b></div>
    <div><span>Dynamic ratios P1–P4</span><b>${features.dynamic_liver_normalized.map(value => fmt(value, 2)).join(' / ')}</b></div>`;
}

function openLesion(row) {
  const first = measurement(row, fromDate);
  const second = measurement(row, toDate);
  const timeline = data.studies.map(study => {
    const item = measurement(row, study.date);
    const validation = row.validation[study.date] || {};
    return `<div><span>${study.label}</span><b>${item ? fmt(item.volume_ml, 2) + ' mL automatic mask' : 'No accepted match'}</b><small>${item ? fmt(item.long_mm) + ' × ' + fmt(item.short_mm) + ' mm · secondary-input Dice ' + fmt(validation.dice, 3) : '—'}</small></div>`;
  }).join('');
  content.innerHTML = `<div class="dialog-inner"><div class="dialog-header"><div><div class="eyebrow">${row.kind === 'node' ? 'Registered extrahepatic target' : 'Registered MRI liver-focus track'}</div><h2>${row.id} · ${row.segment_label}</h2></div><span class="status ${classification(row).cls}">${classification(row).label}</span></div>
    <div class="full-pair"><img src="${panel(row, fromDate)}" alt="${row.id} ${dateLabel(fromDate)}"><img src="${panel(row, toDate)}" alt="${row.id} ${dateLabel(toDate)}"></div>
    <div class="validation-grid"><div class="validation-box"><h3>${dateLabel(fromDate)}</h3><div class="dialog-stats">${metricRows(first)}</div></div><div class="validation-box"><h3>${dateLabel(toDate)}</h3><div class="dialog-stats">${metricRows(second)}</div></div></div>
    <div class="trend-grid">${timeline}</div><p class="dialog-note">The pink line is the longest axial boundary-to-boundary diameter on that examination; the blue line is perpendicular. Its angle may change as lesion shape or patient position changes. ADC, DWI/T2 ratios, and low late-signal fractions are imaging clues—not direct percentages of live tumor or necrosis. The complete August DWI/ADC series are included.</p></div>`;
  dialog.showModal();
}

function updateDates() {
  fromDate = document.querySelector('#fromStudy').value;
  toDate = document.querySelector('#toStudy').value;
  if (fromDate === toDate) {
    const index = data.studies.findIndex(item => item.date === toDate);
    if (index === 0) {
      toDate = data.studies[1].date;
      document.querySelector('#toStudy').value = toDate;
    } else {
      fromDate = data.studies[index - 1].date;
      document.querySelector('#fromStudy').value = fromDate;
    }
  }
  renderTimeline();
  renderOverview();
  render();
}

document.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  button.classList.add('active');
  filter = button.dataset.filter;
  render();
}));
document.querySelector('#search').addEventListener('input', render);
document.querySelector('#fromStudy').addEventListener('change', updateDates);
document.querySelector('#toStudy').addEventListener('change', updateDates);
document.querySelector('#openCrosscheck').addEventListener('click', () => window.open('assets/ct-mri-crosscheck.png?v=4', '_blank', 'noopener'));
document.querySelector('#sharePdf').addEventListener('click', async () => {
  const status = document.querySelector('#shareStatus');
  try {
    const response = await fetch('assets/Noa_Liver_MRI_Comparison.pdf?v=4');
    const blob = await response.blob();
    const file = new File([blob], 'Noa_Liver_MRI_Comparison.pdf', {type: 'application/pdf'});
    if (navigator.canShare?.({files: [file]})) {
      await navigator.share({title: 'Noa liver MRI comparison', files: [file]});
      status.textContent = 'Share sheet opened.';
    } else {
      const anchor = document.createElement('a');
      anchor.href = URL.createObjectURL(blob);
      anchor.download = file.name;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
      status.textContent = 'PDF downloaded.';
    }
  } catch (error) {
    status.textContent = 'Open the PDF, then use the browser Share button.';
  }
});

fetch('assets/report_data.json?v=4').then(response => response.json()).then(json => {
  data = json;
  fromDate = data.studies[0].date;
  toDate = data.studies.at(-1).date;
  renderTimeline();
  renderOverview();
  render();
}).catch(error => {
  grid.innerHTML = '<p>Report data could not be loaded.</p>';
  console.error(error);
});
