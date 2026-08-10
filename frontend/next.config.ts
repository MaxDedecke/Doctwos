import type { NextConfig } from "next";

// Next.js' Dev-Server blockiert standardmäßig Cross-Origin-Requests auf
// interne Endpunkte (u.a. den /_next/webpack-hmr-Websocket) von allem außer
// localhost (DNS-Rebinding-Schutz). Diese Instanz wird während der
// Entwicklung über die öffentliche IP erreicht, daher muss sie explizit
// erlaubt werden - sonst schlägt der HMR-Handshake mit
// ERR_INVALID_HTTP_RESPONSE fehl.
const nextConfig: NextConfig = {
  allowedDevOrigins: ["82.165.216.180"],
};

export default nextConfig;
