import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    const backendTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000';
    const backendProxy = {
        target: backendTarget,
        changeOrigin: true,
        headers: {
            Host: 'localhost',
        },
    };
    const proxy = {
        '/api': backendProxy,
        '/health': backendProxy,
        '/docs': backendProxy,
        '/openapi.json': backendProxy,
    };

    return {
        plugins: [react()],
        server: {
            host: '0.0.0.0',
            proxy,
            watch: {
                usePolling: env.VITE_USE_POLLING === 'true',
            },
        },
        preview: {
            proxy,
        },
    };
});
