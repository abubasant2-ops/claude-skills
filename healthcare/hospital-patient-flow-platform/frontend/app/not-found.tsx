import Link from 'next/link';
import { DEFAULT_LOCALE } from '@/lib/i18n';

export default function NotFound() {
  return (
    <html lang="en">
      <body className="grid min-h-screen place-items-center bg-canvas p-8 text-ink">
        <div className="max-w-md text-center">
          <h1 className="text-2xl font-semibold">Page not found</h1>
          <p className="mt-2 text-sm text-ink-muted">
            That command centre does not exist. Available views are Executive,
            Operations, Emergency, Bed Management, Nursing and Quality.
          </p>
          <Link
            href={`/${DEFAULT_LOCALE}/command/ceo`}
            className="mt-4 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-canvas"
          >
            Go to the executive dashboard
          </Link>
        </div>
      </body>
    </html>
  );
}
