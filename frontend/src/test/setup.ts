import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// We deliberately don't set `test.globals: true` in vitest.config.ts (every
// test file imports describe/it/expect/vi explicitly) — but that means
// @testing-library/react can't auto-detect a global `afterEach` to
// register its own cleanup. Without this, renders from one test leak into
// the next test's DOM ("Found multiple elements..."). Wire it explicitly.
afterEach(() => {
  cleanup()
})
