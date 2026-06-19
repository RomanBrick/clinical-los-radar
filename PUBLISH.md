# How to publish this as the public `clinical-los-radar` repo

This `showcase/` folder is the **complete, ready-to-publish** public repo:
the curated **code** (dbt models + tests for the renal-wedge lineage, and the Python
training / external-validation scripts), the README + figures, the curated docs, and
the metric artifacts that back every number.

It contains **no data** (MIMIC-IV / eICU are credentialed PhysioNet datasets and are
git-ignored), so it is safe to make public. The curated dbt project has been verified
to parse cleanly (`dbt parse`).

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
git commit -m "Clinical LOS Radar — renal longer-stay wedge (code, docs, results)"
git remote add origin https://github.com/RomanBrick/clinical-los-radar.git
git push -u origin main
```

That's it: a brand-new public repo, **single `main` branch, clean history**, with the
curated code but no data.

## Notes
- Only the renal-wedge lineage is included (not the legacy multi-window exploration),
  so the public repo stays focused and coherent.
- The full working repo (all branches, exploratory models, history) stays private.
- To refresh numbers/figures later: regenerate in the private repo and copy the updated
  `assets/*.png` and `docs/*_metrics.*` here, then commit.
- Optional polish on GitHub afterwards: add topics (`healthcare`, `machine-learning`,
  `dbt`, `mimic-iv`, `clinical-ml`), and pin the repo on your profile.
```
