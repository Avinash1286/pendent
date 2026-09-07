import type { Metadata } from 'next';
import localFont from 'next/font/local';
import { ConvexAuthNextjsServerProvider } from '@convex-dev/auth/nextjs/server';
import Providers from './providers';
import './globals.css';
const manrope = localFont({ src: '../public/manrope-latin.woff2', display: 'swap', variable: '--font-manrope', weight: '200 800' });
export const metadata: Metadata = { title: 'AURA Notes — A place for your thoughts', description: 'Your notes, personal context and a portable brief for any AI conversation.' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <ConvexAuthNextjsServerProvider><html lang="en" className={manrope.variable}><body><Providers>{children}</Providers></body></html></ConvexAuthNextjsServerProvider>;
}
