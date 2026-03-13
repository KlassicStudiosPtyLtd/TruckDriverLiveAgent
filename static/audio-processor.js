/**
 * AudioWorklet processor: captures raw Float32 PCM from mic, posts to main thread.
 *
 * Registered as 'pcm-processor'. Runs in AudioWorklet context (separate thread).
 * Buffers 100ms chunks (1600 samples at 16kHz) before posting.
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(1600); // 100ms at 16kHz
    this._offset = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // Float32 mono channel

    for (let i = 0; i < samples.length; i++) {
      this._buffer[this._offset++] = samples[i];

      if (this._offset >= this._buffer.length) {
        // Convert Float32 [-1,1] to Int16 PCM
        const pcm = new Int16Array(this._buffer.length);
        for (let j = 0; j < this._buffer.length; j++) {
          const s = Math.max(-1, Math.min(1, this._buffer[j]));
          pcm[j] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this._buffer = new Float32Array(1600);
        this._offset = 0;
      }
    }

    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
