import { useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Eye,
  Layers3,
  Pause,
  Play,
  RotateCcw,
} from 'lucide-react';
import { Slider } from '@/components/ui/slider';
import DeviceViewer from './device-viewer';
import { parts, type Part, type ViewPreset } from './assembly-model';

export default function AssemblyExplorer({
  finish = '#d6d5cf',
}: {
  finish?: string;
}) {
  const [progress, setProgress] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Part | null>(null);
  const [xray, setXray] = useState(false);
  const [preset, setPreset] = useState<ViewPreset>('perspective');
  const [reset, setReset] = useState(0);
  const host = useRef<HTMLDivElement>(null);
  const playhead = useRef(0);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = 0;
    let elapsed = playhead.current;
    let visible = true;
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    if (host.current) observer.observe(host.current);
    const tick = (time: number) => {
      frame = requestAnimationFrame(tick);
      if (!last) last = time;
      const delta = Math.min((time - last) / 1000, 0.06);
      last = time;
      if (!visible || document.hidden) return;
      elapsed += delta;
      playhead.current = elapsed;
      // Four seconds apart, one second to examine, four seconds together.
      setProgress(
        elapsed < 4
          ? elapsed / 4
          : elapsed < 5
            ? 1
            : Math.max(0, 1 - (elapsed - 5) / 4),
      );
      if (elapsed >= 9) {
        playhead.current = 0;
        setPlaying(false);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [playing]);

  function selectPart(id: Part | null) {
    setSelected(id);
    setPlaying(false);
    if (id) {
      setProgress(1);
      playhead.current = 4;
      setPreset('perspective');
    }
  }
  const part = parts.find((item) => item.id === selected);

  return (
    <div className="assembly-explorer reveal" ref={host}>
      <div className="assembly-viewport">
        <DeviceViewer
          mode="explore"
          finish={finish}
          assembly={progress}
          activePart={selected}
          xray={xray}
          preset={preset}
          resetKey={reset}
          onPartPick={selectPart}
        />
        <div className="view-presets" aria-label="Camera view">
          {(['perspective', 'front', 'profile'] as const).map((view) => (
            <button
              key={view}
              aria-pressed={preset === view}
              onClick={() => {
                setPreset(view);
                setReset(reset + 1);
              }}
            >
              {view === 'perspective'
                ? 'Three-quarter'
                : view === 'front'
                  ? 'Front'
                  : 'Side'}
            </button>
          ))}
        </div>
      </div>
      <div className="assembly-controls">
        <div className="assembly-transport">
          <button
            className="round-control"
            aria-label={
              playing ? 'Pause assembly animation' : 'Play assembly animation'
            }
            onClick={() => {
              setSelected(null);
              setPlaying(!playing);
            }}
          >
            {playing ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <div className="assembly-scrub">
            <span className="sr-only" id="assembly-progress-label">
              Separate the product layers
            </span>
            <div>
              <span>Assembled</span>
              <span>Inside out</span>
            </div>
            <Slider
              aria-labelledby="assembly-progress-label"
              min={0}
              max={100}
              step={1}
              value={[Math.round(progress * 100)]}
              onValueChange={(value) => {
                const p = (Array.isArray(value) ? value[0] : value) / 100;
                setPlaying(false);
                setProgress(p);
                playhead.current = p * 4;
              }}
            />
          </div>
          <button
            className={`round-control ${xray ? 'active' : ''}`}
            aria-label="See through the outer shell"
            aria-pressed={xray}
            onClick={() => setXray(!xray)}
          >
            <Eye size={18} />
          </button>
          <button
            className="round-control"
            aria-label="Reset assembly explorer"
            onClick={() => {
              setPlaying(false);
              setProgress(0);
              playhead.current = 0;
              setSelected(null);
              setXray(false);
              setPreset('perspective');
              setReset(reset + 1);
            }}
          >
            <RotateCcw size={17} />
          </button>
        </div>
        <div className="part-selector" aria-label="Explore a product layer">
          <button aria-pressed={!selected} onClick={() => selectPart(null)}>
            <Layers3 size={15} /> All
          </button>
          {parts.map((item) => (
            <button
              key={item.id}
              aria-pressed={selected === item.id}
              onClick={() => selectPart(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="part-story" aria-live="polite">
          {part ? (
            <>
              <h3>{part.title}</h3>
              <div>
                <p>{part.description}</p>
                <span>
                  {part.detail} <ArrowUpRight size={14} />
                </span>
              </div>
            </>
          ) : (
            <p className="assembly-instruction">
              Slide to open. Select a part to discover.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
