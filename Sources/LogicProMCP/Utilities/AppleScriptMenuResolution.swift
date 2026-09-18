import Foundation

/// Generates the localized-menu candidate-resolution AppleScript snippet used by every
/// generated menu-bar/menu-item click site (#519).
///
/// `AXLocalePolicy` already carries every locale variant Logic's top-level menu titles and
/// menu items are known to use — for example `fileMenuBar` lists `"File"`, `"파일"`, AND
/// `"ファイル"` — but the AppleScript call sites that clicked through the File/Navigate/Edit
/// menus hard-coded only one or two of those names inline. The table looked like it supported
/// a locale (Japanese) that no call site could actually reach. Routing every menu-drive site
/// through this generator, instead of a hand-written literal, is what keeps that gap from
/// reopening: a variant added to `AXLocalePolicy` becomes reachable everywhere this helper is
/// used, with no call site to remember to update, and a future site that skips this helper and
/// writes a quoted literal name straight after the `menu bar item` keyword again is caught by
/// `Scripts/ci-forbid-hardcoded-menu-bar-item.sh` (registered in `.github/workflows/ci.yml` next
/// to the dead-`#expect` gate).
///
/// The generated script never assumes an index or a single name: it tries each label —
/// canonical first, then variants, in the order `LabelSet.labels` returns them — and uses the
/// first one AppleScript reports `exists`. A given running Logic only ever exposes ONE of a
/// LabelSet's labels (its actual UI language), so trying canonical before a locale variant does
/// not change which one an actual run picks; it only fixes the order candidates are probed in.
enum AppleScriptMenuResolution {
    /// Emits:
    /// ```applescript
    /// set <variableName> to missing value
    /// repeat with candidate in {"canonical", "variant1", ...}
    ///     if exists <elementKeyword> candidate<existsSuffix> then
    ///         set <variableName> to candidate as text
    ///         exit repeat
    ///     end if
    /// end repeat
    /// if <variableName> is missing value then error "<notFoundError>"
    /// ```
    ///
    /// `existsSuffix` is the AppleScript text that completes the `exists` specifier right after
    /// the bare `candidate` token — for example `" of menu bar 1"` for a top-level menu-bar
    /// item, or `" of menu 1 of menu bar item barName of menu bar 1"` for a submenu item nested
    /// under an already-resolved bar variable. `elementKeyword` is `"menu bar item"` or
    /// `"menu item"`, interpolated as plain AppleScript vocabulary — never followed directly by
    /// a quote, so this generator itself never trips the hard-coded-literal guard.
    ///
    /// Labels are escaped with `AppleScriptSafety.escapeForScript`, the same helper the rest of
    /// the AppleScript builders use, so a variant containing a `"` or `\` cannot break out of the
    /// `{...}` list literal.
    ///
    /// On failure the loop raises `error "<notFoundError>"` (an ordinary AppleScript error) —
    /// callers that already wrap the resolution in `try ... on error errMsg ... end try` catch it
    /// exactly like any other menu-not-found failure and keep their existing cleanup/Escape path.
    /// `notFoundError: nil` leaves the variable `missing value` for the caller to branch on.
    ///
    /// Raising is right where not finding the element means the operation cannot proceed. It is
    /// WRONG where the caller has a defined fallback: the go-to-position cleanup presses this
    /// dialog's localized Cancel and falls back to Escape only while the exact dialog is still
    /// observed open, so turning "no button matched" into an error would collapse a branch the
    /// operation depends on into the same `UNREADABLE` an AX failure produces.
    static func candidateResolution(
        elementKeyword: String,
        labelSet: AXLocalePolicy.LabelSet,
        existsSuffix: String,
        variableName: String,
        notFoundError: String?
    ) -> String {
        let literals = labelSet.labels
            .map { "\"\(AppleScriptSafety.escapeForScript($0))\"" }
            .joined(separator: ", ")
        let refusal = notFoundError.map {
            "\nif \(variableName) is missing value then error \"\($0)\""
        } ?? ""
        return """
        set \(variableName) to missing value
        repeat with candidate in {\(literals)}
            if exists \(elementKeyword) candidate\(existsSuffix) then
                set \(variableName) to candidate as text
                exit repeat
            end if
        end repeat\(refusal)
        """
    }

    /// Resolves a WINDOW by localized title suffix, in the order the LabelSet lists.
    ///
    /// Window titles are `"<project name> - <localized view name>"`, so this matches by
    /// `ends with` rather than by element name. The `try` around each attempt is load-bearing:
    /// `first window whose name ends with ...` raises `-1719` when nothing matches, which would
    /// abort the whole script instead of moving on to the next locale's suffix.
    ///
    /// This exists because the marker-menu script hard-coded an English and a Korean suffix as a
    /// `try`/`on error` pair. On a Japanese Logic both lookups failed, the script errored, and
    /// `create_marker` reported `Navigate > Create Marker was not found or could not be pressed` —
    /// a locale gap wearing the costume of a missing menu item. Measured live on 2026-08-17: the
    /// menu names were already resolved from a LabelSet; only the window lookup was not.
    static func windowWithTitleSuffix(
        _ labelSet: AXLocalePolicy.LabelSet,
        variableName: String,
        notFoundError: String
    ) -> String {
        let literals = labelSet.labels
            .map { "\"\(AppleScriptSafety.escapeForScript($0))\"" }
            .joined(separator: ", ")
        return """
        set \(variableName) to missing value
        repeat with candidate in {\(literals)}
            try
                set \(variableName) to first window whose name ends with candidate
                exit repeat
            end try
        end repeat
        if \(variableName) is missing value then error "\(notFoundError)"
        """
    }

