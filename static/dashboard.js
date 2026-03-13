/**
 * Dashboard logic: WebSocket for real-time updates, trigger sending,
 * live transcription feed, driver status polling.
 */

let currentCallId = null;
let callTimerInterval = null;
let callStartTime = null;
let dashboardWs = null;

// --- Call sound effects ---
const ringAudio = new Audio('/sfx/ring.mp3');
ringAudio.loop = true;
const endCallAudio = new Audio('/sfx/end_call.mp3');

// --- WebSocket for real-time updates ---

// --- Audio playback for simulated calls ---
let playbackCtx = null;
let nextPlayTime = 0;

function initPlayback() {
  if (playbackCtx) return;
  playbackCtx = new AudioContext({ sampleRate: 24000 });
  nextPlayTime = 0;
}

function stopPlayback() {
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

function connectDashboardWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/dashboard/ws`;
  dashboardWs = new WebSocket(url);
  dashboardWs.binaryType = 'arraybuffer';

  dashboardWs.onmessage = (event) => {
    // Binary = audio PCM data
    if (event.data instanceof ArrayBuffer) {
      playAudioChunk(event.data);
      return;
    }

    const data = JSON.parse(event.data);

    if (data.type === 'transcript') {
      // Stop ringing once conversation begins
      ringAudio.pause();
      ringAudio.currentTime = 0;
      addTranscript(data.speaker, data.text, data.driver_id);
    } else if (data.type === 'call_started') {
      addLocalLog('CALL', `Call started with ${data.driver_id} (trigger: ${data.trigger_type})${data.simulated ? ' [SIM]' : ''}`);
      ringAudio.currentTime = 0;
      ringAudio.play().catch(() => {});
      initPlayback();
      refreshStatus();
    } else if (data.type === 'call_ended') {
      addLocalLog('CALL', `Call ended with ${data.driver_id}`);
      ringAudio.pause();
      ringAudio.currentTime = 0;
      endCallAudio.currentTime = 0;
      endCallAudio.play().catch(() => {});
      stopPlayback();
      refreshStatus();
    } else if (data.type === 'call_initiated') {
      addLocalLog('TRIGGER', `Call initiated for ${data.driver_id} (risk: ${data.risk_score?.toFixed(2)})`);
    } else if (data.type === 'shift_started' || data.type === 'shift_event' || data.type === 'shift_ended') {
      handleShiftMessage(data);
    } else if (data.type === 'card') {
      displayCard(data);
    }
  };

  dashboardWs.onclose = () => {
    setTimeout(connectDashboardWs, 3000);
  };

  dashboardWs.onerror = () => {
    dashboardWs.close();
  };
}

// --- Status polling ---

async function refreshStatus() {
  try {
    const res = await fetch('/dashboard/api/status');
    const data = await res.json();
    updateDriverStatuses(data.drivers);
    updateCallStatus(data.active_calls);
    updateEventLog(data.event_log);
  } catch (e) {
    console.error('Status refresh failed:', e);
  }
}

function updateDriverStatuses(drivers) {
  const container = document.getElementById('driver-list');
  container.innerHTML = drivers.map(d => `
    <div class="driver-card" data-driver-id="${d.driver_id}">
      <div>
        <div class="driver-name">${d.first_name} ${d.last_name}</div>
        <div class="driver-detail">${d.vehicle_rego} — ${d.current_route}</div>
        <div class="driver-detail">${d.hours_driven.toFixed(1)}h driven | ${d.minutes_to_break.toFixed(0)}min to break | ${d.recent_event_count} recent events</div>
      </div>
      <div>
        <span class="status-badge ${d.on_call ? 'status-connected' : 'status-idle'}">
          <span class="dot ${d.on_call ? 'dot-connected' : 'dot-idle'}"></span>
          ${d.on_call ? 'On Call' : 'Idle'}
        </span>
      </div>
    </div>
  `).join('');
}

function updateCallStatus(calls) {
  const badge = document.getElementById('call-status-badge');
  const info = document.getElementById('call-info');
  const endBtn = document.getElementById('btn-end-call');

  if (calls.length > 0) {
    const call = calls[0];
    currentCallId = call.driver_id;

    const statusMap = {
      'ringing': { cls: 'status-ringing', dot: 'dot-ringing', text: 'Ringing...' },
      'connected': { cls: 'status-connected', dot: 'dot-connected', text: 'Connected' },
    };
    const s = statusMap[call.status] || { cls: 'status-idle', dot: 'dot-idle', text: call.status };
    badge.className = `status-badge ${s.cls}`;
    badge.innerHTML = `<span class="dot ${s.dot}"></span> ${s.text}`;
    info.textContent = `Driver: ${call.driver_id} | Trigger: ${call.trigger_type}`;
    endBtn.style.display = 'inline-flex';

    if (call.status === 'connected' && !callTimerInterval) {
      callStartTime = new Date();
      callTimerInterval = setInterval(updateTimer, 1000);
      document.getElementById('call-timer').classList.add('active');
    }
  } else {
    currentCallId = null;
    badge.className = 'status-badge status-idle';
    badge.innerHTML = '<span class="dot dot-idle"></span> No active call';
    info.textContent = 'Select a driver and trigger an event to initiate a call.';
    endBtn.style.display = 'none';
    if (callTimerInterval) {
      clearInterval(callTimerInterval);
      callTimerInterval = null;
    }
    document.getElementById('call-timer').classList.remove('active');
    document.getElementById('call-timer').textContent = '00:00';
  }
}

function updateTimer() {
  if (!callStartTime) return;
  const elapsed = Math.floor((new Date() - callStartTime) / 1000);
  const min = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const sec = String(elapsed % 60).padStart(2, '0');
  document.getElementById('call-timer').textContent = `${min}:${sec}`;
}

function updateEventLog(events) {
  if (!events || events.length === 0) return;
  const container = document.getElementById('event-log');
  container.innerHTML = events.map(e => {
    const time = new Date(e.timestamp).toLocaleTimeString();
    const typeClass = e.type.includes('escalat') ? 'log-type-escalation'
      : e.type.includes('call') ? 'log-type-call'
      : e.type.includes('transcript') ? 'log-type-transcript'
      : 'log-type-trigger';
    return `<div class="log-entry">
      <span class="log-time">${time}</span>
      <span class="log-type ${typeClass}">${e.type.toUpperCase()}</span>
      <span class="log-message">${e.message}</span>
    </div>`;
  }).join('');
}

// --- Trigger sending ---

async function sendTrigger(triggerType) {
  const driverId = document.getElementById('driver-select').value;
  const simulate = document.getElementById('simulate-toggle').checked;
  const payload = {
    driver_id: driverId,
    trigger_type: triggerType,
    simulate: simulate,
    ...getPersonaPayload(),
  };

  if (triggerType === 'fatigue_camera') {
    payload.severity = document.getElementById('fatigue-severity').value;
    payload.fatigue_event_type = document.getElementById('fatigue-type').value;
  } else if (triggerType === 'erratic_driving') {
    payload.erratic_sub_type = document.getElementById('erratic-type').value;
  }

  try {
    const res = await fetch('/api/triggers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    console.log('Trigger sent:', data);
    addLocalLog('TRIGGER', `${triggerType} sent for ${driverId}`);
    setTimeout(refreshStatus, 500);
  } catch (e) {
    console.error('Trigger failed:', e);
    addLocalLog('ERROR', `Failed to send trigger: ${e.message}`);
  }
}

async function driverCallsBetty() {
  const driverId = document.getElementById('driver-select').value;
  const simulate = document.getElementById('simulate-toggle').checked;
  try {
    const res = await fetch(`/api/call/driver-initiate/${driverId}?simulate=${simulate}`, {
      method: 'POST',
    });
    const data = await res.json();
    console.log('Driver calls Betty:', data);
    addLocalLog('CALL', `Driver ${driverId} calling Betty${simulate ? ' [SIM]' : ''}`);
    setTimeout(refreshStatus, 500);
  } catch (e) {
    addLocalLog('ERROR', `Failed to initiate driver call: ${e.message}`);
  }
}

async function endCall() {
  if (!currentCallId) return;
  try {
    const res = await fetch(`/dashboard/api/end-call/${currentCallId}`, { method: 'POST' });
    const data = await res.json();
    console.log('Call ended:', data);
    callStartTime = null;
    setTimeout(refreshStatus, 500);
  } catch (e) {
    console.error('End call failed:', e);
  }
}

// --- Transcription feed ---

function addTranscript(speaker, text, driverId) {
  const feed = document.getElementById('transcript-feed');
  // Clear placeholder
  if (feed.querySelector('div[style]')) {
    feed.innerHTML = '';
  }
  const line = document.createElement('div');
  line.className = 'transcript-line';
  line.innerHTML = `<span class="transcript-speaker">${speaker}:</span> ${text}`;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;

  // Also add to event log
  addLocalLog('TRANSCRIPT', `[${speaker}] ${text}`);
}

// --- Local log helper ---

function addLocalLog(type, message) {
  const container = document.getElementById('event-log');
  const time = new Date().toLocaleTimeString();
  const typeClass = type === 'ERROR' ? 'log-type-escalation'
    : type === 'TRANSCRIPT' ? 'log-type-transcript'
    : type === 'CALL' ? 'log-type-call'
    : type === 'SHIFT' ? 'log-type-shift'
    : type === 'CARD' ? 'log-type-card'
    : 'log-type-trigger';
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-type ${typeClass}">${type}</span>
    <span class="log-message">${message}</span>`;
  container.prepend(entry);
}

