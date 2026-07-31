import type { Metadata, Viewport } from "next";
import { Archivo, Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { LanguageProvider } from "@/lib/i18n/LanguageContext";

// Doctus brand type system (from the Doctus Design blueprint mock): Archivo
// for body/UI text, Space Grotesk for headings, IBM Plex Mono for
// labels/badges/code — exposed as CSS vars and wired into Tailwind's
// font-sans/font-heading/font-mono in tailwind.config.js.
const archivo = Archivo({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-archivo" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-space-grotesk" });
const ibmPlexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-ibm-plex-mono" });

// process.env.API_URL must be read at request time, not baked in at build
// time like NEXT_PUBLIC_* vars are — force-dynamic stops Next.js from
// statically pre-rendering this layout (and thus the env value) at build.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Doctus AI - Code Knowledge System",
  description: "Enterprise Knowledge for Legacy Codebases",
};

// maximumScale/userScalable bewusst NICHT gesetzt: sie unterbinden Pinch-Zoom
// und verstoßen gegen WCAG 1.4.4 (NF-012) — bei AP-9 per axe-core gefunden.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

async function fetchFeatures(): Promise<object | null> {
  try {
    const internalUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";
    const res = await fetch(`${internalUrl}/config/features`, { cache: "no-store" });
    if (res.ok) return await res.json();
  } catch {}
  return null;
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const features = await fetchFeatures();

  return (
    <html lang="en">
      <head>
        <script
          dangerouslySetInnerHTML={{
            // Runs before hydration so the `.dark` class (which now gates the
            // shadcn CSS vars in globals.css) is set before first paint —
            // otherwise the page flashes the light "drafting paper" palette
            // before app/page.tsx's theme useEffect corrects it.
            __html: `(function(){try{var t=localStorage.getItem('doctus-theme');document.documentElement.classList.toggle('dark',t!=='light');}catch(e){document.documentElement.classList.add('dark');}})();`,
          }}
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__DOCTUS_API_URL__ = ${JSON.stringify(process.env.API_URL || "http://localhost:8000")}; window.__DOCTUS_FEATURES__ = ${JSON.stringify(features)};`,
          }}
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                var handleCancellation = function(event) {
                  var reason = event.reason;
                  if (reason && (
                    reason.name === 'Canceled' ||
                    reason.message === 'Canceled' ||
                    reason.message === 'Canceled: Canceled' ||
                    (typeof reason === 'object' && reason.type === 'cancelation')
                  )) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                  }
                };
                var handleGlobalError = function(event) {
                  var errorMsg = event.message || (event.error && event.error.message) || "";
                  var errorName = (event.error && event.error.name) || "";
                  if (
                    errorName === 'Canceled' ||
                    errorMsg === 'Canceled' ||
                    errorMsg === 'Canceled: Canceled' ||
                    errorMsg.indexOf('Canceled') !== -1 ||
                    (event.error && typeof event.error === 'object' && event.error.type === 'cancelation')
                  ) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                  }
                };
                window.addEventListener('unhandledrejection', handleCancellation, true);
                window.addEventListener('error', handleGlobalError, true);
              })();
            `
          }}
        />
      </head>
      <body className={`${archivo.className} ${archivo.variable} ${spaceGrotesk.variable} ${ibmPlexMono.variable}`}>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
