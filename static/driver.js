/**
 * DriverPhone — handles notification WS, mic capture via AudioWorklet,
 * PCM send/receive over call WS, and audio playback.
 *
 * Browser captures at 16kHz mono, sends 16-bit PCM.
 * Receives 24kHz 16-bit PCM from Gemini via server.
 */
class DriverPhone {
  constructor(driverId) {
    this.driverId = driverId;
    this.state = 'idle'; // idle | ringing | connected
    this.notifyWs = null;
    this.callWs = null;
    this.audioCtx = null;
    this.workletNode = null;
    this.micStream = null;
    this.callStartTime = null;
    this.timerInterval = null;
    this.pendingCall = null;

    // Audio playback queue
    this._playbackQueue = [];
    this._isPlaying = false;
    this._playbackCtx = null;

    this._connectNotifications();
  }

  // --- Notification WebSocket ---

  _connectNotifications() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/driver/notifications/${this.driverId}`;
    this.notifyWs = new WebSocket(url);

    this.notifyWs.onopen = () => {
      this._setConnectionStatus(true);
      this._setIdleStatus('Online — waiting for incoming call...');
    };

    this.notifyWs.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'incoming_call') {
        this.pendingCall = data;
        this._setState('ringing');
      }
    };

    this.notifyWs.onclose = () => {
      this._setConnectionStatus(false);
      setTimeout(() => this._connectNotifications(), 3000);
    };

    this.notifyWs.onerror = () => {
      this.notifyWs.close();
    };
  }

  // --- Call Actions ---

  async accept() {
    if (this.state !== 'ringing' && this.state !== 'idle') return;

    try {
      // Set up mic capture BEFORE connecting call WS
      await this._startMic();

      // Connect call WebSocket
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${location.host}/call/${this.driverId}`;
      this.callWs = new WebSocket(url);
      this.callWs.binaryType = 'arraybuffer';

      this.callWs.onopen = () => {
        this._setState('connected');
        this._startTimer();
        this._initPlayback();
      };