// --- Simulation transcript polling ---

let lastTranscriptCount = 0;

async function pollTranscript() {
  if (!currentCallId) {
    lastTranscriptCount = 0;
    return;
  }
  try {
    const res = await fetch(`/dashboard/api/transcript/${currentCallId}`);
    const data = await res.json();
    if (data.transcript && data.transcript.length > lastTranscriptCount) {
      // Concatenate fragments per speaker into full lines
      const newEntries = data.transcript.slice(lastTranscriptCount);
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
        addTranscript(line.speaker, line.text, currentCallId);
      }
      lastTranscriptCount = data.transcript.length;
    }
  } catch (e) {
    // ignore polling errors
  }
}

// --- Shift simulation ---

let shiftRunning = false;

function updateEventCountLabel() {
  document.getElementById('shift-event-label').textContent =
    document.getElementById('shift-event-count').value;
}

async function startShift() {
  const driverId = document.getElementById('driver-select').value;
  const numEvents = parseInt(document.getElementById('shift-event-count').value);
  const clearMem = document.getElementById('shift-clear-memory').checked;

  try {
    const res = await fetch('/api/triggers/simulate-shift', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        driver_id: driverId,
        num_events: numEvents,
        clear_memory: clearMem,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      shiftRunning = true;
      document.getElementById('btn-start-shift').style.display = 'none';
      document.getElementById('btn-stop-shift').style.display = 'inline-flex';
      document.getElementById('shift-progress').style.display = 'block';
      document.getElementById('shift-progress-text').textContent = 'Starting shift...';
      document.getElementById('shift-progress-count').textContent = `0/${numEvents}`;
      document.getElementById('shift-progress-bar').style.width = '0%';
      document.getElementById('shift-schedule').innerHTML = '';
      addLocalLog('SHIFT', `Shift simulation started for ${driverId} (${numEvents} events)`);
    } else {
      addLocalLog('ERROR', data.error || 'Failed to start shift');
    }
  } catch (e) {
    addLocalLog('ERROR', `Shift start failed: ${e.message}`);
  }
}

