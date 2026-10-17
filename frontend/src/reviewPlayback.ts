export class ReviewPlayback {
  private source = "";
  private units: string[] = [];
  private offsets: number[] = [0];
  private shown = 0;
  private position = 0;
  private deadline = 0;
  private lastFrame = 0;
  private lastArrival = 0;
  private cadence = 160;
  private readonly segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });

  constructor(text = "", retained = false) {
    this.source = retained ? text : "";
    this.units = this.segment(this.source);
    this.indexOffsets();
    if (retained) this.shown = this.position = this.units.length;
  }

  get pending() { return this.shown < this.units.length; }
  get text() { return this.source.slice(0, this.offsets[this.shown]); }

  update(text: string, now: number) {
    if (text === this.source) return;
    const extending = text.startsWith(this.source);
    const stable = extending ? Math.max(0, this.units.length - 1) : 0;
    // Re-segment the last cluster too: an arriving combining mark or ZWJ can extend it.
    const next = extending
      ? this.units.slice(0, stable).concat(this.segment(text.slice(this.offsets[stable])))
      : this.segment(text);
    const gap = now - this.lastArrival;
    if (this.lastArrival && gap >= 120) this.cadence = Math.min(3500, Math.max(160, gap * 1.03));
    this.lastArrival = now;
    let shared = Math.min(stable, this.shown);
    while (shared < this.shown && shared < next.length && this.units[shared] === next[shared]) shared++;
    if (shared < this.shown) {
      // Final validation may adjust whitespace or image placement without replaying the body.
      const meaningful = (unit: string) => !/^[\s\uFFFC]+$/u.test(unit);
      const before = this.units.slice(0, this.shown).filter(meaningful), after = next.filter(meaningful);
      let rebased = Math.min(this.shown, next.length);
      if (before.length && before.every((unit, index) => unit === after[index])) {
        let visible = 0;
        rebased = 0;
        while (rebased < next.length && visible < before.length) if (meaningful(next[rebased++])) visible++;
      }
      this.shown = this.position = rebased;
    }
    this.source = text;
    this.units = next;
    this.indexOffsets(stable);
    const backlogWindow = Math.min(3500, Math.max(160, (next.length - this.shown) / 8));
    this.deadline = now + Math.max(this.cadence, backlogWindow);
    this.lastFrame = now;
  }

  frame(now: number) {
    if (!this.pending) return this.text;
    const fraction = Math.min(1, Math.max(0, now - this.lastFrame) / Math.max(1, this.deadline - this.lastFrame));
    this.position += (this.units.length - this.position) * fraction;
    this.lastFrame = now;
    this.shown = Math.min(this.units.length, Math.floor(this.position + 1e-6));
    return this.text;
  }

  private segment(text: string) { return Array.from(this.segmenter.segment(text), part => part.segment); }

  private indexOffsets(start = 0) {
    this.offsets.length = start + 1;
    for (let index = start; index < this.units.length; index++) {
      this.offsets.push(this.offsets[index] + this.units[index].length);
    }
  }
}
