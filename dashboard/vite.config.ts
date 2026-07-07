import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Base relative pour permettre un déploiement statique simple (sous-dossier ok).
export default defineConfig({
  plugins: [react()],
  base: "./",
});
