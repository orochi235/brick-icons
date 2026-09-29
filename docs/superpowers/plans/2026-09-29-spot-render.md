# Spot Rendering (brick-icons side): what is left

**Status: Tasks 1–24 are built and merged (main a68d64b); Task 25 is half
done -- the merge, the fleet suite and the worker are done, the sheet masters
and the lab-side check (Steps 3, 5–9) are not.** The built tasks were cut from this plan; the
spec, `docs/superpowers/specs/2026-09-29-spot-render-design.md`, describes
what was built, and DEVELOPING.md's "Spot rendering" section is the launch
recipe. HANDOFF.md's spot-rendering entry carries the same steps in short.

Run every `onto` command with the Bash sandbox disabled; sandboxed, onto
reports every node `offline`. Ask before `gh pr create`.

---

### Task 25: Merge, test on the fleet, and check it end to end

Run once. The render happens on studio; this Mac runs only the lab and a
headless browser.

- [x] **Step 1: Merge** -- done 2026-09-28 as a fast-forward push of
`spot-render` to main (a68d64b), no PR. Still open: pull the main checkout,
and delete the `spot-render` branch and any worktree on it.

- [x] **Step 2: The full Python suite on the fleet, in the background** --
done 2026-09-28 on studio at a68d64b: 1777 passed, 1 xfailed (test_occt 4589),
2 failed, both known: test_occt's sticker-on-slope test, and test_lab_review's
linked-view test (fixed on the unmerged `review-orphans` branch).

Run (sandbox disabled, backgrounded, not waited on):
`onto test --in brick-icons --ref origin/main --node studio`
Read its exit code when it finishes; a failure becomes the next thing to fix.
An OOM kill or a timeout in a file this plan did not touch is contention, not
a regression.

- [ ] **Step 3: Write every slot's sheet masters, on the fleet**

The lossless masters (`sheet-<level>.master.png`) exist only once a slot has
been composed by the new code, and until then every redraw's sheet patch is
refused with a warning (the drawing and tiles are still stored). Run
`scripts/bake-thumbs.py` per slot. Estimate it first (items times seconds per
item, from a timed bake of one slot, as core-hours and wall time) and launch
it with `onto run --kind bake` per CLAUDE.md, rather than on this Mac.

Estimate so far, not measured under the new code: HANDOFF records a bake of
the occt slot at about 100 s. Every tile is already fresh (unchanged shas
skip), so a bake is mostly `compose`, plus the new ~35 MB lossless master per
slot. 13 slots at 100–150 s is roughly 20–35 min on one core, about 0.5
core-hours. The inputs (`out/thumbs`, 4.3 GB, and `corpus.db`) live only on
this Mac, so a fleet run ships them out and the sheets back.

- [x] **Step 4: Provision and start the worker** -- done 2026-09-28: up on
studio at a68d64b; ping answers `1664.a68d64b`; a 3001 occt request came back
`drawn` in 11.2 s on the first call (worker `secs` 1.1) and 0.7 s warm.

Follow DEVELOPING.md, "Spot rendering": sync `brick-icons-spot` to studio,
clone `.venv` and `vendor/ldraw` into it, `onto service up`. Then check that
`onto call brick-spot-render '{"ping": true}'` answers at origin/main's build
and that `onto service ls` shows it on studio.

- [ ] **Step 5: Reload the lab and read its view of the worker**

After `git pull` and `(cd lab && npm ci)` in the main checkout, run
`brick-lab install` there (it writes the new PATH into the agents; `cycle`
only restarts them on the old plists), then `brick-lab stat`.
Expected: `spot render` reads `up at <origin/main build>`.

- [ ] **Step 6: Redraw 612p01 headless**

With the playwright MCP (headless), open `http://localhost:5178/wall`, find
612p01, and note the wall cell's tile URL and the lightbox's `occt` image
`src` (`v=<sha8>`). Click `Redraw occt`. Expect `Drawing…` (or
`updating worker…` if the worker was rolled), then the image `src` changing to
a new `v=` and, within a second, the wall cell's 128 px tile fetched under the
new sha -- and that tile showing the new drawing, not the old one or a 404
(the tiles are baked before `changed` is sent). No reload. Screenshot the lightbox and the cell before and after.

If the answer is `unchanged`, the path is proven but not the swap: the stored
drawing already matched origin/main. Pick a part drawn before the last engine
change instead:

    since=$(git log -1 --format=%cI -- brick_icons/)
    sqlite3 corpus.db "SELECT part_id FROM renders WHERE source = 'occt' \
      AND made_at < '$since' ORDER BY made_at LIMIT 5"

and redraw the first of those.

- [ ] **Step 7: Put the evidence on the wall**

Build one sheet with `scripts/_sheet.py`: a title line naming the part and
slot, panels labeled `before` and `after`, and the third diff panel. Send it
with `transom post <file>` to the `brick-icons` zone.

- [ ] **Step 8: Close the docs**

Delete this plan. The spec,
`docs/superpowers/specs/2026-09-29-spot-render-design.md`, stays as the record;
set its status line to "built and merged".

- [ ] **Step 9: Stop what this check started**

Close the headless browser. The worker stays up: it is the service.