    /// Resolves a GROUP by its localized `description`, in the order the LabelSet lists.
    ///
    /// `first group of <container> whose description is <x>` RAISES -1719 when nothing matches, so
    /// each attempt is wrapped in its own `try` -- exactly as `windowWithTitleSuffix` does, and for
    /// the same reason. Without it the first locale that does not match aborts the whole script
    /// instead of moving on to the next.
    ///
    /// The marker rename is why this exists. It hard-coded an English attempt with a Korean
    /// `on error` fallback, which is two of the ten languages Logic ships; a German or Japanese
    /// Logic raised in both arms and the operation reported a write failure about a window that
    /// was open.
    static func groupWithDescription(
        _ labelSet: AXLocalePolicy.LabelSet,
        of container: String,
        variableName: String,
        notFoundError: String
    ) -> String {
        let literals = labelSet.labels
            .map { "\"\(AppleScriptSafety.escapeForScript($0))\"" }
            .joined(separator: ", ")
        return """
        set \(variableName) to missing value
        repeat with candidate in {\(literals)}
            try
                set \(variableName) to first group of \(container) whose description is candidate
                exit repeat
            end try
        end repeat
        if \(variableName) is missing value then error "\(notFoundError)"
        """
    }

    /// Resolves a BUTTON by its localized `description`, in the order the LabelSet lists.
    ///
    /// The sibling of `groupWithDescription`, and it exists because the button beside that group
    /// was resolved the other way and could not be found at all.
    ///
    /// `candidateResolution(elementKeyword: "button", ...)` emits `exists button <name> of
    /// <container>`, which is a BY-NAME reference. That is right for a dialog's Cancel, whose
    /// title is the label -- it is what the go-to-position cleanup has always used and what works
    /// live. It is wrong for a Logic toolbar button, whose label is its AXDescription and whose
    /// AXTitle is empty.
    ///
    /// Measured on a running Logic 12.3 on 2026-09-18, through System Events: of 439 buttons in
    /// the arrange window, 412 report `name` as `missing value`, and none of the 27 that have a
    /// name carries an Edit-family label. Asked of one container both ways for the same button:
    ///
    ///     desc=바운스   exists button "바운스" of container            -> false
    ///                  exists (first button whose description is …)  -> true
    ///
    /// So the marker rename's Edit button must be found the way the marker GROUP above it is.
    /// Each attempt is wrapped in its own `try` for the same reason: `whose description is` raises
    /// -1719 when nothing matches, and without the `try` the first locale that does not match
    /// aborts the script instead of moving to the next.
    static func buttonWithDescription(
        _ labelSet: AXLocalePolicy.LabelSet,
        of container: String,
        variableName: String,
        notFoundError: String
    ) -> String {
        let literals = labelSet.labels
            .map { "\"\(AppleScriptSafety.escapeForScript($0))\"" }
            .joined(separator: ", ")
        return """
        set \(variableName) to missing value
        repeat with candidate in {\(literals)}
            try
                set \(variableName) to first button of \(container) whose description is candidate
                exit repeat
            end try
        end repeat
        if \(variableName) is missing value then error "\(notFoundError)"
        """
    }

    /// Tests an ALREADY-READ AppleScript text value against every label in a set.
    ///
    /// `if <text> contains "Bounce" or <text> contains "바운스"` is the shape this replaces, and
    /// it is the same two-language shape `windowWithTitleSuffix` and `groupWithDescription` were
    /// written for: a dialog that Logic opens under a localized title is invisible to a pair of
    /// literals in every other language Logic ships, and the operation reports the dialog missing
    /// rather than the language.
    ///
    /// Unlike the resolvers above this raises nothing and needs no `try`: `contains` on a text
    /// value cannot error, and the caller branches on the boolean.
    static func textContainsAny(
        _ labelSet: AXLocalePolicy.LabelSet,
        of textVariable: String,
        variableName: String
    ) -> String {
        let literals = labelSet.labels
            .map { "\"\(AppleScriptSafety.escapeForScript($0))\"" }
            .joined(separator: ", ")
        return """
        set \(variableName) to false
        repeat with candidate in {\(literals)}
            if \(textVariable) contains (candidate as text) then
                set \(variableName) to true
                exit repeat
            end if
        end repeat
        """
    }


    /// Convenience for a top-level menu-bar item: `menu bar item <name> of menu bar 1`.
    static func menuBarItem(
        _ labelSet: AXLocalePolicy.LabelSet,
        variableName: String,
        notFoundError: String
    ) -> String {
        candidateResolution(
            elementKeyword: "menu bar item",
            labelSet: labelSet,
            existsSuffix: " of menu bar 1",
            variableName: variableName,
            notFoundError: notFoundError
        )
    }

    /// Convenience for a menu item nested one level under an already-resolved parent
    /// specifier (a resolved `menu bar item` variable or a resolved `menu item` variable).
    /// `parentSpecifier` is the exact AppleScript specifier text the item lives under, e.g.
    /// `"menu bar item barName of menu bar 1"` or
    /// `"menu item goToName of menu 1 of menu bar item barName of menu bar 1"`.
    static func menuItem(
        _ labelSet: AXLocalePolicy.LabelSet,
        under parentSpecifier: String,
        variableName: String,
        notFoundError: String
    ) -> String {
        candidateResolution(
            elementKeyword: "menu item",
            labelSet: labelSet,
            existsSuffix: " of menu 1 of \(parentSpecifier)",
            variableName: variableName,
            notFoundError: notFoundError
        )
    }
}
