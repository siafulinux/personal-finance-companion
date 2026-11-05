import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../", "");
  const webPort = Number(env.WEB_PORT || 5183);
  const apiPort = Number(env.API_PORT || 8010);
  // A wildcard bind means "all interfaces"; the dev proxy still connects over loopback.
  const apiHost =
    !env.API_HOST || env.API_HOST === "0.0.0.0" ? "127.0.0.1" : env.API_HOST;

  return {
    plugins: [react()],
    server: {
      host: env.WEB_HOST || "127.0.0.1",
      port: webPort,
      strictPort: true,
      proxy: {
        "/api": {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: false,
        },
      },
    },
    preview: {
      host: env.WEB_HOST || "127.0.0.1",
      port: webPort,
      strictPort: true,
    },
  };
});