      this.callWs.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          // PCM audio from Betty
          this._queueAudio(event.data);
        } else {
          // JSON message
          const data = JSON.parse(event.data);
          if (data.type === 'transcript') {
            this._addTranscript(data.speaker || 'betty', data.text);
          } else if (data.type === 'call_connected') {
            console.log('Call connected:', data.call_id);
          } else if (data.type === 'interrupted') {
            // Barge-in: clear buffered audio so Betty stops immediately
            this._clearPlayback();
          }
        }
      };

      this.callWs.onclose = () => {
        this._endCall();
      };

      this.callWs.onerror = (e) => {
        console.error('Call WS error:', e);
        this._endCall();
      };

    } catch (err) {
      console.error('Failed to accept call:', err);
      alert('Could not access microphone. Please allow microphone access.');
      this._setState('idle');
    }
  }

  async callBetty() {
    if (this.state !== 'idle') return;

    this._setIdleStatus('Calling Betty...');
    try {
      const res = await fetch(`/api/call/driver-initiate/${this.driverId}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        this._setIdleStatus(data.error || 'Failed to call Betty');
        return;
      }
      // Call created — now connect via WebSocket (same as accepting an incoming call)
      this.pendingCall = { type: 'driver_initiated' };
      await this.accept();
    } catch (err) {
      console.error('Failed to call Betty:', err);
      this._setIdleStatus('Failed to call Betty. Try again.');
    }
  }

  decline() {
    this.pendingCall = null;
    this._setState('idle');
  }

  hangup() {
    if (this.callWs && this.callWs.readyState === WebSocket.OPEN) {
      this.callWs.send(JSON.stringify({ type: 'hangup' }));
      this.callWs.close();
    }
    this._endCall();
  }

  // --- Mic Capture ---

  async _startMic() {
    this.audioCtx = new AudioContext({ sampleRate: 16000 });
    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
    });

    await this.audioCtx.audioWorklet.addModule('/static/audio-processor.js');
    const source = this.audioCtx.createMediaStreamSource(this.micStream);
    this.workletNode = new AudioWorkletNode(this.audioCtx, 'pcm-processor');

    this.workletNode.port.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // PCM audio data — send to server
        if (this.callWs && this.callWs.readyState === WebSocket.OPEN) {
          this.callWs.send(event.data);
        }
      } else if (event.data && event.data.type === 'vad') {
        // Client-side VAD: mute Betty immediately when driver starts speaking
        if (event.data.speaking) {
          this._clearPlayback();
        }
      }
    };

    source.connect(this.workletNode);
    // Don't connect to destination — we don't want mic echo
  }

  _stopMic() {
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach(t => t.stop());
      this.micStream = null;
    }
    if (this.audioCtx) {
      this.audioCtx.close();
      this.audioCtx = null;
    }
  }

  // --- Audio Playback (queue-based to avoid clicks/gaps) ---

  _initPlayback() {
    this._playbackCtx = new AudioContext({ sampleRate: 24000 });
    this._playbackQueue = [];
    this._isPlaying = false;
    this._nextPlayTime = 0;
    this._activeSources = [];
  }

  _queueAudio(arrayBuffer) {
    if (!this._playbackCtx) return;

    // Convert Int16 PCM to Float32
    const int16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }

    // Create audio buffer
    const audioBuffer = this._playbackCtx.createBuffer(1, float32.length, 24000);
    audioBuffer.getChannelData(0).set(float32);

    // Schedule seamless playback
    const now = this._playbackCtx.currentTime;
    const startTime = Math.max(now, this._nextPlayTime);

    const source = this._playbackCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this._playbackCtx.destination);
    source.start(startTime);

    this._activeSources.push(source);
    source.onended = () => {
      const idx = this._activeSources.indexOf(source);
      if (idx !== -1) this._activeSources.splice(idx, 1);
    };

    this._nextPlayTime = startTime + audioBuffer.duration;

    // Update audio level indicator
    const rms = Math.sqrt(float32.reduce((sum, s) => sum + s * s, 0) / float32.length);
    const level = Math.min(100, rms * 500);
    const bar = document.getElementById('audio-level-bar');
    if (bar) bar.style.width = level + '%';
  }

  _clearPlayback() {
    // Stop all actively playing/scheduled sources immediately
    if (this._activeSources) {
      for (const src of this._activeSources) {
        try { src.stop(); } catch (e) {}
      }
      this._activeSources = [];
    }
    if (this._playbackCtx) {
      this._nextPlayTime = 0;
    }
  }

  _stopPlayback() {
    if (this._activeSources) {
      for (const src of this._activeSources) {
        try { src.stop(); } catch (e) {}
      }
      this._activeSources = [];
    }
    if (this._playbackCtx) {
      this._playbackCtx.close();
      this._playbackCtx = null;
    }
    this._playbackQueue = [];
    this._isPlaying = false;
  }

  // --- UI State ---

  _setState(state) {
    this.state = state;
    document.body.className = `state-${state}`;

    const avatar = document.getElementById('avatar');
    avatar.className = 'avatar';
    if (state === 'ringing') avatar.classList.add('ringing');
    if (state === 'connected') avatar.classList.add('connected');

    const timer = document.getElementById('call-timer');
    if (state === 'connected') {
      timer.classList.add('active');
    } else {
      timer.classList.remove('active');
    }
  }

  _setConnectionStatus(online) {
    const el = document.getElementById('conn-status');
    el.className = `connection-status ${online ? 'online' : 'offline'}`;
    el.textContent = online ? 'Online' : 'Reconnecting...';
  }

  _setIdleStatus(text) {
    const el = document.getElementById('idle-status');
    if (el) el.textContent = text;
  }

  _startTimer() {
    this.callStartTime = Date.now();
    this.timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - this.callStartTime) / 1000);
      const min = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const sec = String(elapsed % 60).padStart(2, '0');
      document.getElementById('call-timer').textContent = `${min}:${sec}`;
    }, 1000);
  }

  _stopTimer() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
  }

  _addTranscript(speaker, text) {
    const area = document.getElementById('transcript-area');
    if (!area) return;
    const line = document.createElement('div');
    line.className = 'transcript-line';
    line.innerHTML = `<span class="transcript-speaker">${speaker}:</span> ${text}`;
    area.appendChild(line);
    area.scrollTop = area.scrollHeight;
  }

  _endCall() {
    this._stopMic();
    this._stopPlayback();
    this._stopTimer();
    this._setState('idle');
    this._setIdleStatus('Call ended. Waiting for next call...');
    this.callWs = null;
    this.pendingCall = null;
    document.getElementById('call-timer').textContent = '00:00';
  }
}
