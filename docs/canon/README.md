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
  120   are a QuickHelp Title
  222   are somewhere in the bundle's 605,160 .strings entries
   37   are nowhere in Logic at all
```

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

### Why the absence set is 32 bits

Proving presence needs one entry. Proving **absence** needs all of them, which is the expensive
direction and the one people skip — "I looked and it wasn't there" is not a proof anyone can re-run.

A 32-bit prefix collides, and the collision fails in the safe direction: it can make an absent
string look **present**, which refuses the absence claim and sends a person back to a machine with
Logic on it. It can never make a present string look absent, which would let a hand-typed string
masquerade as uncitable. The rate is in `MANIFEST.json` — worst case 1.2 × 10⁻⁵ — rather than left
for the reader to assume it is zero.

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

## What this does **not** check

That a citation is the **right** one. A reference resolving with the right digest proves the quote
is Apple's text under that key. It does not prove that key describes the control the change is
about. `used_for` is required and is read by a person.

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
