export type Part = 'shell' | 'controls' | 'board' | 'battery' | 'back';
export type ViewPreset = 'perspective' | 'front' | 'profile';

export const parts: {
  id: Part;
  label: string;
  title: string;
  description: string;
  detail: string;
}[] = [
  {
    id: 'shell',
    label: 'The surface',
    title: 'Quiet on the outside.',
    description:
      'Soft radii, a fine seam and a satin finish. A radio-transparent polymer shell keeps the Bluetooth antenna clear.',
    detail: '48 × 28 × 10 mm body target',
  },
  {
    id: 'controls',
    label: 'The gesture',
    title: 'One press. A place for a thought.',
    description:
      'The black front is a short-travel recording paddle, with a discreet light and two microphone openings. The side switch physically disconnects microphone power.',
    detail: 'Tactile control · visible feedback',
  },
  {
    id: 'board',
    label: 'The intelligence',
    title: 'Every millimetre has a purpose.',
    description:
      'A compact four-layer board brings together Bluetooth, digital speech capture, local flash and haptic feedback. Your phone handles the AI.',
    detail: '24 × 42 mm circuit board',
  },
  {
    id: 'battery',
    label: 'The energy',
    title: 'Room for the everyday.',
    description:
      'A thin rechargeable cell sits behind the board. The design includes charge management and battery monitoring; runtime awaits prototype testing.',
    detail: '3 mm cell envelope · rechargeable',
  },
  {
    id: 'back',
    label: 'The last detail',
    title: 'A considered finish, all around.',
    description:
      'A removable rear shell gives access for assembly. Three recessed contacts provide a connection to the proposed charging dock.',
    detail: 'Serviceable shell · recessed contacts',
  },
];

export function partForName(name: string): Part {
  if (/battery/i.test(name)) return 'battery';
  if (/rear|back|pogo|charging|case_screw/i.test(name)) return 'back';
  if (/button|led|acoustic|plunger|privacy|switch|face|paddle|lens/i.test(name))
    return 'controls';
  if (/front|frame|bail|eyelet|cord|chain|wordmark/i.test(name)) return 'shell';
  return 'board';
}

export function assemblyCameraDistance(
  aspect: number,
  progress: number,
): number {
  return aspect < 0.85 ? 4.6 + progress * 4.2 : 4.2 + progress * 1.8;
}

export function separation(part: Part, progress: number, size: number): number {
  const p = Math.max(0, Math.min(1, progress));
  const distances: Record<Part, number> = {
    shell: 0.37,
    controls: 0.49,
    board: 0,
    battery: -0.19,
    back: -0.39,
  };
  return distances[part] * size * p;
}
