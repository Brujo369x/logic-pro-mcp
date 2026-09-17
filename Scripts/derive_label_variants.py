#!/usr/bin/env python3
"""Read a LabelSet's ten languages off Apple's own bytes instead of measuring them one at a time.

A `LabelSet` in `AXLocalePolicy.swift` carries one string per language somebody read off a running
Logic. Ten locales therefore cost ten machines running Logic in ten languages, and six of the ten
have never been read at all -- which is #892. Apple ships the whole mapping: a `.strings` row is
one control's text in every locale at once, so the ten languages are a LOOKUP rather than ten
measurements.

The hard part is choosing the row, because a value does not choose one. `off` is the English value
of ten different rows and they disagree in Chinese (`关闭` against `关`). Two things narrow it, in
this order, and neither is a judgement:

1. The LabelSet's members are a JOINT constraint. `off` AND `끔` AND `オフ` is a much smaller set
   than any of them alone -- measured over all 159 LabelSets, intersecting takes 26 resolutions to
   67.
2. Apple's key namespace. `Localizable.strings` keys are not opaque: `#mti` is a menu title, `#acc`
   an accessibility name, `StrTransportBtns|||` a transport control, `StrToolbItemName|||` a
   toolbar item -- and every key in all four carries all ten locales. Restricting candidates to the
   namespace a label belongs to takes 67 to 112 of 159.

`fileMenuBar` is why this is not a guess. Its German variant `Ablage` was read off a running Logic;
of the two rows whose English is `File`, only `File#mti` says `Ablage` and the other says `Datei`.
Apple's namespace and this repository's own measurement pick the same row without consulting each
other.

    Scripts/derive_label_variants.py                 every LabelSet, with its verdict
    Scripts/derive_label_variants.py <name> ...      just these
    Scripts/derive_label_variants.py --json          machine-readable, for the migration
    Scripts/derive_label_variants.py --swift <name>  the variants list, ready to paste

Needs Logic: it reads the bundle. The GUARD that checks a migrated LabelSet needs nothing, because
`logic_canon.py build` pins the row's ten digests into `docs/canon/index/`.
"""
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "/Applications/Logic Pro.app"
UI_LABELS = os.path.join(REPO, "docs", "locale", "ui-labels.json")

#: The ten locale names Logic ships, in the corpus's own spelling.
LOCALES = ("en", "ko", "ja", "de", "es", "fr", "it", "pt", "zh_CN", "zh_TW")

#: Apple's semantic key namespaces, most specific first. Each is a RULE about what a key means, and
#: the counts are measured against Logic 12.3 (6674): every key in each carries all ten locales, so
#: a label that belongs to one of them is answered completely or not at all.
#:
#: Order matters where a label could sit in two. A menu title is a menu title before it is an
#: accessibility name, which is why `#mti` is first -- `View` is both, and the menu bar is what
#: `viewMenuBar` matches.
NAMESPACES = (
    ("#mti", lambda key: key.endswith("#mti")),                        # 48 keys, menu titles
    ("#acc", lambda key: key.endswith("#acc")),                        # 60 keys, accessibility names
    ("StrTransportBtns", lambda key: key.startswith("StrTransportBtns|||")),   # 44 keys
    ("StrToolbItemName", lambda key: key.startswith("StrToolbItemName|||")),   # 62 keys
    ("StrToolbTooltip", lambda key: key.startswith("StrToolbTooltip|||")),
    ("StrViewBtns", lambda key: key.startswith("StrViewBtns|||")),
    ("StrTabBtnLabel", lambda key: key.startswith("StrTabBtnLabel|||")),
    ("#key", lambda key: key.endswith("#key")),
    ("#par", lambda key: key.endswith("#par")),
    ("#und", lambda key: key.endswith("#und")),
)


