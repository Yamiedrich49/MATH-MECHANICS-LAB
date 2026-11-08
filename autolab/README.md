# AUTOLAB — Nightly Autonomous Game Research (v1)

A real, sequential multi-agent prototype integrated **without changing the existing main game**.

**Agents (separate Responses API calls):**
Inventor → Skeptic → Designer ↔ Adversarial reviewer (up to 3 design passes) → Implementer → Independent tester → optional repair engineer.
Every call has its own instructions and receives only the data needed for its role. This is not five parallel chats, and agreement between them is not evidence that the game is fun.

## State as of installation
- Cron: 00:43 JST daily, GitHub Actions.
- **Safe by default:** schedules skip unless repository variable `AUTOLAB_ENABLED` is exactly `true`.
- Manual `workflow_dispatch` defaults to free DEMO (no API calls).
- LIVE requires OpenAI **API** key (ChatGPT Plus subscription is separate).
- API token and call controls are in `autolab/config.json`. USD ceiling is an **estimated soft guard**, not an API billing hard cap. Configure a separate API project budget/alerts.
- Output: `autolab/output/index.html`, `game.html`, `latest.json`, `report.md`. Only these paths get new automated commits.
- GitHub Pages preview target after opt-in: `https://yamiedrich49.github.io/MATH-MECHANICS-LAB/autolab/output/`. Merely committing with `GITHUB_TOKEN` does not trigger a branch-source Pages deployment; opt in to the included deploy-pages step and switch Pages source to Actions.
- Existing root `index.html` and saved game data remain untouched.

## Setup (iPhone Safari)
1. Open https://platform.openai.com/api-keys and create a restricted project API key.
2. Open https://github.com/Yamiedrich49/MATH-MECHANICS-LAB/settings/secrets/actions ; add repository secret `OPENAI_API_KEY` (never paste it into code or chats).
3. Open https://github.com/Yamiedrich49/MATH-MECHANICS-LAB/actions/workflows/autolab-nightly.yml ; manually click **Run workflow** with demo=true to test without API spend. The separate check job also runs on PR/push automatically.
4. When ready, change `demo=false` to perform **one paid live run**.
5. Only after approving recurring charges, open https://github.com/Yamiedrich49/MATH-MECHANICS-LAB/settings/variables/actions and add repository variable `AUTOLAB_ENABLED` = `true`. Set it to `false` to pause future scheduled runs.
6. For automated nightly Pages updates, set GitHub Pages source to **GitHub Actions** in https://github.com/Yamiedrich49/MATH-MECHANICS-LAB/settings/pages and opt in by setting repository variable `AUTOLAB_PAGES_ENABLED` = `true`. This deploys the existing root game and AUTOLAB subfolder together. Leave the variable unset to avoid changing Pages behavior. This is PUBLIC.

### What is and isn't tested
Static checks reject network calls/remote assets and use `node --check` to parse the generated JavaScript, but do **not** prove solvability, uniqueness, touch feel, visual polish or absence of runtime bugs.
No untrusted generated JavaScript is executed on the GitHub runner. The game is embedded in a sandboxed iframe and receives a restrictive CSP.
Generated pages are **public if GitHub Pages is enabled** on this public repository. Do not put business secrets or private preference records here.

### Failure behavior
- Bad ideas fail the design gate and no fresh game is advertised.
- Failed code safety/syntax checks prevent publication.
- API failures produce an ERROR report and fail the Action; an old prototype file may remain in git, but the dashboard never labels it as a new success.
- If a repaired game passed only static checks, the report discloses missing second AI review.
- This version does not run visual end-to-end Safari tests, search the internet for competing game mechanics, or automatically deliver iOS push notifications.

### Test locally
```sh
python -m unittest discover -s autolab/tests -v
python autolab/run.py --demo
# OPENAI_API_KEY=... python autolab/run.py --live
```

### Next iteration
Add browser-automation screenshot tests; calibrate critic against the owner's accept/reject examples; add candidate collision/search checks; add explicit human feedback as evaluations rather than silently assuming the AI can predict subjective fun.
\n## Preference calibration\nThe engine loads `autolab/feedback.json` for every independent agent call. This currently stores concise positive, negative, and mixed examples from prior game design reviews. It is deliberately NOT a direct connection to ChatGPT private memory. Update that file after real playtests. Autonomous AI scoring should never replace the user's acceptance test.\n