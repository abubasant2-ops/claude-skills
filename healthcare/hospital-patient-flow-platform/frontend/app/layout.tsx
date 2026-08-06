import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Patient Flow Command Centre',
  description:
    'Hospital patient flow and operational intelligence — capacity, emergency, journey, quality and nursing indicators from imported Excel extracts.',
};

/**
 * The root layout deliberately renders no <html> chrome of its own: lang
 * and dir depend on the locale segment, so the locale layout owns them.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
