import { defineConfig } from 'vitest/config';

// SANDBOX: the isolation lock runs before every test file, so no test can
// reach a live service even if the copied code tries to.
export default defineConfig({
  test: {
    setupFiles: ['./isolation/lock.mjs'],
  },
});
