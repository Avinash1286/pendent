import { useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowRight,
  AudioLines,
  Battery,
  Bluetooth,
  Check,
  Download,
  Fingerprint,
  Layers3,
  Mic,
  Play,
  RotateCcw,
  Rotate3D,
  ShieldCheck,
  Sparkles,
  Square,
  WifiOff,
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
              <p>
                The intended flow transfers your recording to your phone, then
                turns it into a clear, useful note.
              </p>
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
        <span>
          Sample content.
          <br />
          Your microphone stays off.
        </span>
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
  const [exploded, setExploded] = useState(false);
  const [view, setView] = useState(0);
  const [saved, setSaved] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = mainRef.current;
    if (!root || !('IntersectionObserver' in window)) return;
    root.classList.add('motion-ready');
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        }),
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
      /* preference remains in memory */
    }
  }
  function saveConfiguration() {
    const config = {
      product: 'AURA',
      finish: finishes[finish].name,
      targetPriceUSD: 179,
      status: 'Development concept — not an order',
      revision: 'A02',
      bodyMM: { height: 40, width: 30, depth: 9.5 },
      intendedBundle: [
        'AURA pendant',
        'Adjustable breakaway cord',
        'Magnetic charging dock',
      ],
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
      <a href="#experience" className="skip">
        Skip to product experience
      </a>
      <header id="top" className="nav">
        <a href="#top" className="wordmark" aria-label="AURA home">
          AURA
        </a>
        <nav className="nav-links" aria-label="Main navigation">
          <a href="#experience">The experience</a>
          <a href="#design">The design</a>
          <a href="#film">The film</a>
          <a href="#configure" className="nav-cta">
            Explore AURA <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </header>
      <main ref={mainRef}>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="dot" /> SMALL DEVICE. MORE PRESENCE.
            </p>
            <h1 id="hero-title">
              Be here.
              <br />
              <span className="soft">Keep the</span>
              <br />
              <span className="soft">thought.</span>
            </h1>
            <p className="hero-description">
              An AI note-taking pendant designed to keep your thoughts close.
              And your phone away.
            </p>
            <div className="hero-actions">
              <a className="pill light" href="#experience">
                Meet AURA <ArrowDown size={15} />
              </a>
              <button className="text-button" onClick={() => setFilmOpen(true)}>
                Watch the film <Play size={15} />
              </button>
            </div>
          </div>
          <div className="hero-stage">
            <DeviceViewer mode="hero" finish={finishes[0].color} />
          </div>
          <div className="hero-bottom">
            <a className="scroll-cue" href="#experience">
              <ArrowDown /> A little less screen. A little more life.
            </a>
            <span className="viewer-hint">
              <Rotate3D /> Drag to discover
            </span>
            <span className="hero-edition">DESIGN EDITION / 02</span>
          </div>
        </section>
        <div className="ribbon" aria-label="Intended product features">
          <div>
            <Fingerprint /> One-touch recording
          </div>
          <div>
            <WifiOff /> Capture, even offline
          </div>
          <div>
            <Sparkles /> Phone-assisted AI notes
          </div>
          <div>
            <ShieldCheck /> Physical privacy switch
          </div>
        </div>

        <section id="experience" className="section light-section">
          <div className="intro-heading reveal">
            <div>
              <p className="eyebrow">01 / A LITTLE MORE PRESENT</p>
              <h2>
                Stay in the moment.
                <br />
                The thought can stay, too.
              </h2>
            </div>
            <p>
              A conversation. A small revelation. The idea that arrives on a
              walk. One press gives it a place to land.
            </p>
          </div>
          <div className="demo-grid reveal">
            <div className="capture-panel">
              <img
                className="detail-image"
                src="/product/detail.webp"
                alt="Close-up of AURA’s tactile record button and softly rounded satin body"
                loading="lazy"
              />
              <div className="capture-copy">
                <h3>
                  Less to do.
                  <br />
                  More to remember.
                </h3>
                <p>
                  Press to start. Feel the confirmation.
                  <br />
                  Press again when the thought is yours.
                </p>
              </div>
            </div>
            <NoteDemo />
          </div>
          <div className="steps reveal">
            <div>
              <span className="step-index">01</span>
              <h3>Catch the thought.</h3>
              <p>
                A tactile button and a gentle pulse let you start without
                looking down.
              </p>
            </div>
            <div>
              <span className="step-index">02</span>
              <h3>Give it some clarity.</h3>
              <p>
                The companion workflow turns a recording into a transcript,
                summary and next steps.
              </p>
            </div>
            <div>
              <span className="step-index">03</span>
              <h3>Come back to it.</h3>
              <p>
                Find an idea by its meaning. Keep the original audio close to
                the note.
              </p>
            </div>
          </div>
        </section>

        <section id="design" className="section design-section">
          <div className="design-head reveal">
            <p className="eyebrow">02 / THOUGHTFULLY SMALL</p>
            <h2>
              A beautiful thought.
              <br />
              Inside and out.
            </h2>
            <p>
              A slimmer silhouette. A softer presence. Open it up and discover
              how every detail finds its place.
            </p>
          </div>
          <AssemblyExplorer />
          <div className="engineering-grid engineering-features">
            <div className="features reveal">
              <article className="feature">
                <div className="feature-icon">
                  <AudioLines />
                  <h3>A clearer starting point.</h3>
                </div>
                <p>
                  Two digital microphones, spaced across the front, form the
                  basis for speech capture.
                </p>
              </article>
              <article className="feature">
                <div className="feature-icon">
                  <Battery />
                  <h3>Made to move with you.</h3>
                </div>
                <p>
                  A rechargeable battery and magnetic charging contacts keep the
                  everyday ritual simple.
                </p>
              </article>
              <article className="feature">
                <div className="feature-icon">
                  <Bluetooth />
                  <h3>Small by working together.</h3>
                </div>
                <p>
                  Bluetooth connects the pendant to your phone. Your phone
                  handles the heavier AI work.
                </p>
              </article>
              <article className="feature">
                <div className="feature-icon">
                  <WifiOff />
                  <h3>A thought can wait for Wi-Fi.</h3>
                </div>
                <p>
                  Local flash stores recordings before a phone is in reach.
                  Capture first. Sync when ready.
                </p>
              </article>
            </div>
          </div>
          <div className="spec-line reveal">
            <div>
              <strong>40 × 30 mm</strong>
              <span>Compact body design</span>
            </div>
            <div>
              <strong>9.5 mm</strong>
              <span>Body depth target</span>
            </div>
            <div>
              <strong>2 microphones</strong>
              <span>Digital speech capture</span>
            </div>
            <div>
              <strong>One button</strong>
              <span>Record. Stop. Bookmark.</span>
            </div>
          </div>
        </section>

        <section className="section privacy-section">
          <div className="reveal">
            <p className="eyebrow">03 / YOUR MOMENT. YOUR CHOICE.</p>
            <h2>
              Privacy you
              <br />
              can put a finger on.
            </h2>
            <div className="privacy-mark">
              <ShieldCheck /> A physical microphone disconnect
            </div>
          </div>
          <div className="reveal">
            <p>
              <strong>
                When you slide it off, the microphones lose power.
              </strong>{' '}
              AURA is designed with a hardware privacy switch, a visible
              recording light and clear haptic feedback. You choose when a
              moment becomes a recording.
            </p>
            <p style={{ marginTop: 20 }}>
              Record with the knowledge of the people around you. The intended
              companion app asks before audio is sent for AI processing.
            </p>
          </div>
        </section>

        <section id="film" className="film-section">
          <img
            src="/product/hero.webp"
            alt="AURA pendant in a cinematic studio setting"
            loading="lazy"
          />
          <div className="film-copy">
            <p className="eyebrow">AURA / THE INTRODUCTION</p>
            <h2>
              For the thoughts
              <br />
              worth keeping.
            </h2>
            <button className="text-button" onClick={() => setFilmOpen(true)}>
              <span className="film-play">
                <Play />
              </span>{' '}
              Watch the launch film{' '}
              <span style={{ color: '#98989c' }}>00:36</span>
            </button>
          </div>
        </section>

        <section id="configure" className="section light-section configure">
          <div className="configure-stage">
            <DeviceViewer
              mode="configure"
              finish={finishes[finish].color}
              exploded={exploded}
              resetKey={view}
            />
            <div className="viewer-toolbar">
              <button
                className={exploded ? 'active' : ''}
                aria-pressed={exploded}
                onClick={() => setExploded(!exploded)}
              >
                <Layers3 /> {exploded ? 'Assemble' : 'Look inside'}
              </button>
              <button
                onClick={() => {
                  setView(view + 1);
                  setExploded(false);
                }}
              >
                <RotateCcw /> Reset view
              </button>
            </div>
          </div>
          <div className="configure-copy reveal">
            <p className="eyebrow">04 / MAKE IT YOURS</p>
            <h2>
              Your everyday,
              <br />
              with AURA.
            </h2>
            <p>A small companion for a mind that keeps moving.</p>
            <div className="price">
              $179 <span>Target price · USD</span>
            </div>
            <div className="finish-title">
              Finish <span>{finishes[finish].name}</span>
            </div>
            <div className="finishes" aria-label="Choose a finish">
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
            <p style={{ fontSize: 14 }}>{finishes[finish].description}</p>
            <div className="included">
              <div>
                <Check /> AURA pendant
              </div>
              <div>
                <Check /> Adjustable breakaway cord
              </div>
              <div>
                <Check /> Magnetic charging dock
              </div>
            </div>
            <button className="pill dark" onClick={() => setConfigOpen(true)}>
              Save your AURA <ArrowRight size={16} />
            </button>
            <p className="configuration-disclaimer">
              Development concept. Orders are not open.
              <br />
              Price and included accessories are design proposals.
            </p>
            <div className="availability-label">
              <span /> Explore the open development project
            </div>
          </div>
        </section>
      </main>
      <footer className="footer">
        <div className="footer-top">
          <a href="#top" className="wordmark">
            AURA
          </a>
          <span>Be here. Keep the thought.</span>
        </div>
        <div className="footer-bottom">
          <p>
            © 2026 AURA project. Product development concept. Dimensions and
            features are design targets, subject to prototype validation. AI
            screens use sample content; companion software is not connected. No
            orders or payments are accepted.
          </p>
          <a
            href="https://github.com/Avinash1286/pendent"
            target="_blank"
            rel="noreferrer"
          >
            Explore the project ↗
          </a>
        </div>
      </footer>

      <Dialog open={filmOpen} onOpenChange={setFilmOpen}>
        <DialogContent className="film-dialog">
          <DialogTitle>AURA — Be here. Keep the thought.</DialogTitle>
          <DialogDescription className="sr-only">
            A 36-second product concept launch film with original music and
            on-screen titles.
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
            <Download size={15} /> Download the film
          </a>
        </DialogContent>
      </Dialog>
      <Dialog open={configOpen} onOpenChange={setConfigOpen}>
        <DialogContent className="config-dialog">
          <p className="eyebrow" style={{ marginBottom: 2 }}>
            YOUR AURA
          </p>
          <DialogTitle>A thought for the future.</DialogTitle>
          <DialogDescription>
            Save your preferred design while AURA takes shape. The file stays
            with you; this is not a reservation or an order.
          </DialogDescription>
          <div className="config-summary">
            <span>AURA / {finishes[finish].name}</span>
            <span>$179 target</span>
          </div>
          <button className="pill light" onClick={saveConfiguration}>
            {saved ? <Check size={16} /> : <Download size={16} />}
            {saved ? 'Download again' : 'Download configuration'}
          </button>
          <p className="small-note" aria-live="polite">
            {saved
              ? 'Your configuration download is ready. You can keep exploring or follow the public project for updates.'
              : 'Hardware testing, companion software and production planning come before a launch date.'}
          </p>
          <a
            className="text-button"
            href="https://github.com/Avinash1286/pendent"
            target="_blank"
            rel="noreferrer"
          >
            Follow the open project <ArrowRight size={15} />
          </a>
        </DialogContent>
      </Dialog>
    </>
  );
}
