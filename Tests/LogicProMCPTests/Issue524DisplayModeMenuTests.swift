import Testing
@testable import LogicProMCP

/// `refuseTimeDisplayIfNeeded` resolved the position display mode from the **application** menu bar.
/// Measured live on Logic 12.3, that menu holds sixteen entries and none of them is the setting:
///
///     Library · Inspector · Mixer · Smart Controls · Editor · List Editors · Note Pads ·
///     Loop Browser · Browsers · Control Bar · Customize Control Bar and Display… · Toolbar ·
///     Customize Toolbar… · Movie Window · Colors · Enter Full Screen
///
/// It lives in the Event pane's own View menu, beside the column toggles:
///
///     Link · Relative Position · Event Position and Length as Time · Length as Absolute Position ·
///     SysEx in Hex Format · Locked ✓ · Muted ✓ · Position ✓ · Status ✓ · Channel ✓ · Number ✓ ·
///     Value ✓ · Articulation · Length/Info ✓ · Off · Same Level · Content ✓
///
/// So the search found zero matches and every `collect()` threw `displayModeUnavailable` before it
/// could return evidence. Nothing caught it: the collector is reachable from no dispatcher, and the
/// unit tests supply the mode through a seam rather than a live menu.
@Suite("#524 display mode is resolved from the pane's own View menu")
struct Issue524DisplayModeMenuTests {
    @Test("the setting is addressed by a locale policy entry, not an inline literal")
    func settingHasAPolicyEntry() {
        #expect(AXLocalePolicy.eventPositionAsTimeMenuItem.canonical
            == "Event Position and Length as Time")
        #expect(AXLocalePolicy.eventPositionAsTimeMenuItem.labels
            .contains("Event Position and Length as Time"))
    }

    @Test("no locale variant is INVENTED, which is not the same as none being claimed")
    func noInventedTranslation() {
        // This asserted `labels.count == 1` and said: the entry has not been read on a non-English
        // Logic, an English-only match fails closed, and "when it is measured, this expectation is
        // what has to be updated deliberately". This is that update, and the evidence is not a
        // reading -- it is Apple's own row (#892). Every label now comes from the `(unit, key)` in
        // `derivedFrom`, and `Scripts/check-labelsets-are-derived.py` requires, for each of the ten
        // locales the corpus carries, that one of these strings is the value pinned there.
        //
        // The property this case actually defends is unchanged: nothing here was translated by
        // hand. `derivedFrom` being present is what says so, and it is the thing to assert --
        // counting labels only ever measured how little had been done.
        #expect(AXLocalePolicy.eventPositionAsTimeMenuItem.derivedFrom != nil)
        #expect(AXLocalePolicy.eventPositionAsTimeMenuItem.labels.count > 1)
    }

    @Test("the pane's View menu is addressed by the same policy entry as the app menu")
    func viewMenuLabelIsShared() {
        // The pane's menu button and the application menu bar item both answer to "View", so one
        // policy entry serves both — what changed is WHERE it is looked for, not what it is called.
        #expect(AXLocalePolicy.viewMenuBar.labels.contains("View"))
        #expect(AXLocalePolicy.viewMenuBar.labels.contains("보기"))
    }
}
