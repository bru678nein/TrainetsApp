/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 is Vite's default and it is not an arbitrary choice here: it is the
    // value `AUTH_AUTHORIZED_PARTY` carries in development, which the backend
    // compares against the token's `azp` claim and also uses as the allowed CORS
    // origin. Moving this port means moving that setting, or every request fails
    // twice over with two errors that look unrelated.
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
