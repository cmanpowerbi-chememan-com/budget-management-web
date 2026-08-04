import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { resetSessionExpiredForTests } from '../api/sessionExpiry'

// We deliberately don't set `test.globals: true` in vitest.config.ts (every
// test file imports describe/it/expect/vi explicitly) — but that means
// @testing-library/react can't auto-detect a global `afterEach` to
// register its own cleanup. Without this, renders from one test leak into
// the next test's DOM ("Found multiple elements..."). Wire it explicitly.
afterEach(() => {
  cleanup()
  // The session-expiry latch (api/sessionExpiry.ts) is a module-level
  // singleton — vitest isolates per FILE, not per test, so a test that
  // raises it would otherwise leak a phantom dialog into every later test
  // in the same file.
  resetSessionExpiredForTests()
})
