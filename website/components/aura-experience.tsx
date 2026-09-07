import { useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  Check,
  Download,
  Mic,
  Play,
  RotateCcw,
  Rotate3D,
  Sparkles,
  Square,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import DeviceViewer from './device-viewer';
import AssemblyExplorer from './assembly-explorer';

const finishes = [
  { name: 'Lunar', color: '#d6d5cf', description: 'A quiet, satin silver.' },
  {
    name: 'Graphite',
    color: '#45474a',
    description: 'A deeper shade of understated.',
  },
  {
    name: 'Dune',
    color: '#c6ac91',
    description: 'A little warmth, everywhere.',
  },
];
const bars = Array.from(
  { length: 65 },
  (_, i) => 8 + ((i * 13 + i * i * 7) % 30),
);

function NoteDemo() {
  const [step, setStep] = useState(0);
  const label = [
    'Try a thought',
    'Finish recording',
    'See the AI note',
    'Try it again',
  ][step];
  return (
    <div className="note-panel">
      <div>
        <div className="sample-label">
          AURA NOTES <span>INTERACTIVE DEMO</span>
        </div>
        <h3>
          {step < 3 ? 'An idea, on the way home.' : 'A little more green.'}
        </h3>
        <p className="note-meta">
          Personal thought <span aria-hidden="true">·</span> 18 seconds
        </p>
        <div
          className={`waveform ${step === 1 ? 'recording' : ''}`}
          aria-hidden="true"
        >
          {bars.map((h, i) => (
            <span
              key={i}
              style={{ height: h, animationDelay: `${i * 0.034}s` }}
            />
          ))}
        </div>
        <div className="demo-content" aria-live="polite">
          {step === 0 && (
            <p>
              That good idea doesn’t need to wait until you find your phone.{' '}
              <strong>Give it a moment.</strong>
            </p>
          )}
          {step === 1 && (
            <p>
              “What if we turned the unused corner by the window into a little
              herb garden? I should ask Maya about it on Friday.”
            </p>
          )}
          {step === 2 && (
            <>
              <strong>Thought saved.</strong>
              <p>Your recording becomes a transcript and a starting point.</p>
            </>
          )}
          {step === 3 && (
            <>
              <strong>Start a windowsill herb garden.</strong>
              <ul>
                <li>Use the empty corner by the window.</li>
                <li>Ask Maya about the idea on Friday.</li>
              </ul>
            </>
          )}
        </div>
      </div>
      <div className="note-foot">
        <button className="demo-button" onClick={() => setStep((step + 1) % 4)}>
          {step === 1 ? (
            <Square />
          ) : step === 2 ? (
            <Sparkles />
          ) : step === 3 ? (
            <RotateCcw />
          ) : (
            <Mic />
          )}
          {label}
        </button>
        <span>Sample · no audio recorded</span>
      </div>
    </div>
  );
}

export default function AuraExperience() {
  const [filmOpen, setFilmOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [finish, setFinish] = useState(() => {
    try {
      return Math.max(
        0,
        finishes.findIndex(
          (f) => f.name === localStorage.getItem('aura-finish'),
        ),
      );
    } catch {
      return 0;
    }
  });
  const [saved, setSaved] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = mainRef.current;
    if (!root || !('IntersectionObserver' in window)) return;
    root.classList.add('motion-ready');
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 },
    );
    root.querySelectorAll('.reveal').forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  function chooseFinish(index: number) {
    setFinish(index);
    setSaved(false);
    try {
      localStorage.setItem('aura-finish', finishes[index].name);
    } catch {
      /* Keep the in-memory choice. */
    }
  }
  function saveConfiguration() {
    const config = {
      product: 'AURA',
      finish: finishes[finish].name,
      status: 'Development concept — not an order',
      revision: 'A03',
      bodyMM: { height: 48, width: 28, depth: 10 },
      project: 'https://github.com/Avinash1286/pendent',
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `aura-${finishes[finish].name.toLowerCase()}-configuration.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setSaved(true);
  }

  return (
    <>
      <a href="#design" className="skip">
        Skip to interactive product
      </a>
      <header id="top" className="nav">
        <a href="#top" className="wordmark" aria-label="AURA home">
          AURA
        </a>
        <nav className="nav-links" aria-label="Main navigation">
          <a href="#design">Explore</a>
          <a href="#experience">The experience</a>
          <a href="#configure" className="nav-cta">
            Make it yours <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </header>
      <main ref={mainRef}>
        <section className="hero minimal-hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">WEARABLE AI NOTES</p>
            <h1 id="hero-title">
              Capture the
              <br />
              <span className="soft">context of</span>
              <br />
              <span className="soft">your life.</span>
            </h1>
            <p className="hero-description">
              For the moments you choose to keep.
            </p>
            <div className="hero-actions">
              <a className="pill light" href="#design">
                Explore inside <ArrowDown size={15} />
              </a>
              <button className="text-button" onClick={() => setFilmOpen(true)}>
                Watch the film <Play size={15} />
              </button>
            </div>
          </div>
          <div className="hero-stage">
            <DeviceViewer mode="hero" finish={finishes[finish].color} />
          </div>
          <div
            id="configure"
            className="finish-dock"
            aria-label="Choose your AURA finish"
          >
            <div className="finishes">
              {finishes.map((f, i) => (
                <button
                  key={f.name}
                  className="finish"
                  style={{ background: f.color }}
                  aria-label={`${f.name} finish`}
                  aria-pressed={finish === i}
                  onClick={() => chooseFinish(i)}
                />
              ))}
            </div>
            <span className="finish-name" aria-live="polite">
              {finishes[finish].name}
            </span>
            <button
              className="save-finish"
              onClick={() => setConfigOpen(true)}
              aria-label="Save your selected finish"
            >
              <Download size={17} />
            </button>
          </div>
          <span className="hero-drag-hint">
            <Rotate3D size={15} />
            Drag to turn
          </span>
        </section>

        <section
          id="design"
          className="section design-section minimal-design"
          aria-labelledby="design-title"
        >
          <h2 id="design-title" className="reveal">
            Inside, out.
          </h2>
          <AssemblyExplorer finish={finishes[finish].color} />
        </section>

        <section
          id="experience"
          className="section light-section minimal-notes"
          aria-labelledby="notes-title"
        >
          <div className="notes-intro reveal">
            <h2 id="notes-title">
              From a thought
              <br />
              to a possibility.
            </h2>
            <p>
              Turn a thought into a note. Bring your context to the AI you
              choose.
            </p>
          </div>
          <div className="reveal">
            <NoteDemo />
          </div>
        </section>
      </main>
      <footer className="footer minimal-footer">
        <p>AURA · Development concept. Not available for purchase.</p>
        <a
          href="https://github.com/Avinash1286/pendent"
          target="_blank"
          rel="noreferrer"
        >
          Project & downloads ↗
        </a>
      </footer>

      <Dialog open={filmOpen} onOpenChange={setFilmOpen}>
        <DialogContent className="film-dialog">
          <DialogTitle>AURA — Capture the context of your life.</DialogTitle>
          <DialogDescription className="sr-only">
            A 36-second product concept film with original music and English
            title captions.
          </DialogDescription>
          {filmOpen && (
            <video
              src="/film/aura-launch.mp4"
              poster="/film/poster.jpg"
              controls
              autoPlay
              playsInline
              preload="metadata"
            >
              <track
                kind="captions"
                src="/film/captions.vtt"
                srcLang="en"
                label="English titles"
                default
              />
              Your browser does not support video.{' '}
              <a href="/film/aura-launch.mp4">Download the film.</a>
            </video>
          )}
          <a className="text-button" href="/film/aura-launch.mp4" download>
            <Download size={15} />
            Download the film
          </a>
        </DialogContent>
      </Dialog>
      <Dialog open={configOpen} onOpenChange={setConfigOpen}>
        <DialogContent className="config-dialog">
          <DialogTitle>Your AURA.</DialogTitle>
          <DialogDescription>
            Save your chosen finish as a configuration file.
          </DialogDescription>
          <div className="config-summary">
            <span>AURA / {finishes[finish].name}</span>
          </div>
          <button className="pill light" onClick={saveConfiguration}>
            {saved ? <Check size={16} /> : <Download size={16} />}
            {saved ? 'Download again' : 'Save configuration'}
          </button>
          <p className="small-note" aria-live="polite">
            {saved
              ? 'Saved to your downloads.'
              : 'A design preference, not an order.'}
          </p>
        </DialogContent>
      </Dialog>
    </>
  );
}
