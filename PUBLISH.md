# How to publish this as the public `clinical-los-radar` repo

This `showcase/` folder is the **complete, ready-to-publish** public repo:
README + figures + curated docs + the metric artifacts that back every number.
It contains **no code, no SQL, no data** — safe to make public.

## One time: create the empty repo on GitHub
1. Go to https://github.com/new
2. Name: **`clinical-los-radar`**
3. Visibility: **Public**
4. **Do NOT** add a README, .gitignore, or license (we push our own).
5. Create repository.

## Push this folder as its own clean repo
From the repo root, on your machine (after pulling the branch):

```bash
cd showcase
git init -b main
git add .
git commit -m "Clinical LOS Radar — case study (write-up, figures, metric artifacts)"
git remote add origin https://github.com/RomanBrick/clinical-los-radar.git
git push -u origin main
```

That's it: a brand-new public repo, **single `main` branch, clean history, no code**.

## Notes
- The full implementation (dbt models, training & eICU-validation scripts) stays in
  the private `CDSP` repo. Nothing here exposes it.
- If you later want to refresh the numbers/figures, regenerate them in the private
  repo and copy the updated `assets/*.png` and `docs/*_metrics.*` here, then commit.
- Optional polish on GitHub afterwards: add topics (`healthcare`, `machine-learning`,
  `dbt`, `mimic-iv`), and pin the repo on your profile.
