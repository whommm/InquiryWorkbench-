# SmartProcure Risk Fix Todo

Updated: 2026-02-16

## P0 (Critical: build and quality gate)

- [x] Fix frontend build script (`vite` command not found)
  - File: `smart-procure/frontend/package.json`
  - Done: switched scripts to direct node entrypoint and added `--configLoader native`
  - Verification: `npm run build` passes in `smart-procure/frontend`

- [x] Clear frontend lint errors
  - Files touched:
    - `smart-procure/frontend/src/App.tsx`
    - `smart-procure/frontend/src/components/ChatPanel.tsx`
    - `smart-procure/frontend/src/components/Header.tsx`
    - `smart-procure/frontend/src/components/HistoryPanel.tsx`
    - `smart-procure/frontend/src/components/RecommendPanel.tsx`
    - `smart-procure/frontend/src/components/UniverSheet.tsx`
    - `smart-procure/frontend/src/hooks/useAutoSave.ts`
    - `smart-procure/frontend/src/hooks/useProcureState.ts`
  - Verification: `npm run lint` passes in `smart-procure/frontend`

## P1 (Important: feature integrity)

- [x] Implement ChatPanel "clear chat" action
  - File: `smart-procure/frontend/src/components/ChatPanel.tsx`
  - File: `smart-procure/frontend/src/App.tsx`

- [x] Complete history restore flow
  - File: `smart-procure/frontend/src/components/HistoryPanel.tsx`
  - File: `smart-procure/frontend/src/App.tsx`
  - Note: restore now loads selected sheet and chat history into a tab

- [x] Replace mock export with real backend export
  - File: `smart-procure/frontend/src/components/Header.tsx`
  - API: `exportSheet(activeTab.id)`

- [x] Replace mock notifications with backend notifications
  - File: `smart-procure/frontend/src/components/Header.tsx`
  - API: `getNotifications()` polling + unread handling

## P2 (Stability and maintainability)

- [x] Standardize backend timezone-aware datetime usage
  - Files updated:
    - `smart-procure/backend/app/services/notification_service.py`
    - `smart-procure/backend/app/models/database.py`
    - `smart-procure/backend/app/auth/routes.py`
    - `smart-procure/backend/app/auth/utils.py`
    - `smart-procure/backend/app/services/db_service.py`
    - `smart-procure/backend/app/services/supplier_service.py`
    - `smart-procure/backend/app/api/suppliers.py`
  - Notes: introduced `smart-procure/backend/app/core/datetime_utils.py` with `utc_now()` / `ensure_utc()`

- [x] Replace key backend `print` statements with structured logging
  - File: `smart-procure/backend/app/api/routes.py`
  - Notes: `print(...)` replaced with `logger.warning(...)` and contextual messages

- [ ] Add frontend regression tests for save/restore/chat core flows
  - Suggested path: `smart-procure/frontend/src/__tests__/`
  - Blocker: cannot install test dependency in current sandbox (`npm install -D vitest` failed: network `EACCES`)

## Current verification status

- Frontend lint: PASS (`npm run lint`)
- Frontend build: PASS (`npm run build`)
- Backend tests: PASS (`python -m unittest discover -s smart-procure/backend/app/tests -p "test_*.py"`)
