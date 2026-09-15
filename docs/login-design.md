# Verisade desktop login design

The login uses the website's exact dark HSL background, card, border and primary tokens from `src/app/globals.css`. Secondary text is white composited over the card; primary text is white. The primary button uses the website's dark primary-foreground for readable contrast on its indigo primary. The logo mirrors the tile radius, check points and stroke width from `src/components/brand/brand.js`.

The default window is 900 × 640 logical pixels, with a 480 × 640 minimum. Below 780 logical pixels the brand panel collapses to a compact header without recreating the form or losing typed values. Inter and Space Grotesk ship with the frozen app. No webview or external font request is introduced.

Keyboard focus outlines, keyboard activation of buttons, Enter submission, readable field labels and a busy button state improve form interaction. Authentication, remembered-email persistence, dashboard navigation and registration/password-reset callbacks remain unchanged. The latter two callbacks were already informational “coming soon” dialogs; this visual change does not implement those flows. Authentication remains synchronous as before.

Validation: `scripts/login_ui_smoke.py` constructs actual widgets with inert providers, checks layout bounds at wide/narrow sizes and 100/125/150% scaling, calls the submit wrapper and existing footer actions, and saves wide/narrow screenshots. The Windows workflow runs this check and attaches previews. No screenshots, input capture, login requests or backend writes occur in the smoke test.
