# Contributing

Bug reports, pull requests, and feedback are welcome. This is a small project maintained on the side, so a few notes on how to make contributions land smoothly.

## Reporting bugs

Open an issue with:

- What you ran (the script, the flags, redacted prompt if relevant)
- What you expected
- What actually happened (full error, request_id from the response if you have it)
- xAI model and version if relevant (`grok-imagine-image`, `grok-imagine-image-pro`, `grok-imagine-video`)
- Your OS and Python version

If the bug involves an API response, include the response JSON with secrets redacted. xAI's `request_id` field is the fastest way for me to verify what you saw.

## Proposing features

Open an issue first with the use case before sending a pull request. The toolkit deliberately stays close to "execution layer for the Grok Imagine API"; features that pull it toward shot-list authoring, brand systems, or video editing pipelines are usually better as separate skills that pair with this one.

Things that fit:

- New documented endpoints or parameters as xAI ships them
- Workarounds for newly discovered quirks
- Cost-tracking improvements
- Better error handling, retries, partial-failure recovery
- Test coverage for edge cases

Things that probably don't fit:

- Wrapping unrelated AI APIs (this is xAI Grok Imagine specifically)
- UI layers, dashboards, web frontends
- Video editing beyond the stitching needed for hyperframe

## Pull request guidelines

1. Fork, branch from `main`, name the branch after what it does (`fix-cloudflare-ua`, `add-mask-edit-flag`, etc.)
2. Run the lint job locally before pushing:
   ```
   pip install ruff
   ruff check scripts/ tests/
   python -m compileall -q scripts/ tests/
   ```
3. If you touched anything that hits the API, run the relevant subset of `tests/test-edges.sh` and paste the output in the PR. Full suite is ~$0.50.
4. Update `references/` if behavior changed. The reference docs are the source of truth; if a parameter changes and only the code reflects it, the next person hits the same wall you just climbed.
5. Update `SKILL.md`'s "Last verified" date if you re-ran the edge suite.
6. Keep commits scoped. One logical change per commit.

## What "verified" means in this repo

When the docs say "verified May 2026" or "verified live," that means the test suite ran successfully against the live xAI API on that date. If you change behavior, re-verify or flag the claim as unverified; don't quietly leave stale "verified" claims in place.

## Response time

I check this repo on weekends and the occasional weekday evening. Reasonable response time for issues is a few days; PRs usually within a week. If something has gone two weeks with no response, ping the issue.

## License

By contributing, you agree your contributions are licensed under the MIT License (see `LICENSE`).
