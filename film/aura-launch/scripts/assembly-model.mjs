// Kept in step with website/components/assembly-model.ts, A03 geometry revision.
export function partForName(name) {
  if (/battery/i.test(name)) return 'battery';
  if (/rear|back|pogo|charging|case_screw/i.test(name)) return 'back';
  if (/button|led|acoustic|plunger|privacy|switch|face|paddle|lens/i.test(name)) return 'controls';
  if (/front|frame|bail|eyelet|cord|chain|wordmark/i.test(name)) return 'shell';
  return 'board';
}
export const travel = { shell: .37, controls: .49, board: 0, battery: -.19, back: -.39 };
const clamp = x => Math.max(0, Math.min(1, x));
const ease = x => { const p=clamp(x); return p<.5 ? 4*p*p*p : 1-(-2*p+2)**3/2; };
export function assemblyPose(time) {
  const t=time-21;
  const open=ease((t-.7)/2.05);
  const close=ease((t-5.15)/1.95);
  const progress=open*(1-close);
  const orbit=ease((t-.35)/6.65);
  return { progress, yaw: -.28-.69*progress+.13*orbit, pitch: -.07-.04*progress,
    roll: -.055+.085*progress, distance: 4.25+1.35*progress };
}
