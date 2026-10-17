import assert from 'node:assert/strict';
import { mock } from 'node:test';
import { JSDOM } from 'jsdom';
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { useLiveAudioRecorder } from '../hooks/useLiveAudioRecorder';
import { TurnDetector } from '../utils/turnDetector';

const dom = new JSDOM('<div id="root"></div>', { url: 'https://intentlock.example' });
for (const [name, value] of Object.entries({ window: dom.window, document: dom.window.document,
  navigator: { mediaDevices: { getUserMedia: async () => media } }, IS_REACT_ACT_ENVIRONMENT: true })) {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}
let rms = 0;
let tracksStopped = 0;
let contextsClosed = 0;
const track = { onended: null, stop: () => { tracksStopped++; } };
const media = { getTracks: () => [track], getAudioTracks: () => [track] };
class Recorder {
  static instances: Recorder[] = [];
  static isTypeSupported() { return true; }
  state = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable?: (e: { data: Blob }) => void;
  onstop?: () => void;
  constructor() { Recorder.instances.push(this); }
  start() { this.state = 'recording'; }
  stop() {
    assert.equal(this.state, 'recording');
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['original-container-audio']) });
    this.onstop?.();
  }
}
class Context {
  destination = {};
  audioWorklet = { addModule: async () => {} };
  createMediaStreamSource() { return { connect() {} }; }
  createAnalyser() { return { fftSize: 2048, getFloatTimeDomainData: (data: Float32Array) => data.fill(rms) }; }
  async resume() {}
  async close() { contextsClosed++; }
}
class Worklet {
  port = { onmessage: null, close() {} };
  connect() {}
  disconnect() {}
}
class Socket {
  static OPEN = 1;
  static CONNECTING = 0;
  static instances: Socket[] = [];
  readyState = 1;
  bufferedAmount = 0;
  onmessage?: (e: { data: string }) => void;
  onclose?: () => void;
  onerror?: () => void;
  closed = false;
  constructor() { Socket.instances.push(this); }
  addEventListener() {}
  send() {}
  close() { this.closed = true; this.readyState = 3; this.onclose?.(); }
}
Object.assign(globalThis, { MediaRecorder: Recorder, AudioContext: Context, AudioWorkletNode: Worklet, WebSocket: Socket });
mock.timers.enable({ apis: ['Date', 'setInterval', 'setTimeout'], now: 100_000 });
const submissions: { blob: Blob; id?: string }[] = [];
const partials: string[] = [];
let release: (() => void) | undefined;
let disabled = false;
let hook!: ReturnType<typeof useLiveAudioRecorder>;
function Harness() {
  hook = useLiveAudioRecorder({ disabled, onLiveTranscript: event => partials.push(event.text),
    onAudioCaptured: async (blob, _duration, id) => {
      submissions.push({ blob, id });
      await new Promise<void>(resolve => { release = resolve; });
    } });
  return null;
}
const root = createRoot(document.getElementById('root')!);
async function tick(ms: number) {
  for (let elapsed = 0; elapsed < ms; elapsed += 50) {
    await act(async () => { mock.timers.tick(Math.min(50, ms - elapsed)); });
  }
}
async function render() { await act(async () => { root.render(createElement(Harness)); }); }

try {
  const detector = new TurnDetector(0);
  detector.sample(0.2, 100); detector.sample(0, 150);
  assert.equal(detector.heardSpeech, false, 'a single click must not become speech');
  assert.equal(detector.decision(20_000), 'idle');
  await render();
  await act(async () => { await hook.startRecording(); });
  const first = Recorder.instances.at(-1)!;
  const socket = Socket.instances.at(-1)!;
  await act(async () => { socket.onmessage?.({ data: JSON.stringify({ type: 'ready' }) }); });
  await act(async () => { socket.onmessage?.({ data: JSON.stringify({ type: 'transcript.partial', text: 'My employee ID is EMP-4002' }) }); });
  assert.ok(partials.includes('My employee ID is EMP-4002'), 'partial text must arrive during recording');
  assert.equal(submissions.length, 0);
  await act(async () => { socket.onerror?.(); socket.close(); });
  rms = 0.015; await tick(400);  // Quiet speech, below the broken 0.04 threshold.
  rms = 0; await tick(1450);
  assert.equal(submissions.length, 1, 'pause sends despite preview outage');
  assert.equal(await submissions[0].blob.text(), 'original-container-audio');
  assert.equal(hook.isArmed, true);
  await act(async () => { first.onstop?.(); });
  assert.equal(submissions.length, 1, 'duplicate stop event cannot resubmit');
  disabled = true; await render();
  await tick(1000);
  assert.equal(Recorder.instances.length, 1, 'never record during processing/playback');
  await act(async () => { release?.(); });
  disabled = false; await render();
  await tick(400);
  assert.equal(Recorder.instances.length, 2, 'conversation resumes after the response');
  rms = 0; await tick(20_000);
  assert.equal(submissions.length, 1, 'idle silence is discarded without any API submission');
  assert.equal(hook.isArmed, false);
  await act(async () => { await hook.startRecording(); });
  rms = 0.015; await tick(400);
  await act(async () => { hook.cancelRecording(); });
  assert.equal(submissions.length, 1, 'cancel discards even a speech-containing recording');
  assert.equal(hook.isArmed, false);
  assert.ok(tracksStopped >= 3 && contextsClosed >= 3, 'every completed turn releases its microphone and context');
  console.log('Recorder regression passed: real hook, live partials, quiet speech, offline VAD, one submission, continuous restart, idle, cancel, cleanup.');
} finally {
  await act(async () => { root.unmount(); });
  mock.timers.reset();
  dom.window.close();
}