def _canon():
    spec = importlib.util.spec_from_file_location(
        "logic_canon_for_derivation", os.path.join(REPO, "Scripts", "logic_canon.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def corpus_rows(canon, app=APP):
    """{(unit, key): {locale: value}} over `strings` and `nibstrings`, which share one namespace.

    Both, not `strings` alone: Apple compiles the English of 162 tables into `Base.lproj` nibs and
    ships no `en.lproj` overlay for any of them (#895). A derivation over `strings` alone would
    have no English for those tables and would reject every row in them for being incomplete.
    """
    rows: dict = {}
    for source, extract in (("strings", canon.extract_strings),
                            ("nibstrings", canon.extract_nibstrings)):
        for unit, locale, key, field, value in extract(app):
            if field == "value":
                rows.setdefault((unit, key), {})[locale] = value
                _SOURCE_OF[(unit, key, locale)] = source
    return rows


#: Which source holds a given (unit, key, locale). One ROW can span two of them: Apple compiles the
#: English of 162 tables into `Base.lproj` nibs and ships the nine translations as `.strings`, so
#: `GotoPosition.strings 5.title` is `nibstrings` in English and `strings` in every other language.
#: A `logic-canon://` reference names ONE source, so it has to name the one that holds the locale it
#: cites -- writing `strings` for all of them left eight references unresolvable, and unresolvable
#: reads offline as "typed and never checked".
_SOURCE_OF: dict = {}


def by_value(canon, rows):
    index: dict = {}
    for row, values in rows.items():
        for value in values.values():
            index.setdefault(canon.normalize(value), set()).add(row)
    return index


def _signature(canon, rows, row):
    return tuple(canon.normalize(rows[row][locale]) for locale in LOCALES)


def derive(canon, rows, index, members):
    """(verdict, row, namespace, candidates) for one LabelSet's members.

    `verdict` is one of `value`, `namespace`, `ambiguous`, `no-row`, `no-complete-row`. The row is
    returned only when one answer survives, and "one answer" means one SIGNATURE rather than one
    key: ten keys that say the same thing in all ten languages are not an ambiguity, and treating
    them as one was the difference between 26 resolutions and 42.
    """
    sets = [index.get(canon.normalize(member), set()) for member in members if member]
    sets = [found for found in sets if found]
    if not sets:
        return ("no-row", None, None, [])
    intersection = set.intersection(*sets) if len(sets) > 1 else sets[0]
    candidates = intersection or set.union(*sets)
    complete = sorted(row for row in candidates
                      if all(locale in rows[row] for locale in LOCALES))
    if not complete:
        return ("no-complete-row", None, None, sorted(candidates))
    # Namespace FIRST, even when the bare value is already unambiguous. A citation names a row, and
    # the row has to mean the thing. `trackMenuBar` resolved by value to a ControllerAssignments
    # dialog label: ten candidates all said `Spur` / `Pista` / `轨道`, so the ANSWER was right and
    # the row was a control-assignments field rather than the Track menu. `used_for` would have had
    # to defend a citation nobody could defend. `Track#mti` is the same answer from the right row.
    for name, belongs in NAMESPACES:
        narrowed = [row for row in complete if belongs(row[1])]
        if narrowed and len({_signature(canon, rows, row) for row in narrowed}) == 1:
            return ("namespace", narrowed[0], name, complete)
    if len({_signature(canon, rows, row) for row in complete}) == 1:
        return ("value", complete[0], None, complete)
    return ("ambiguous", None, None, complete)


#: Why a LabelSet with a row may still not be applied automatically.
SAFE = "safe"                       # the row already holds every string this label carries
EXTRA_MEMBERS = "extra-members"     # the label carries something the row does not


def applicability(canon, rows, row, members):
    """(verdict, the members the row does not hold).

    Derivation is pure ADDITION when the row already holds every string the label carries: nothing
    can be lost and no judgement is involved. When it does not, the extra member is either the
    tolerance `variants` exists for -- a lowercase fragment matched by containment, which is not the
    value of anything -- or a sign the row is wrong, or a sign the label is compound and no single
    row can cover it. `pluginOpenOrListControl` matches `open` AND `list`; `nonInsertButtonText`
    carries 25 members spanning a dozen controls. Telling those three apart is a reading, so this
    reports them instead of guessing.
    """
    # Case-FOLDED, the same way the applier dedupes and the guard checks, because that is the
    # question the product asks: every `LabelSet.matches` mode is case-insensitive. Comparing
    # case-exactly called the lowercase containment fragments `marker`, `bus` and `audio` members
    # their row does not hold, when the row holds `Marker`, `Bus` and `Audio` and the product
    # cannot tell those apart. The corpus stays case-exact; this question is not the corpus's.
    held = {canon.normalize(rows[row][locale]).casefold() for locale in LOCALES}
    extra = [member for member in members
             if canon.normalize(member).casefold() not in held]
    return (SAFE if not extra else EXTRA_MEMBERS), extra


def compose(rows, template_row, noun_row, locales=LOCALES):
    """The strings Logic BUILDS at runtime from a `%@` template and a noun, per locale.

    Apple ships `Show %@` and `Hide %@` as templates, so `Show Library` is not a string that exists
    anywhere -- it is assembled. Measured on a Korean Logic 12.3 on 2026-09-18: the View menu reads
    `\uB77C\uC774\uBE0C\uB7EC\uB9AC \uAC00\uB9AC\uAE30`, which is the Hide template with the
    Library noun in it, and no literal list could have produced the Traditional Chinese form with
    its corner brackets.

    Returned in locale order with duplicates dropped, which is the shape a LabelSet wants.
    """
    out = []
    for locale in locales:
        value = rows[template_row][locale].replace("%@", rows[noun_row][locale])
        if value not in out:
            out.append(value)
    return out


def load_labels():
    with open(UI_LABELS, encoding="utf-8") as handle:
        return json.load(handle)["labels"]


def members_of(entry):
    return [text for text in [entry.get("canonical")] + list(entry.get("variants") or []) if text]


def _report(canon, rows, index, labels, wanted):
    out = {}
    for name in sorted(labels) if not wanted else wanted:
        entry = labels.get(name)
        if entry is None:
            print(f"{name}: not a LabelSet in {os.path.relpath(UI_LABELS, REPO)}", file=sys.stderr)
            continue
        verdict, row, namespace, candidates = derive(canon, rows, index, members_of(entry))
        record = {"verdict": verdict, "candidates": len(candidates)}
        if row is not None:
            record["unit"], record["key"] = row
            record["namespace"] = namespace
            record["values"] = {locale: rows[row][locale] for locale in LOCALES}
            record["ref"] = canon.citation_for(
                _SOURCE_OF.get((row[0], row[1], "en"), "strings"), row[0], "en", row[1], "value")
            applied, extra = applicability(canon, rows, row, members_of(entry))
            record["applicability"] = applied
            if extra:
                record["members_the_row_does_not_hold"] = extra
        out[name] = record
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    swift = "--swift" in argv
    compose_pair = None
    if "--compose" in argv:
        rest = [a for a in argv[argv.index("--compose") + 1:]]
        if len(rest) < 2:
            print("usage: --compose <template-key> <noun-key>", file=sys.stderr)
            return 2
        compose_pair = (rest[0], rest[1])
    wanted = [] if compose_pair else [arg for arg in argv if not arg.startswith("--")]
    if not os.path.isdir(APP):
        print(f"{APP} is not installed. This tool reads Apple's bytes; there is no offline "
              f"substitute for extracting them, and inventing one would be the failure this whole "
              f"axis exists to stop.", file=sys.stderr)
        return 2
    canon = _canon()
    rows = corpus_rows(canon)
    index = by_value(canon, rows)
    if compose_pair:
        template_key, noun_key = compose_pair
        def one(key):
            hits = [k for k in rows if k[1] == key and all(l in rows[k] for l in LOCALES)]
            if len(hits) != 1:
                print(f"{key!r} resolves to {len(hits)} row(s) carrying all ten locales; "
                      f"composition needs exactly one", file=sys.stderr)
                raise SystemExit(2)
            return hits[0]
        template, noun = one(template_key), one(noun_key)
        for value in compose(rows, template, noun):
            print(value)
        print(f"# template {template[0]} {template[1]}", file=sys.stderr)
        print(f"# noun     {noun[0]} {noun[1]}", file=sys.stderr)
        return 0
    labels = load_labels()
    report = _report(canon, rows, index, labels, wanted)
    if as_json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if swift:
        for name, record in report.items():
            if "values" not in record:
                print(f"// {name}: {record['verdict']}", file=sys.stderr)
                continue
            values = record["values"]
            rest = [values[locale] for locale in LOCALES if locale != "en"]
            seen, ordered = set(), []
            for text in rest:
                if text not in seen and text != values["en"]:
                    seen.add(text)
                    ordered.append(text)
            print(f"// {name} <- {record['ref']}")
            print("        variants: [" + ", ".join(f'"{t}"' for t in ordered) + "],")
        return 0
    tally: dict = {}
    for name, record in sorted(report.items()):
        tally[record["verdict"]] = tally.get(record["verdict"], 0) + 1
        where = (f"{record['unit'].split('/')[-1]} {record['key']}"
                 if "key" in record else f"{record['candidates']} candidate(s)")
        namespace = f" via {record['namespace']}" if record.get("namespace") else ""
        print(f"  {record['verdict']:16} {name:36} {where}{namespace}")
    print()
    for verdict, count in sorted(tally.items(), key=lambda pair: -pair[1]):
        print(f"  {count:4}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
