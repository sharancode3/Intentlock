// Preview only: the original MediaRecorder audio is kept separately for verification.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = [];
    this.position = 0;
    this.frame = [];
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (const value of channel) this.pending.push(value);
    const ratio = sampleRate / 16000;
    while (this.position + ratio < this.pending.length) {
      const start = Math.floor(this.position);
      const end = Math.max(start + 1, Math.floor(this.position + ratio));
      let sum = 0;
      for (let i = start; i < end; i++) sum += this.pending[i];
      const value = Math.max(-1, Math.min(1, sum / (end - start)));
      this.frame.push(value < 0 ? value * 32768 : value * 32767);
      this.position += ratio;
      if (this.frame.length === 1024) {
        const pcm = new Int16Array(this.frame);
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.frame = [];
      }
    }
    const consumed = Math.floor(this.position);
    this.pending.splice(0, consumed);
    this.position -= consumed;
    return true;
  }
}
registerProcessor('pcm-capture', PcmCapture);
