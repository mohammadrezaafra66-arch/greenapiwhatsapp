import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Optional: proxy API in dev so you can use relative /api/v1 paths
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
