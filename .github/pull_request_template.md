## Summary

- 

## Linked issue

- Closes #

## Risk

- Priority: P0 / P1 / P2 / P3
- Area:
- User-visible impact:
- Contract impact: none / docs only / State A-B-C changed

## Logic canon

Every fact this change states about Logic is either cited to Apple's own bytes, or declared
uncitable with a proof. `Scripts/check-canon-citations.py` checks this offline and CI runs it.
See `docs/canon/README.md`.

Canonical sources this change rests on — paste each reference and the value it resolves to:

```text
logic-canon://<source>/<unit>/<locale>/<key>#<field>
  value:    <the exact string Logic ships>
  used for: <what in this change stands on it>
```

- [ ] `Scripts/logic_canon.py check '<ref>=<value>'` passes for every reference above
- [ ] Anything this change asserts about Logic that is NOT above is listed here with
      `Scripts/logic_canon.py absent <source> <locale> '<string>'` output showing it is uncitable:

```text

```

- [ ] No reference above → this change asserts nothing about Logic. Say so in the exact wording
      `docs/canon/README.md` gives under **The opt-out**, and give the reason. It is deliberately
      NOT written here: a template that types the sentence for you is a sentence nobody meant, and
      the first version of this file shipped it pre-typed, so every untouched template passed.
      A reference alone is not a citation either — the value it resolves to must be in this body.
      The opt-out is refused outright for a change that edits a Logic-facing path.

## Verification

- [ ] `swift build`
- [ ] `swift test --no-parallel`
- [ ] `swift build -c release`
- [ ] Targeted test:
- [ ] Live Logic evidence: not required / attached below

Evidence:
```text

```

## Release readiness

- [ ] Public claims, API docs, troubleshooting, and changelog are updated if behavior changed.
- [ ] Mutating or destructive behavior has explicit target validation, confirmation, and readback.
- [ ] Known limitations are documented in the PR or docs.

## Reviewer focus

-
