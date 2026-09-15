# The canon axis

**Apple's own bytes are the source of truth. A measurement is what we do where Apple's bytes cannot
answer — and that they cannot is itself checked, not asserted.**

## Why

Every failure this repository has had about Logic's interface has one shape: a string somebody
typed, standing where a string Logic ships should have been.

`playheadPositionGroupLabel` carried `再生ヘッド位置`. Logic shows `再生ヘッドの位置`. One missing
character made the element unfindable on every Japanese Logic, the set is matched whole, and the
ledger read it as coverage. Nothing was lying. Nothing had a way to check.

Measured on 2026-09-15, that is not an isolated case:

```
AXLocalePolicy holds 379 distinct literals the product matches Logic's interface with
  113   are a QuickHelp Title
  226   are somewhere in the bundle's 605,190 .strings entries
   40   are in no file of the app bundle
```

Those counts are printed by `Scripts/check-policy-literals-against-canon.py`, and they are the
only place they are written down. An earlier revision of this file carried 120/222/37 -- a first
pass taken before the extractor stopped counting `rationale` prose as labels -- in four documents
at once, in a change whose subject is typed numbers drifting from measured ones.

Some of those 37 are deliberate substrings for `.contains` matching. Some are labels nobody can
find. The repository could not tell which, because it had no notion of a citation.

## The rule

1. A fact about Logic is **cited** to bytes inside Logic, by a reference that resolves and a quoted
   value whose digest matches Apple's.
2. A fact that cannot be cited is declared **`canon_absent`**, with the string, the corpora
   searched, and why a runtime measurement is the only route.
3. Both are checked mechanically, in CI, with no Logic installed.

That last clause is the whole design problem. `docs/observations/LOGIC-BUILD.json` already says CI
has no Logic — which is why the build there is declared rather than detected. A checker that needs
the application is advice, not a gate.

## How it works offline

```
build time   (needs Logic)     extract → digest → commit docs/canon/
check time   (needs nothing)   resolve a citation against what was committed
```

| file | what it is |
|---|---|
| `SOURCES.json` | which Logic assets are canonical, what each can answer, and what each cannot |
| `MANIFEST.json` | the exact Logic build and a digest over every byte of every corpus file |
| `index/<source>.tsv` | key → digest, for keys something in this repository actually cites |
| `absence/<source>.<locale>.u32` | the sorted 32-bit digest prefixes of **every** value in that corpus |
| `WITHOUT-CANON.json` | records written before the rule. May only shrink. |

The index holds only cited keys on purpose. A full QuickHelp index is 295,050 rows across ten
locales, and a checked-in artefact that size stops being read. The absence sets are the opposite:
they must be complete, because proving absence needs the whole corpus.

### The corpus is bounded, and the bound is the claim's bound

The absence sets cover four sources: `QuickHelp.plist`, every `.strings` file, MADSP's parameter
tables, and nib runtime attributes. They do **not** cover strings compiled into the Logic binary,
strings living inside nib object graphs, AppKit strings in the dyld shared cache, or the Help Book,
which Logic serves over the network rather than shipping.

So `absent` means *not in this corpus*, never *not in Logic*. Two consequences worth stating:

- an absence claim over English `strings` is the weakest proof the system can produce, because
  English lives in `Base.lproj` nibs rather than in `.strings` overlays — 97 of 135 tables that
  back a live match have no `en.lproj` file at all;
- the one live AXHelp value this repository cannot cite is most plausibly an AppKit string, and
  that plausibility is recorded as unverified rather than as a finding.

### Why the absence set is 32 bits

Proving presence needs one entry. Proving **absence** needs all of them, which is the expensive
direction and the one people skip — "I looked and it wasn't there" is not a proof anyone can re-run.

A 32-bit prefix collides, and the collision fails in the safe direction: it can make an absent
string look **present**, which refuses the absence claim and sends a person back to a machine with
Logic on it. It can never make a present string look absent, which would let a hand-typed string
masquerade as uncitable. The rate is in `MANIFEST.json` — worst case 1.2 × 10⁻⁵ — rather than left
for the reader to assume it is zero.

### Two ratchets over one population, measured

`docs/canon/WITHOUT-CANON.json` and `docs/observations/RATCHETS.json` overlap, and so do
`docs/canon/POLICY-LITERALS.json` and the ledger's `undocumented_variants`. The overlap is measured
rather than denied:

```
RATCHETS.schema_v1_records (schema < 2)   is a strict SUBSET of WITHOUT-CANON.json (schema < 3)
undocumented_variants ∩ POLICY-LITERALS `nowhere`   ≈ 30 of 42
```

They are kept apart because they answer different questions — *has this record caught up to the
current schema* versus *is this string in Logic's data* — and merging them would make one number
stand for two debts that close by different work. What this repository warns against is a second
copy of the truth, and the honest position is that this is close to one: shrinking either list does
not shrink the other, and nobody has yet written which shrinks first. That is a debt, and it is
recorded here rather than in nobody's head.

## Sighting and citation are not the same claim

A **sighting** is a row in a record: somebody saw this string on screen. A **citation** is a
reference into Logic's own data: Apple ships this string. Neither retires the other, and they can
disagree in both directions:

- a string can be in Logic's data and never reach the interface — measured: the live UI shows
  untranslated `German` and `MIDI Region` although ko translations for both keys exist;
- a string can reach the interface with no file behind it — measured: one live AXHelp value is in
  no file of the bundle.

Where they disagree, **neither wins automatically.** The rule is that the disagreement is recorded,
because a rule that picked a winner would have to pick it before anyone looked.

## Citing

```
logic-canon://<source>/<unit>/<locale>/<key>#<field>
```