async function stopShift() {
  const driverId = document.getElementById('driver-select').value;
  try {
    await fetch(`/api/triggers/stop-shift/${driverId}`, { method: 'POST' });
    addLocalLog('SHIFT', 'Stopping shift simulation...');
  } catch (e) {
    addLocalLog('ERROR', `Stop shift failed: ${e.message}`);
  }
}

function handleShiftMessage(data) {
  const progress = document.getElementById('shift-progress');
  const progressText = document.getElementById('shift-progress-text');
  const progressCount = document.getElementById('shift-progress-count');
  const progressBar = document.getElementById('shift-progress-bar');
  const schedule = document.getElementById('shift-schedule');

  if (data.type === 'shift_started') {
    progress.style.display = 'block';
    progressText.textContent = 'Shift started — waiting for first event...';
    progressCount.textContent = `0/${data.total_events}`;
    progressBar.style.width = '0%';

    // Show schedule
    if (data.schedule) {
      schedule.innerHTML = data.schedule.map((s, i) =>
        `<div id="shift-ev-${i+1}" class="shift-schedule-item" style="padding:0.25rem 0.5rem; border-left:3px solid var(--border); margin-bottom:0.25rem; color:var(--text-muted);">
          <strong>${s.hour}h</strong> — ${s.trigger} <span style="opacity:0.7;">${s.desc}</span>
        </div>`
      ).join('');
    }
    addLocalLog('SHIFT', `Shift started: ${data.total_events} events planned`);
  }

  else if (data.type === 'shift_event') {
    const pct = ((data.event_index - 1) / data.total_events * 100).toFixed(0);
    progressBar.style.width = `${pct}%`;
    progressText.textContent = `Event ${data.event_index}/${data.total_events}: ${data.trigger_type} @ ${data.hour}h`;
    progressCount.textContent = `${data.event_index}/${data.total_events}`;

    // Highlight current event in schedule
    const el = document.getElementById(`shift-ev-${data.event_index}`);
    if (el) {
      el.style.borderLeftColor = 'var(--primary)';
      el.style.color = 'var(--text)';
      el.style.fontWeight = '500';
    }
    // Mark previous as done
    if (data.event_index > 1) {
      const prev = document.getElementById(`shift-ev-${data.event_index - 1}`);
      if (prev) {
        prev.style.borderLeftColor = 'var(--success)';
        prev.style.opacity = '0.6';
        prev.style.fontWeight = 'normal';
      }
    }
    addLocalLog('SHIFT', `Event ${data.event_index}/${data.total_events}: ${data.desc}`);
  }

  else if (data.type === 'shift_ended') {
    progressBar.style.width = '100%';
    progressBar.style.background = 'var(--success)';
    progressText.textContent = data.events_completed === data.total_events
      ? `Shift complete! ${data.events_completed} events in ${Math.round(data.duration_s)}s`
      : `Shift stopped. ${data.events_completed}/${data.total_events} events completed`;
    progressCount.textContent = `${data.events_completed}/${data.total_events}`;

    // Mark last event as done
    const lastEl = document.getElementById(`shift-ev-${data.events_completed}`);
    if (lastEl) {
      lastEl.style.borderLeftColor = 'var(--success)';
      lastEl.style.opacity = '0.6';
      lastEl.style.fontWeight = 'normal';
    }

    shiftRunning = false;
    document.getElementById('btn-start-shift').style.display = 'inline-flex';
    document.getElementById('btn-stop-shift').style.display = 'none';
    addLocalLog('SHIFT', `Shift ended: ${data.events_completed}/${data.total_events} events, ${Math.round(data.duration_s)}s`);

    // Reset bar color after a moment
    setTimeout(() => { progressBar.style.background = 'var(--primary)'; }, 3000);
  }
}

