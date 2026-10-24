import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The repository root's schema/ is the single source for thresholds shared with the
// backend and the contract; @schema/... imports it at build time.
const sharedSchema = fileURLToPath(new URL('../schema', import.meta.url))
// contracts/shared builds the on-chain project key of a demo round ("ATH-0142#3"); the
// contract scripts and the oracle use the same file.
const sharedChain = fileURLToPath(new URL('../contracts/shared', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@schema': sharedSchema, '@shared': sharedChain } },
  // The dev server only serves files under frontend/ unless the shared folders are allowed.
  server: { fs: { allow: ['.', sharedSchema, sharedChain] } },
})
