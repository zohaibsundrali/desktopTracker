# Verisade dashboard visual refresh

The dashboard now uses the login/website dark HSL tokens, bundled Inter UI font, Space Grotesk timer/headings, white primary text and the same Verified V mark. Window ownership, the 860×720 starting size and 760×600 minimum are unchanged.

The scrollable main area groups the current session and timer controls first, followed by project/task selection, four compact metric tiles, activity lists, capture synchronization and break/idle controls. Every existing field and command remains wired to its existing callback. The previously static zero-valued decorative bars in count tiles are replaced by line icons; real activity percentages and list durations still drive the actual progress indicators. No tracking totals are fabricated.

Disabled actions use quiet status tints; Start is green, Pause amber, Stop red and Resume uses the existing indigo accent. Keyboard activation/focus outlines are supported on navigation and buttons. Project/task option menus retain their selection and lock logic. Long application names wrap above their duration bars; sync descriptions rewrap on resize. All underlying tracker, synchronization, authorization and persistence modules are unchanged.

The `theme.py` dark palette is shared by the dashboard's dynamic status callbacks, so updates no longer revert to unrelated blues. The existing light token values remain for other callers. The login continues explicitly selecting dark mode.

Validation: `scripts/dashboard_ui_smoke.py` uses the real widgets and an inert timer, checks the normal/minimum/expanded layouts, 100/125/150% scaling, populated list rendering, action enabled/disabled styling and existing support callbacks. It saves screenshots in the Windows workflow. No tracking, capture or provider requests run in this visual check. The existing 226-test regression suite also covers work-selection and tracking handlers; its headless UI harness now supplies the shared color-token lookup.

This changes presentation, not release trust. Unsigned installers still require an appropriate testing environment; Store signing/certification and physical-device capture acceptance remain separate.
