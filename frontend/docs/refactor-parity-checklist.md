# Frontend Refactor Parity Checklist

Use this checklist before and after behavior-preserving frontend refactors.
`npm run build` is the minimum automated gate; the manual checks below cover the
current user-visible behavior that is not yet protected by tests.

## Automated Baseline

- Run `npm run build` from `frontend/`.
- Confirm static export routes include `/`, `/_not-found`, and `/app`.

## Landing Page

- Open `/` and confirm the UrbanFlux landing page renders.
- Toggle light/dark mode from the header and confirm the page theme changes.
- Confirm the primary action opens `/app`.
- Confirm the GitHub link still points to the UrbanFlux repository.

## CityTwin App

- Open `/app` and confirm the MapLibre map initializes with the demo zone.
- Confirm the status, context pills, population card, and dashboard render without runtime errors.
- Toggle the basemap theme and confirm the map theme follows the UI.
- Use Demo, Undo, Clear, and Refit controls and confirm the map responds.
- Adjust all six sliders and confirm their displayed values update immediately.
- Toggle Water override and confirm it remains reflected in the switch state.
- Draw a polygon with at least four points and confirm generated roads/buildings/green space render.
- Drag a vertex and confirm the plan updates.
- Start Auto improvement, then Stop and Restart it; confirm manual controls recover after stopping.
- Confirm impact metrics load or show their existing fallback/error state without breaking layout.

## Responsive Layout

- On desktop width, confirm the left status column, right controls/dashboard column, and bottom hint are visible.
- On mobile width, confirm the home button is visible and controls move into the bottom sheet.
- Expand and collapse the bottom sheet and confirm the content remains scrollable.

## Static Export

- After `npm run build`, confirm `frontend/out/index.html` and `frontend/out/app.html` exist.
