/** Response shapes returned by the FastAPI backend endpoints this SPA calls
 * (see backend/app/routers/{me,scope}.py). Kept in lock-step with those
 * Pydantic models — do not add fields speculatively. */

export interface MeResponse {
  email: string
  app_env: string
}

export type ScopeRole = 'admin' | 'filler' | 'see_only' | 'none'

export interface ScopeResponse {
  email: string
  is_admin: boolean
  role: ScopeRole
  fill_cost_centers: string[]
  see_cost_centers: string[]
}
