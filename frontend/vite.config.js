import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    const proxy = {
        '/api': {
            target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
            changeOrigin: true,
        },
    };

    return {
        plugins: [react()],
        server: {
            proxy,
        },
        preview: {
            proxy,
        },
    };
});
