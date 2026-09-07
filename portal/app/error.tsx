'use client';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="auth-page"><div className="auth-card"><p className="brand">AURA</p><h1>Let’s reconnect.</h1><p>The notes service could not complete that request. Your saved notes remain in your account.</p><button className="primary" onClick={reset}>Try again</button></div></main>;
}
