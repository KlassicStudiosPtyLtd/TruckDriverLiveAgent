/**
 * Demo flow logic — guided walkthrough with live API calls.
 * Each page triggers real simulated conversations via the backend.
 */

const TOTAL_PAGES = 6;
const DRIVER_ID = 'DRV-001';  // Dazza for demos
let currentPage = 1;

// Track call state per page
const pageState = {};

// Sound effects
let ringAudio = null;
let sfxReady = false;

// Pre-fetch audio buffers so they're ready instantly on click
const sfxBuffers = {};
async function preloadSfx() {
  try {
    const [ringResp, endResp] = await Promise.all([
      fetch('/static/sfx/ring.mp3'),
      fetch('/static/sfx/end_call.mp3'),
    ]);
    if (ringResp.ok) sfxBuffers.ring = await ringResp.blob();
    if (endResp.ok) sfxBuffers.end = await endResp.blob();
    sfxReady = true;
    console.log('SFX preloaded');
  } catch (e) {
    console.warn('SFX preload failed:', e);
  }
}
preloadSfx();

// Stop all audio and end active calls on page unload (refresh / navigate away)
window.addEventListener('beforeunload', () => {
  stopRinging();
  stopPlayback();
  // Close WebSocket so server knows we're gone
  if (demoWs) { demoWs.onclose = null; demoWs.close(); }
  // End any active call so the server stops generating audio
  const activePage = findActiveCallPage();
  if (activePage) {
    navigator.sendBeacon(`/dashboard/api/end-call/${DRIVER_ID}`);
  }
});

// WebSocket
let demoWs = null;
let playbackCtx = null;
let nextPlayTime = 0;

// Timer intervals per page
const timerIntervals = {};

// --- Progress bar ---

function buildProgressBar() {
  const container = document.getElementById('progress-steps');
  container.innerHTML = '';
  for (let i = 1; i <= TOTAL_PAGES; i++) {
    const dot = document.createElement('div');
    dot.className = 'demo-step-dot';
    dot.dataset.page = i;
    dot.onclick = () => goToPage(i);
    container.appendChild(dot);
  }
  updateProgressBar();
}

function updateProgressBar() {
  const dots = document.querySelectorAll('.demo-step-dot');
  dots.forEach(dot => {
    const p = parseInt(dot.dataset.page);
    dot.classList.toggle('active', p === currentPage);
    dot.classList.toggle('completed', p < currentPage);
  });
  const activePage = document.getElementById(`page-${currentPage}`);
  const title = activePage ? activePage.dataset.title : '';
  document.getElementById('progress-label').textContent = title;
}

// --- Page navigation ---

function goToPage(page) {
  if (page < 1 || page > TOTAL_PAGES) return;

  // Hide all pages
  document.querySelectorAll('.demo-page').forEach(p => p.classList.remove('active'));

  // Show target page
  currentPage = page;
  const target = document.getElementById(`page-${page}`);
  if (target) {
    target.classList.add('active');
    // Re-trigger animation
    target.style.animation = 'none';
    target.offsetHeight; // reflow
    target.style.animation = '';
  }

  updateProgressBar();
  sessionStorage.setItem('betty-demo-page', page);
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Load frames when entering page 2 for the first time
  if (page === 2 && !framesLoaded) {
    loadFatigueFrames();
  }
}

// --- WebSocket connection ---

function connectDemoWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/dashboard/ws`;
  demoWs = new WebSocket(url);
  demoWs.binaryType = 'arraybuffer';

  demoWs.onmessage = (event) => {
    // Binary = audio
    if (event.data instanceof ArrayBuffer) {
      playAudioChunk(event.data);
      return;
    }

    const data = JSON.parse(event.data);

    if (data.type === 'transcript') {
      handleTranscript(data);
    } else if (data.type === 'call_started') {
      handleCallStarted(data);
    } else if (data.type === 'call_ended') {
      handleCallEnded(data);
    } else if (data.type === 'card') {
      handleCard(data);
    }
  };

  demoWs.onclose = () => {
    setTimeout(connectDemoWs, 3000);
  };

  demoWs.onerror = () => {
    demoWs.close();
  };
}

// --- Audio playback ---

// Cabin noise loop (continuous background during calls)
let cabinNoiseSource = null;
let cabinNoiseBuffer = null;
let cabinNoiseGain = null;

async function loadCabinNoise() {
  try {
    const resp = await fetch('/static/sfx/cabin_noise.pcm');
    if (!resp.ok) return;
    const raw = await resp.arrayBuffer();
    // PCM is 16-bit signed, 24kHz mono — convert to Float32
    const int16 = new Int16Array(raw);
    // We'll store the raw int16 and create the AudioBuffer when playbackCtx exists
    cabinNoiseBuffer = int16;
    console.log('Cabin noise loaded:', (int16.length / 24000).toFixed(1) + 's');
  } catch (e) {
    console.warn('Failed to load cabin noise:', e);
  }
}
loadCabinNoise();

function startCabinNoise() {
  if (!playbackCtx || !cabinNoiseBuffer || cabinNoiseSource) return;

  const float32 = new Float32Array(cabinNoiseBuffer.length);
  for (let i = 0; i < cabinNoiseBuffer.length; i++) {
    float32[i] = cabinNoiseBuffer[i] / 32768;
  }
  const buf = playbackCtx.createBuffer(1, float32.length, 24000);
  buf.getChannelData(0).set(float32);

  cabinNoiseSource = playbackCtx.createBufferSource();
  cabinNoiseSource.buffer = buf;
  cabinNoiseSource.loop = true;

  cabinNoiseGain = playbackCtx.createGain();
  cabinNoiseGain.gain.value = 0.3;  // background level

  cabinNoiseSource.connect(cabinNoiseGain);
  cabinNoiseGain.connect(playbackCtx.destination);
  cabinNoiseSource.start();
  console.log('Cabin noise loop started');
}

function stopCabinNoise() {
  if (cabinNoiseSource) {
    try { cabinNoiseSource.stop(); } catch (e) {}
    cabinNoiseSource = null;
  }
  cabinNoiseGain = null;
}

function initPlayback() {
  if (playbackCtx) return;
  playbackCtx = new AudioContext({ sampleRate: 24000 });
  nextPlayTime = 0;
  // Start continuous cabin noise loop
  startCabinNoise();
}

function stopPlayback() {
  stopCabinNoise();
  if (playbackCtx) {
    playbackCtx.close();
    playbackCtx = null;
  }
  nextPlayTime = 0;
}

function playAudioChunk(arrayBuffer) {
  if (!playbackCtx) initPlayback();
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  const buf = playbackCtx.createBuffer(1, float32.length, 24000);
  buf.getChannelData(0).set(float32);
  const now = playbackCtx.currentTime;
  const startTime = Math.max(now, nextPlayTime);
  const source = playbackCtx.createBufferSource();
  source.buffer = buf;
  source.connect(playbackCtx.destination);
  source.start(startTime);
  nextPlayTime = startTime + buf.duration;
}

// --- Transcript handling ---

function handleTranscript(data) {
  // Find which page has an active call
  const page = findActiveCallPage();
  if (!page) return;

  const feed = document.getElementById(`transcript-${page}`);
  if (!feed) return;

  // Clear placeholder
  const placeholder = feed.querySelector('.demo-transcript-placeholder');
  if (placeholder) placeholder.remove();

  const line = document.createElement('div');
  line.className = 'demo-transcript-line';
  const speakerClass = data.speaker === 'betty' ? 'betty' : '';
  const speakerLabel = data.speaker === 'betty' ? 'Betty' : 'Driver';
  line.innerHTML = `<span class="demo-transcript-speaker ${speakerClass}">${speakerLabel}:</span> ${data.text}`;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;
}

function findActiveCallPage() {
  for (const [page, state] of Object.entries(pageState)) {
    if (state.callActive) return page;
  }
  return null;
}

// --- Call lifecycle ---

function handleCallStarted(data) {
  const page = findPendingCallPage();
  if (!page) return;

  // Ensure ringtone plays for at least MIN_RING_MS before connecting
  const elapsed = Date.now() - ringStartedAt;
  const delay = Math.max(0, MIN_RING_MS - elapsed);

  setTimeout(() => _completeCallStart(page), delay);
}

function _completeCallStart(page) {
  if (!pageState[page]) return;

  pageState[page].callPending = false;
  pageState[page].callActive = true;
  pageState[page].callStartTime = Date.now();

  // Stop ringing, start playing call audio
  stopRinging();

  const statusEl = document.getElementById(`call-status-${page}`);
  const timerEl = document.getElementById(`call-timer-${page}`);

  if (statusEl) {
    statusEl.innerHTML = `<span class="demo-status-pill demo-status-connected"><span class="dot dot-connected"></span> Connected</span>`;
  }
  if (timerEl) {
    timerEl.classList.add('active');
  }

  initPlayback();

  // Start timer
  timerIntervals[page] = setInterval(() => {
    const elapsed = Math.floor((Date.now() - pageState[page].callStartTime) / 1000);
    const min = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const sec = String(elapsed % 60).padStart(2, '0');
    if (timerEl) timerEl.textContent = `${min}:${sec}`;
  }, 1000);
}

function handleCallEnded(data) {
  const page = findActiveCallPage();
  if (!page) return;

  pageState[page].callActive = false;
  pageState[page].callCompleted = true;

  // Stop ringing (in case it's still going) and play end-call sound
  stopRinging();
  playEndCallSound();

  const statusEl = document.getElementById(`call-status-${page}`);
  const timerEl = document.getElementById(`call-timer-${page}`);

  if (statusEl) {
    statusEl.innerHTML = `<span class="demo-status-pill demo-status-ended"><span class="dot dot-idle"></span> Call ended</span>`;
  }
  if (timerEl) timerEl.classList.remove('active');

  if (timerIntervals[page]) {
    clearInterval(timerIntervals[page]);
    delete timerIntervals[page];
  }

  stopPlayback();

  // Reset button states per page
  if (page === '2') {
    const btn = document.getElementById('btn-fatigue');
    if (btn) { btn.textContent = 'Detect Drowsy Eyes'; btn.disabled = false; }
  } else if (page === '3') {
    const btn = document.getElementById('btn-escalation');
    if (btn) { btn.textContent = 'Detect Microsleep'; btn.disabled = false; }
  } else if (page === '4') {
    if (!pageState['4'].call2Done) {
      // Call 1 just ended — update button and enable Call 2
      const btn1 = document.getElementById('btn-memory-1');
      if (btn1) btn1.textContent = 'Call 1: Complete';
      const btn2 = document.getElementById('btn-memory-2');
      if (btn2) btn2.disabled = false;
      setCallStatus(4, 'ended', 'Call 1 complete — now trigger Call 2');
    } else {
      // Call 2 just ended
      const btn2 = document.getElementById('btn-memory-2');
      if (btn2) btn2.textContent = 'Call 2: Complete';
    }
  }
}

function findPendingCallPage() {
  for (const [page, state] of Object.entries(pageState)) {
    if (state.callPending && !state.callActive) return page;
  }
  return null;
}

// --- Card handling ---

function handleCard(data) {
  // Show on current page's card area, or page 3 for incident, or page 5
  let targetArea = null;
  if (currentPage === 3 || findActiveCallPage() === '3') {
    targetArea = document.getElementById('cards-area-3');
  } else if (currentPage === 5) {
    targetArea = document.getElementById('cards-area-5');
  }

  if (!targetArea) return;

  // Remove any spinner
  const spinner = targetArea.querySelector('.demo-card-spinner');
  if (spinner) spinner.remove();

  const typeLabels = {
    rest_stop: 'Rest Stop Recommendation',
    wellness_summary: 'Shift Wellness Summary',
    incident: 'Incident Report',
  };
  const label = typeLabels[data.card_type] || data.card_type;

  const wrapper = document.createElement('div');
  wrapper.className = 'card-item';
  wrapper.innerHTML = `
    <div class="card-item-header">
      <span class="card-item-label">${label}</span>
      <span class="card-item-time">${new Date().toLocaleTimeString()}</span>
    </div>
    <img src="${data.image_url}" alt="${label}" class="card-image"
         onclick="window.open('${data.image_url}', '_blank')" style="max-width:100%;">
  `;
  targetArea.prepend(wrapper);
}

// --- Trigger actions ---

async function triggerFatigue() {
  const btn = document.getElementById('btn-fatigue');
  btn.disabled = true;
  btn.textContent = 'Triggering...';

  pageState['2'] = { callPending: true, callActive: false };

  setCallStatus(2, 'ringing', 'Ringing...');
  startRinging();

  try {
    await fetch('/api/triggers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        driver_id: DRIVER_ID,
        trigger_type: 'fatigue_camera',
        severity: 'high',
        fatigue_event_type: 'droopy_eyes',
        simulate: true,
      }),
    });
    btn.textContent = 'Call in progress...';
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Detect Drowsy Eyes';
    setCallStatus(2, 'idle', 'Failed to trigger — try again');
  }
}

async function triggerEscalation() {
  const btn = document.getElementById('btn-escalation');
  btn.disabled = true;
  btn.textContent = 'Triggering...';

  pageState['3'] = { callPending: true, callActive: false };

  setCallStatus(3, 'ringing', 'Ringing...');
  startRinging();

  try {
    await fetch('/api/triggers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        driver_id: DRIVER_ID,
        trigger_type: 'fatigue_camera',
        severity: 'high',
        fatigue_event_type: 'head_nod',
        simulate: true,
        persona_mood: 'irritable',
        persona_resistance: 'high',
      }),
    });
    btn.textContent = 'Call in progress...';
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Detect Microsleep';
    setCallStatus(3, 'idle', 'Failed to trigger — try again');
  }
}

async function triggerMemoryCall1() {
  const btn = document.getElementById('btn-memory-1');
  btn.disabled = true;
  btn.textContent = 'Calling...';

  pageState['4'] = { callPending: true, callActive: false, call2Done: false };

  setCallStatus(4, 'ringing', 'Call 1: Ringing...');
  startRinging();

  try {
    await fetch('/api/triggers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        driver_id: DRIVER_ID,
        trigger_type: 'companion_check_in',
        simulate: true,
      }),
    });
    btn.textContent = 'Call 1 in progress...';
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Call 1: Companion Check-in';
    setCallStatus(4, 'idle', 'Failed — try again');
  }
}

async function triggerMemoryCall2() {
  const btn = document.getElementById('btn-memory-2');
  btn.disabled = true;
  btn.textContent = 'Calling...';

  pageState['4'].callPending = true;
  pageState['4'].callActive = false;
  pageState['4'].call2Done = true;

  // Clear transcript for call 2
  const feed = document.getElementById('transcript-4');
  feed.innerHTML = '<div class="demo-transcript-placeholder">Call 2 starting...</div>';

  setCallStatus(4, 'ringing', 'Call 2: Ringing...');
  startRinging();

  try {
    await fetch('/api/triggers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        driver_id: DRIVER_ID,
        trigger_type: 'fatigue_camera',
        severity: 'medium',
        fatigue_event_type: 'yawning',
        simulate: true,
      }),
    });
    btn.textContent = 'Call 2 in progress...';
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Call 2: Fatigue Event';
    setCallStatus(4, 'idle', 'Failed — try again');
  }
}

// --- Card generation (page 5) ---

async function generateDemoCard(cardType, scenario) {
  const area = document.getElementById('cards-area-5');

  // Add spinner
  const spinner = document.createElement('div');
  spinner.className = 'card-item card-generating demo-card-spinner';
  const typeLabels = {
    rest_stop: 'Rest Stop Recommendation',
    wellness: 'Shift Wellness Summary',
    incident: 'Incident Report',
  };
  spinner.innerHTML = `
    <div class="card-item-header">
      <span class="card-item-label">${typeLabels[cardType] || cardType}</span>
      <span class="card-item-time">Generating...</span>
    </div>
    <div class="card-spinner-area">
      <div class="card-spinner"></div>
      <div class="card-spinner-text">${cardType === 'rest_stop' ? 'Generating scenic background with Imagen 4...' : 'Generating card...'}</div>
    </div>
  `;
  area.prepend(spinner);

  try {
    const res = await fetch('/api/cards/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ driver_id: DRIVER_ID, card_type: cardType, scenario }),
    });
    const data = await res.json();
    spinner.remove();

    if (data.image_url) {
      handleCard({
        card_type: data.card_type || cardType,
        driver_id: DRIVER_ID,
        image_url: data.image_url,
      });
    }
  } catch (e) {
    spinner.remove();
    console.error('Card generation failed:', e);
  }
}

// --- Helpers ---

let ringStartedAt = 0;
const MIN_RING_MS = 3000;  // ring for at least 3 seconds

function startRinging() {
  stopRinging();
  // Create a fresh Audio element from preloaded blob or URL
  if (sfxBuffers.ring) {
    ringAudio = new Audio(URL.createObjectURL(sfxBuffers.ring));
  } else {
    ringAudio = new Audio('/static/sfx/ring.mp3');
  }
  ringAudio.loop = true;
  ringAudio.volume = 0.8;
  ringStartedAt = Date.now();
  ringAudio.play().then(() => {
    console.log('Ringtone playing');
  }).catch(e => {
    console.error('Ring play failed:', e);
  });
}

function stopRinging() {
  if (ringAudio) {
    ringAudio.pause();
    ringAudio.currentTime = 0;
    ringAudio = null;
  }
  ringStartedAt = 0;
}

function playEndCallSound() {
  let audio;
  if (sfxBuffers.end) {
    audio = new Audio(URL.createObjectURL(sfxBuffers.end));
  } else {
    audio = new Audio('/static/sfx/end_call.mp3');
  }
  audio.volume = 0.8;
  audio.play().catch(() => {});
}

function setCallStatus(page, status, text) {
  const el = document.getElementById(`call-status-${page}`);
  if (!el) return;

  const statusMap = {
    idle: 'demo-status-idle',
    ringing: 'demo-status-ringing',
    connected: 'demo-status-connected',
    ended: 'demo-status-ended',
  };

  const dotMap = {
    idle: 'dot-idle',
    ringing: 'dot-ringing',
    connected: 'dot-connected',
    ended: 'dot-idle',
  };

  el.innerHTML = `<span class="demo-status-pill ${statusMap[status] || ''}">
    <span class="dot ${dotMap[status] || ''}"></span> ${text}
  </span>`;
}

// --- Transcript polling (backup for simulated calls) ---

let lastTranscriptCounts = {};

async function pollTranscripts() {
  const page = findActiveCallPage();
  if (!page) return;

  try {
    const res = await fetch(`/dashboard/api/transcript/${DRIVER_ID}`);
    const data = await res.json();
    const key = `page-${page}`;
    if (!lastTranscriptCounts[key]) lastTranscriptCounts[key] = 0;

    if (data.transcript && data.transcript.length > lastTranscriptCounts[key]) {
      const newEntries = data.transcript.slice(lastTranscriptCounts[key]);
      // Consolidate fragments per speaker
      const lines = [];
      for (const entry of newEntries) {
        const last = lines[lines.length - 1];
        if (last && last.speaker === entry.speaker) {
          last.text += ' ' + entry.text;
        } else {
          lines.push({ speaker: entry.speaker, text: entry.text });
        }
      }
      for (const line of lines) {
        handleTranscript({
          speaker: line.speaker,
          text: line.text,
          driver_id: DRIVER_ID,
        });
      }
      lastTranscriptCounts[key] = data.transcript.length;
    }
  } catch (e) {
    // ignore
  }
}

// --- Video frames preview (page 2) ---

let framesLoaded = false;

async function loadFatigueFrames() {
  const strip = document.getElementById('frames-strip');
  if (!strip) return;

  try {
    const res = await fetch('/api/videos/frames?event_type=droopy_eyes&severity=high&max_frames=10');
    const data = await res.json();

    if (!data.frames || data.frames.length === 0) {
      strip.innerHTML = '<div style="color:#64748b; padding:1rem;">No frames available</div>';
      framesLoaded = true;
      return;
    }

    strip.innerHTML = '';
    data.frames.forEach((b64, i) => {
      const item = document.createElement('div');
      item.className = 'demo-frame-item';
      item.innerHTML = `
        <img src="data:image/jpeg;base64,${b64}" alt="Frame ${i + 1}">
        <div class="demo-frame-label">Frame ${i + 1}/${data.count}</div>
      `;
      strip.appendChild(item);
    });

    framesLoaded = true;
  } catch (e) {
    strip.innerHTML = '<div style="color:#64748b; padding:1rem;">Failed to load frames</div>';
    console.error('Frame loading failed:', e);
  }
}

// --- Init ---

const savedPage = parseInt(sessionStorage.getItem('betty-demo-page'));
if (savedPage >= 1 && savedPage <= TOTAL_PAGES) {
  currentPage = savedPage;
}
buildProgressBar();
goToPage(currentPage);
connectDemoWs();
setInterval(pollTranscripts, 2000);