// --- Persona loading ---

let personasData = null;

async function loadPersonas() {
  try {
    const res = await fetch('/api/personas');
    personasData = await res.json();

    // Populate preset dropdown
    const presetSel = document.getElementById('persona-preset');
    for (const p of personasData.preset_combinations || []) {
      const opt = document.createElement('option');
      opt.value = JSON.stringify(p);
      opt.textContent = p.name;
      presetSel.appendChild(opt);
    }

    // Populate mood dropdown
    const moodSel = document.getElementById('persona-mood');
    for (const [key, val] of Object.entries(personasData.moods || {})) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = val.label;
      moodSel.appendChild(opt);
    }

    // Populate situation dropdown
    const sitSel = document.getElementById('persona-situation');
    for (const [key, val] of Object.entries(personasData.situations || {})) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = val.label;
      sitSel.appendChild(opt);
    }

    // Populate resistance dropdown
    const resSel = document.getElementById('persona-resistance');
    for (const [key, val] of Object.entries(personasData.resistance_levels || {})) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = val.label;
      resSel.appendChild(opt);
    }
  } catch (e) {
    console.error('Failed to load personas:', e);
  }
}

function applyPreset() {
  const sel = document.getElementById('persona-preset');
  if (sel.value === 'random') {
    document.getElementById('persona-mood').value = '';
    document.getElementById('persona-situation').value = '';
    document.getElementById('persona-resistance').value = '';
    return;
  }
  const preset = JSON.parse(sel.value);
  document.getElementById('persona-mood').value = preset.mood || '';
  document.getElementById('persona-situation').value = preset.situation || '';
  document.getElementById('persona-resistance').value = preset.resistance || '';
}