```jsonc
"canon": [
  {"ref": "logic-canon://quickhelp/QuickHelp/ko/KCE_024_Record#composed",
   "value": "녹음 버튼. 선택한 트랙 또는 녹음 준비된 여러 트랙에 녹음합니다.",
   "used_for": "the key the AXHelp parser returns for the transport record button"}
]
```

```jsonc
"canon_absent": [
  {"claim": "the window zoom button's AXHelp has no canonical source",
   "strings": ["이 버튼을 누르면 윈도우를 확대/축소합니다."],
   "searched": [{"source": "quickhelp", "locale": "ko"}, {"source": "strings", "locale": "ko"}],
   "why_runtime": "an exhaustive byte scan of all 75,535 bundle files in three encodings found it nowhere; it is most likely drawn from AppKit inside the dyld shared cache, which is not a file this corpus can hold"}
]
```

## Where it is enforced

| | |
|---|---|
| files in the tree | `Scripts/check-canon-citations.py`, run by `run-repo-guards.py` in CI |
| a pull request body | the `canon-citations-in-the-pull-request` CI job, which reads the body |
| issue bodies | the issue templates require it; nothing checks an issue mechanically yet |

A pull request body is not a file, so the tree-wide sweep could not see it — and the two documents
a change is actually reviewed through were exempt from the rule they carry. That is the
named-site / enforcement-site gap in its usual shape, and it is why rule 11 exists.

### The opt-out

A body that asserts nothing about Logic writes this sentence, with the reason:

> states no fact about Logic

Deliberately a sentence rather than a checkbox, because a checkbox is ticked without reading — and
deliberately **not** printed in `.github/pull_request_template.md`, because the first version of
that template shipped it pre-typed and every untouched template passed. A sentence the template
types for you is a sentence nobody meant.

It is refused in two cases, both derived rather than declared:

- the change edits a **Logic-facing path** (`Sources/LogicProMCP/{Accessibility,HostParameters,Channels}/`,
  `docs/{observations,locale,canon}/`, `Scripts/livekit/`) — what a change says about itself does
  not decide whether it states a fact about Logic; what it touches does;
- the sentence appears only inside a fenced code block or an HTML comment. Text a reader does not
  see cannot carry a promise, and both hiding places were used against this check before it looked.

## The bindings — "was it actually used?"

A reference that resolves proves the quote is Apple's text. It does not prove anything in the
change rests on it, which is the other half of the requirement. So every citation declares where
the value lands, and the value must literally be there:

```jsonc
"binding": {"kind": "code", "path": "Sources/.../X.swift"}   // the file must contain it
"binding": {"kind": "record"}                                // this record must, outside `canon`
```

The first version of this had no bindings at all, and a citation could be decorative: correct
digest, correct quote, and no line of code or reading that had anything to do with it.

## The threat model, stated rather than implied

This is a **consistency** control, not a security control, and it cannot become one while its root
of trust is a file in the tree.

| adversary | what this stops |
|---|---|
| an honest author who errs | nearly everything: a misquoted value, an unpinned reference, a malformed one, a schema-2 record, an edited index, a truncated absence set, a literal Logic does not ship |
| an author routing around the rule | some of it. The opt-out is derived from the diff, the waiver lists are compared against the merge base, and the classification is committed — but a determined author has more room than an honest one |
| a committer acting in bad faith | **nothing.** `MANIFEST.json` digests the index and the absence sets, and `MANIFEST.json` is a tracked file. Whoever can edit one can edit all three in one commit. Review 2026-09-15 did exactly that in three edits and the gate stayed green. |
| a fork pull request | the most, since a fork cannot rewrite the guard on the base branch |

`verify_index_against_absence` raises the cost of the third case from a text edit to a deliberate
one — a forged row must also appear in a sorted binary absence set — and `.github/CODEOWNERS`
puts a human on `docs/canon/`. Neither makes it impossible, and nothing offline can.

What the gate actually proves is that **a quoted value matches a previously committed digest**. Only
`build`, on a machine with Logic, ever touches Apple's bytes. That is worth having: it makes the
class of error that produced `再生ヘッド位置` against `再生ヘッドの位置` impossible to commit by
accident. It is not a proof that Apple shipped the string.

## What this does **not** check

That a citation is the **right** one, and that a binding's occurrence is the one that matters.

A reference resolving with the right digest proves the quote is Apple's text under that key. It
does not prove that key describes the control the change is about. A binding proves the value is
in the file; a value sitting in a comment satisfies it. Closing that second gap needs the binding
to name a symbol AND the build to confirm the symbol carries the value — a different and much
heavier rule. `used_for` is required and is read by a person.

This is the same trust boundary `docs/observations/SCHEMA.md` already names for sightings, and
moving it would take a citation that says what the value is used *for* in a form a machine can
check against the code. That is worth building and is not built.

## Commands

```
Scripts/logic_canon.py build              # needs Logic. Re-pins everything.
Scripts/logic_canon.py status             # has the installed Logic drifted from the pin?
Scripts/logic_canon.py resolve <ref>      # what value does this reference name?
Scripts/logic_canon.py check <ref>=<val>  # does this quote hold, offline?
Scripts/logic_canon.py absent <src> <loc> <text>
Scripts/logic_canon.py axhelp             # reverse live AXHelp readings into keys, from stdin
Scripts/check-canon-citations.py          # the gate. Runs in CI.
```

## When Logic updates

`MANIFEST.json` pins a digest over every corpus byte. `logic_canon.py status` compares it to the
installed Logic and fails on drift. Rebuild, and every citation whose digest moved fails loudly —
which is the point: a citation that silently still "resolves" after Apple changed the string is
exactly the failure this axis exists to end.
