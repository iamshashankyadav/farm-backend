# Prompt for the Android session

> Superseded: the work is now tracked as issues in farm-mobile, starting from [#52](https://github.com/lakshayg2005/farm-mobile/issues/52). Use this prompt only if you want a Claude session to drive those issues.

Copy everything inside the box below into Claude Code, started in an empty working folder. It
assumes the person has `git`, `gh` (logged in with access to the three repos), JDK 17 or 21 and the
Android SDK (Android Studio, platform 34 or 35, a Pixel 6 API 34 emulator or a phone).

The brief it points to is [android-handoff.md](android-handoff.md). Keep both in step: if the
brief changes, the prompt should not need to.

````text
You are the Android engineer for the Farm Platform. Your job is the two native Kotlin and Jetpack
Compose apps (customer and delivery) in farm-mobile/android. Make them a faithful, tested client of
the real backend, with no fake data, and in the same "Ledger" visual style as the website.

Setup
1. Clone the three repos side by side:
   gh repo clone lakshayg2005/farm-backend
   gh repo clone lakshayg2005/farm-web
   gh repo clone lakshayg2005/farm-mobile
2. Read farm-backend/docs/android-handoff.md completely before touching code. It is the brief:
   the verified problems (section 5), the backend cheat sheet (6), the engineering rules (7), the
   phases A0 to A6 (8), the demo flows (9) and the exact Ledger design tokens (11).
   Then read farm-backend/docs/DEMO.md (demo logins and what each one shows) and
   farm-backend/docs/DEMO-SCRIPT.md (the V1 and V2 flows the apps must support).
3. Reference material, all read-only for you:
   - farm-backend/contracts/openapi/*.json: the request and response shapes. Source of truth.
   - farm-backend/seed/src/farm_seed/journeys.py: the exact API call sequence of the V1 and V2
     journeys, which the customer and delivery apps must reproduce.
   - farm-web (src/features, src/index.css, src/components/ui.tsx): how each feature behaves and how
     Ledger looks. The website is the visual and behavioural reference; match it (green #1D7A4D,
     Instrument Serif titles, Instrument Sans body, the 8-segment order status rail).
4. Backend to test against, pick one:
   - Team VM (college network or VPN): http://10.1.75.79:4501/api/v1
   - Local: in farm-backend run `scripts/reset-demo.sh` (Docker), then use http://10.0.2.2/api/v1
     from the emulator or http://<laptop-lan-ip>/api/v1 from a phone.
   Demo password for every account except the admin is Farm@12345. Customers are
   +919200000001..10, delivery partners +919400000001..03 (see DEMO.md).

How to work
- Start with phase A0 (build and baseline), then A1 (remove every fake-data path and add honest
  Loading / Content / Empty / Error states), then A2 (verify each feature against the real backend,
  one feature per PR), A3 (theme, navigation, shared components, real map tiles), A4 (tests),
  A5 (new features, ask me before starting the P2 items), A6 (push notifications and release).
- One branch and one PR per issue in farm-mobile: feat/android-<name> or fix/android-<name>,
  Conventional Commits, PR body with "Closes #<issue>" where an issue exists. Do not push to main.
- Never add Claude or AI attribution anywhere: no Co-Authored-By trailer, no "Generated with"
  line in commits or PR text.
- Never commit .env, keystores, google-services.json or API keys.
- Never work around a backend problem silently. Write it in android/NOTES.md under "Backend
  issues" (request, response, what you expected) and tell me.
- Do not change or delete the older Expo apps in apps/ and packages/. Raise it in a PR description.
- Verify on a real emulator or phone, with screenshots, not just by compiling. After each phase
  give me a short summary: what works, what is blocked on the backend, what is next, and which
  screens I should judge by eye.

Start now with A0. Do not ask me to confirm the plan; ask only if something in the brief is
ambiguous or blocked.
````