function getPersonaPayload() {
  const mood = document.getElementById('persona-mood').value;
  const situation = document.getElementById('persona-situation').value;
  const resistance = document.getElementById('persona-resistance').value;
  const payload = {};
  if (mood) payload.persona_mood = mood;
  if (situation) payload.persona_situation = situation;
  if (resistance) payload.persona_resistance = resistance;
  return payload;
}

// --- Card display ---

function displayCard(data) {
  const feed = document.getElementById('cards-feed');
  if (!feed) return;

  // Clear placeholder
  const placeholder = feed.querySelector('.cards-placeholder');
  if (placeholder) placeholder.remove();

  const wrapper = document.createElement('div');
  wrapper.className = 'card-item';

  const typeLabels = {
    rest_stop: 'Rest Stop Recommendation',
    wellness_summary: 'Shift Wellness Summary',
    incident: 'Incident Report',
  };

  const label = typeLabels[data.card_type] || data.card_type;
  const time = new Date().toLocaleTimeString();

  wrapper.innerHTML = `
    <div class="card-item-header">
      <span class="card-item-label">${label}</span>
      <span class="card-item-time">${time}</span>
    </div>
    <img src="${data.image_url}" alt="${label}" class="card-image" onclick="window.open('${data.image_url}', '_blank')">
  `;

  feed.prepend(wrapper);
  addLocalLog('CARD', `${label} generated for ${data.driver_id}`);
}

// --- Card generation demo ---

async function generateCard(cardType) {
  const driverId = document.getElementById('driver-select').value;
  let scenario = '';

  if (cardType === 'rest_stop') {
    scenario = document.getElementById('card-rest-scenario').value;
  } else if (cardType === 'wellness') {
    scenario = document.getElementById('card-wellness-scenario').value;
  } else if (cardType === 'incident') {
    scenario = document.getElementById('card-incident-scenario').value;
  }

  // Show spinner placeholder in the cards feed
  const feed = document.getElementById('cards-feed');
  const placeholder = feed.querySelector('.cards-placeholder');
  if (placeholder) placeholder.remove();

  const typeLabels = {
    rest_stop: 'Rest Stop Recommendation',
    wellness_summary: 'Shift Wellness Summary',
    incident: 'Incident Report',
  };
  const label = typeLabels[cardType] || cardType;

  const spinner = document.createElement('div');
  spinner.className = 'card-item card-generating';
  spinner.innerHTML = `
    <div class="card-item-header">
      <span class="card-item-label">${label}</span>
      <span class="card-item-time">Generating...</span>
    </div>
    <div class="card-spinner-area">
      <div class="card-spinner"></div>
      <div class="card-spinner-text">${cardType === 'rest_stop' ? 'Generating scenic background with Imagen...' : 'Generating card...'}</div>
    </div>
  `;
  feed.prepend(spinner);
  addLocalLog('CARD', `Generating ${label}...`);

  try {
    const res = await fetch('/api/cards/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ driver_id: driverId, card_type: cardType, scenario }),
    });
    const data = await res.json();
    spinner.remove();
    if (data.image_url) {
      displayCard({
        card_type: cardType,
        driver_id: driverId,
        image_url: data.image_url,
      });
    } else {
      addLocalLog('ERROR', data.error || 'Failed to generate card');
    }
  } catch (e) {
    spinner.remove();
    addLocalLog('ERROR', `Card generation failed: ${e.message}`);
  }
}

// --- Init ---

connectDashboardWs();
setInterval(refreshStatus, 3000);
setInterval(pollTranscript, 2000);
refreshStatus();
loadPersonas();
