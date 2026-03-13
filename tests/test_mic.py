"""Quick mic check: records 3 seconds from your mic, plays it back.

Usage:
    python tests/test_mic.py
"""

import pyaudio
import time

RATE = 16000
CHANNELS = 1
CHUNK = 1600  # 100ms
FORMAT = pyaudio.paInt16
RECORD_SECONDS = 3

pa = pyaudio.PyAudio()

# Show available devices
print("Audio devices:")
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    tag = ""
    if i == pa.get_default_input_device_info()["index"]:
        tag += " [DEFAULT INPUT]"
    if i == pa.get_default_output_device_info()["index"]:
        tag += " [DEFAULT OUTPUT]"
    print(f"  {i}: {info['name']} (in={info['maxInputChannels']}, out={info['maxOutputChannels']}){tag}")

print(f"\nRecording {RECORD_SECONDS}s from default mic at {RATE}Hz...")
mic = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

frames = []
for _ in range(int(RATE / CHUNK * RECORD_SECONDS)):
    data = mic.read(CHUNK, exception_on_overflow=False)
    frames.append(data)

mic.stop_stream()
mic.close()

audio = b"".join(frames)
print(f"Recorded {len(audio)} bytes ({len(audio)/2/RATE:.1f}s)")

# Check if it's silence
samples = [int.from_bytes(audio[i:i+2], "little", signed=True) for i in range(0, min(len(audio), 6400), 2)]
peak = max(abs(s) for s in samples)
print(f"Peak amplitude: {peak} (silence < 100, speech > 1000)")

print("\nPlaying back...")
spk = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
spk.write(audio)
spk.stop_stream()
spk.close()

pa.terminate()
print("Done. If you heard your recording, mic and speakers are working.")
