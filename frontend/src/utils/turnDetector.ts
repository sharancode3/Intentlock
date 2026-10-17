/** Microphone activity only. It never authenticates a speaker or reads a transcript. */
export class TurnDetector {
  heardSpeech = false;
  lastSpeechAt: number;
  private candidateAt: number | null = null;
  private noiseFloor = 0.002;

  readonly startedAt: number;

  constructor(startedAt: number) {
    this.startedAt = startedAt;
    this.lastSpeechAt = startedAt;
  }

  sample(rms: number, now: number): boolean {
    // Learn the quiet background, without adapting the floor upwards during speech.
    const threshold = Math.max(0.008, this.noiseFloor * 3);
    if (Number.isFinite(rms) && rms >= threshold) {
      this.candidateAt ??= now;
      if (now - this.candidateAt >= 120) {
        this.heardSpeech = true;
        this.lastSpeechAt = now;
        return true;
      }
    } else {
      this.candidateAt = null;
      if (Number.isFinite(rms)) this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05;
    }
    return false;
  }

  markSpeech(now: number) {
    this.heardSpeech = true;
    this.lastSpeechAt = now;
  }

  decision(now: number): 'listen' | 'submit' | 'idle' | 'limit' {
    if (!this.heardSpeech && now - this.startedAt >= 20_000) return 'idle';
    if (this.heardSpeech && now - this.lastSpeechAt >= 1_400) return 'submit';
    if (now - this.startedAt >= 55_000) return 'limit';
    return 'listen';
  }
}
