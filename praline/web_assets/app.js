const source = document.querySelector('#source-code');
const fileInput = document.querySelector('#file-input');
const dropZone = document.querySelector('#drop-zone');
const analyzeButton = document.querySelector('#analyze-button');
const formError = document.querySelector('#form-error');
let currentFilename = 'input.c';
let latestResult = null;

function setFilename(name) {
  currentFilename = name || 'input.c';
  const selected = currentFilename !== 'input.c';
  document.querySelector('#upload-title').textContent = selected ? currentFilename : 'Drop a .c file here';
  document.querySelector('#upload-copy').textContent = selected ? 'Loaded and ready to analyze' : 'or click to browse · single file · maximum 1 MB';
}

async function loadFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.c')) {
    showError('Choose a C source file ending in .c.');
    return;
  }
  if (file.size > 1_000_000) {
    showError('Choose a file smaller than 1 MB.');
    return;
  }
  source.value = await file.text();
  setFilename(file.name);
  showError('');
}

function showError(message) {
  formError.textContent = message;
  formError.hidden = !message;
}

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') fileInput.click();
});
fileInput.addEventListener('change', () => loadFile(fileInput.files[0]));
for (const eventName of ['dragenter', 'dragover']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragging');
  });
}
for (const eventName of ['dragleave', 'drop']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragging');
  });
}
dropZone.addEventListener('drop', (event) => loadFile(event.dataTransfer.files[0]));

document.querySelectorAll('.result-tabs button').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.result-tabs button').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelectorAll('.tab-content').forEach((item) => item.classList.toggle('active', item.id === `tab-${button.dataset.tab}`));
  });
});

function decisionMeta(decision, loopCount) {
  if (decision === 'safe') return ['Safe to parallelize', `${loopCount} supported loop${loopCount === 1 ? '' : 's'} can be transformed under the recorded assumptions.`];
  if (decision === 'unsafe') return ['Parallelization refused', 'Praline found a concrete conflict that can change the program when iterations overlap.'];
  return ['More information needed', 'Praline could not prove independence, so it left the source unchanged.'];
}

function renderTargetResult(result, decision) {
  const target = result.target === 'gpu' ? 'gpu' : 'cpu';
  const box = document.querySelector('#target-result');
  const kind = document.querySelector('#target-kind');
  const title = document.querySelector('#target-title');
  const detail = document.querySelector('#target-detail');
  const state = document.querySelector('#target-state');
  box.className = `target-result ${target}`;
  kind.textContent = `${target.toUpperCase()} TARGET`;

  if (decision !== 'safe') {
    box.classList.add('blocked');
    title.textContent = `${target.toUpperCase()} transformation not created`;
    detail.textContent = 'Praline only transforms loops after static analysis establishes that they are safe.';
    state.textContent = 'BLOCKED';
    return;
  }
  if (result.transformation_error) {
    box.classList.add('blocked');
    title.textContent = `${target.toUpperCase()} generation needs more information`;
    detail.textContent = result.transformation_error.message;
    state.textContent = 'NOT GENERATED';
    return;
  }
  if (target === 'gpu') {
    title.textContent = 'GPU offload source prepared';
    detail.textContent = 'Praline created OpenMP GPU directives and buffer mappings. This browser did not execute them on a physical GPU.';
    state.textContent = 'NOT DEVICE-RUN';
  } else {
    title.textContent = 'CPU parallel source prepared';
    detail.textContent = 'Praline created an OpenMP parallel-for transformation for CPU threads. This browser did not execute the uploaded program.';
    state.textContent = 'NOT EXECUTED';
  }
}

function renderResult(result) {
  latestResult = result;
  const report = result.analysis || {};
  const loops = report.loops || [];
  const safeLoops = loops.filter((loop) => loop.decision === 'safe');
  const decision = loops.some((loop) => loop.decision === 'unsafe') ? 'unsafe' : safeLoops.length ? 'safe' : 'unknown';
  const [title, copy] = decisionMeta(decision, safeLoops.length);
  document.querySelector('#decision-title').textContent = title;
  document.querySelector('#decision-copy').textContent = report.status === 'error'
    ? (report.errors || []).map((error) => error.message).join(' ') || 'The source could not be analyzed.'
    : copy;
  const badge = document.querySelector('#decision-badge');
  badge.textContent = decision.toUpperCase();
  badge.className = `decision-badge ${decision}`;
  renderTargetResult(result, decision);

  const reasonList = document.querySelector('#reason-list');
  const reasons = loops.flatMap((loop) => loop.reasons || []);
  if (!reasons.length && report.errors) reasons.push(...report.errors);
  reasonList.innerHTML = '';
  for (const reason of reasons) {
    const card = document.createElement('div');
    card.className = 'reason-card';
    const code = document.createElement('div');
    code.className = 'reason-code';
    code.textContent = reason.code || 'ANALYSIS_ERROR';
    const message = document.createElement('p');
    message.className = 'reason-message';
    message.textContent = reason.message || 'No explanation available.';
    card.append(code, message);
    reasonList.append(card);
  }

  const assumptions = [...new Set(loops.flatMap((loop) => loop.assumptions || []))];
  const assumptionList = document.querySelector('#assumption-list');
  assumptionList.innerHTML = '';
  document.querySelector('#assumptions-block').hidden = assumptions.length === 0;
  for (const assumption of assumptions) {
    const item = document.createElement('li');
    item.textContent = assumption;
    assumptionList.append(item);
  }

  document.querySelector('#analysis-json').textContent = JSON.stringify(report, null, 2);

  document.querySelector('#empty-result').hidden = true;
  document.querySelector('#loading-result').hidden = true;
  document.querySelector('#result-content').hidden = false;
}

function downloadText(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

document.querySelector('#download-json').addEventListener('click', () => {
  if (latestResult?.analysis) downloadText('analysis.json', JSON.stringify(latestResult.analysis, null, 2), 'application/json');
});

function updateTargetUI() {
  const target = document.querySelector('input[name="target"]:checked').value;
  document.querySelector('.gpu-only-field').hidden = target !== 'gpu';
  document.querySelector('#target-help').textContent = target === 'gpu'
    ? 'GPU prepares OpenMP offload code for large independent workloads. It requires buffer sizes and compatible GPU hardware.'
    : 'CPU prepares OpenMP code for parallel threads on the processor.';
  analyzeButton.querySelector('span').textContent = `Analyze for ${target.toUpperCase()}`;
}

document.querySelectorAll('input[name="target"]').forEach((input) => input.addEventListener('change', updateTargetUI));
updateTargetUI();

analyzeButton.addEventListener('click', async () => {
  const code = source.value;
  if (!code.trim()) {
    showError('Paste C source or choose a .c file first.');
    source.focus();
    return;
  }
  showError('');
  analyzeButton.disabled = true;
  analyzeButton.querySelector('span').textContent = 'Analyzing…';
  document.querySelector('#empty-result').hidden = true;
  document.querySelector('#result-content').hidden = true;
  document.querySelector('#loading-result').hidden = false;
  try {
    const selectedTarget = document.querySelector('input[name="target"]:checked').value;
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        filename: currentFilename,
        target: selectedTarget,
        extents: selectedTarget === 'gpu' ? document.querySelector('#extents').value : '',
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Analysis failed.');
    renderResult(data);
  } catch (error) {
    document.querySelector('#loading-result').hidden = true;
    document.querySelector('#empty-result').hidden = false;
    showError(error.message || 'Analysis failed.');
  } finally {
    analyzeButton.disabled = false;
    updateTargetUI();
  }
});

source.value = '';
setFilename('input.c');
