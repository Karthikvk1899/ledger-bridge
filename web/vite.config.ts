import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], server: { proxy: { '/v1': 'http://api:8000', '/health': 'http://api:8000' } }, test: { environment: 'jsdom' } });
