import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';

// Android Chrome only exposes camera/mic/geolocation on secure origins, so the dev
// server runs on self-signed HTTPS and binds to the LAN (open https://<laptop-ip>:5173
// on the phone and accept the certificate warning once).
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  worker: { format: 'es' },
  test: { environment: 'node' },
});
