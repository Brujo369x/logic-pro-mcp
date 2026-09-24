import ApplicationServices
import Foundation

/// Read-only census of a named plug-in across the Mixer, plus the AX identity
/// each open editor window advertises (#972). Built for hosts that want to find
/// their OWN instances: an AUv3 view sets `kAXIdentifier` on its root
/// (`<prefix><instance-id>`), and this read walks each editor window for it.
///
/// Composes the existing readers only: `getMixerArea` / `stripEnumeration`
/// (ordinal strips, read whole or partial), `audioPluginInsertSlots` (physical
/// slot positions preserved), `trackNames` (arrange headers) and
/// `pluginEditorWindows` (fully classified editors). Nothing here actuates and
/// no `AXUIElement` escapes: the snapshot is value data.
///
/// Three states a caller can tell apart, because they mean different things:
///  * EMPTY: `census` returns a snapshot with no strips and no windows and a
///    `diagnostics.note` saying why (`mixer-not-found`, `no-hosting-strips`, …).
///  * PARTIAL: `stripsReadWhole == false`; strips are listed but ordinals must
///    not be trusted, a child of the Mixer refused its role read.
///  * FAILED: the editor-window enumeration answered an AX error; `census`
///    THROWS `CensusError.windowsReadFailed` carrying the status and whatever
///    strips were read. A failed read is never reported as zero windows.
///
/// Measured on Logic Pro 12.3.1 (6682), en-US, and stated rather than papered
/// over: the editor window's AX title is the TRACK name, so a window is joined
/// to a strip by name and duplicate names are the caller's ambiguity to refuse;
/// Logic labels an occupied insert slot with the AU component name truncated
/// (~10 characters), so slot matching is prefix-tolerant; the Mixer strips are
/// reachable through `getMixerArea` when the Mixer is docked in the main window.
public enum AXPluginInstanceIdentity {

    /// One Mixer strip carrying at least one insert whose display name matches.
    public struct Strip: Sendable, Equatable {
        /// Ordinal in the Mixer's strip enumeration (0-based). Meaningful only
        /// when the snapshot's `stripsReadWhole` is true.
        public let ordinal: Int
        /// The strip's readable name, if any (AXTextField / title metadata).
        public let name: String?
        /// Physical insert positions whose display name matched.
        public let insertSlots: [Int]
    }

    /// One open plug-in editor window and the identity found inside it.
    public struct Window: Sendable, Equatable {
        /// The window's AX title (measured: the track name).
        public let title: String
        /// The first descendant `kAXIdentifier` beginning with the prefix, or nil.
        public let identifier: String?
    }

    /// What WAS observed, so an empty snapshot can never be silent about its
    /// cause. Counts and flags only; no names.
    public struct Diagnostics: Sendable, Equatable {
        public let logicPID: Int
        /// The raw `AXWindows` count on the application element, nil when that
        /// read did not succeed.
        public let axWindowCount: Int?
        public let mainWindowFound: Bool
        public let mixerFound: Bool
        /// The app-level windows read answered `kAXErrorCannotComplete` once and
        /// was re-read after 200 ms (the #608 rule: once, and only for that status).
        public let windowsReadRetried: Bool
        /// Why the snapshot is empty when it is: `main-window-nil`,
        /// `mixer-not-found`, `no-hosting-strips`. Nil when something was found.
        public let note: String?
    }

    public struct AXSnapshot: Sendable, Equatable {
        public let strips: [Strip]
        /// Whether the strip list was read WHOLE (no Mixer child refused its role).
        public let stripsReadWhole: Bool
        public let windows: [Window]
        /// Arrange track headers by 0-based index, when every header read.
        public let trackNames: [Int: String]?
        public let diagnostics: Diagnostics
    }

    public enum CensusError: Error, Sendable, Equatable {
        /// No Logic Pro process; nothing was read.
        case logicNotRunning
        /// The editor-window enumeration answered an AX error. `status` is the
        /// raw `AXError`; `strips` and `stripsReadWhole` are what the Mixer read
        /// returned before the failure, so a caller keeps the half it has.
        case windowsReadFailed(status: Int32, strips: [Strip], stripsReadWhole: Bool,
                               diagnostics: Diagnostics)
    }

    /// Does an insert slot's display name denote `pluginName`? Logic labels an
    /// occupied slot with the Audio Unit's component name TRUNCATED to about ten
    /// characters (measured on 12.3.1: an AU named "SN8KExtension" reads
    /// "SN8KExtens"), so an exact match is wrong in both directions: the label
    /// may be a prefix of the name, or the name a prefix of the label. Both
    /// sides are trimmed and lowercased; a prefix match needs at least 4 characters.
    static func slotNameMatches(_ slotName: String?, pluginName wanted: String) -> Bool {
        let a = (slotName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let b = wanted.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard a.count >= 4, b.count >= 4 else { return a == b && !a.isEmpty }
        return a == b || a.hasPrefix(b) || b.hasPrefix(a)
    }

    /// Enumerate strips hosting `pluginName` and the identity each open editor
    /// window exposes under `identifierPrefix`.
    /// - Parameters:
    ///   - pluginName: the insert display name to match (case-insensitive, trimmed, prefix-tolerant).
    ///   - identifierPrefix: the `kAXIdentifier` prefix the plug-in's view root sets.
    ///   - maxDepth: window walk depth for the identifier search.
    /// - Throws: `CensusError.logicNotRunning`; `CensusError.windowsReadFailed`
    ///   when the editor-window read itself failed (never surfaced as empty).
    public static func census(
        pluginName: String,
        identifierPrefix: String,
        maxDepth: Int = 12
    ) throws -> AXSnapshot {
        try census(pluginName: pluginName, identifierPrefix: identifierPrefix,
                   maxDepth: maxDepth, runtime: .production)
    }

    /// Runtime-injected variant (the module's test seam; `Runtime` is internal).
    static func census(
        pluginName: String,
        identifierPrefix: String,
        maxDepth: Int,
        runtime: AXLogicProElements.Runtime
    ) throws -> AXSnapshot {
        guard let pid = runtime.logicProPID() else { throw CensusError.logicNotRunning }
        let appRoot = AXLogicProElements.appRoot(runtime: runtime)

        // #608 measured: the FIRST windows read in a fresh process can answer
        // kAXErrorCannotComplete (-25204), the AX messaging did not go through,
        // and the same read succeeds milliseconds later. A failed read is not an
        // observation: re-read once, only for that status, never a read that
        // succeeded (whatever it said).
        var windowsReadRetried = false
        var axWindowCount: Int?
        if let appRoot {
            var read: Result<[AXUIElement]?, AXHelpers.AXStatusError> =
                AXHelpers.getAttributeResult(appRoot, kAXWindowsAttribute as String, runtime: runtime.ax)
            if case let .failure(error) = read, error.raw == AXError.cannotComplete.rawValue {
                usleep(200_000)
                windowsReadRetried = true
                read = AXHelpers.getAttributeResult(appRoot, kAXWindowsAttribute as String, runtime: runtime.ax)
            }
            if case let .success(windows) = read { axWindowCount = windows?.count }
        }
        let mainWindowFound = AXLogicProElements.mainWindow(runtime: runtime) != nil
        let mixer = AXLogicProElements.getMixerArea(runtime: runtime)

        var strips: [Strip] = []
        var readWhole = false
        if let mixer {
            let enumeration = AXLogicProElements.stripEnumeration(in: mixer, runtime: runtime.ax)
            readWhole = enumeration.unreadableChildren == 0
            for (index, strip) in enumeration.strips.enumerated() {
                let slots = AXLogicProElements.audioPluginInsertSlots(in: strip, runtime: runtime.ax)
                let hits = slots.filter { slotNameMatches($0.name, pluginName: pluginName) }.map(\.index)
                guard !hits.isEmpty else { continue }
                strips.append(Strip(ordinal: index, name: stripName(strip, runtime: runtime.ax), insertSlots: hits))
            }
        }

        func diagnostics(note: String?) -> Diagnostics {
            Diagnostics(logicPID: Int(pid), axWindowCount: axWindowCount,
                        mainWindowFound: mainWindowFound, mixerFound: mixer != nil,
                        windowsReadRetried: windowsReadRetried, note: note)
        }

        let editors: [AXUIElement]
        switch AXLogicProElements.pluginEditorWindows(runtime: runtime) {
        case let .success(found):
            editors = found
        case let .failure(error):
            // FAILED is not EMPTY: the caller gets the status and what was read.
            throw CensusError.windowsReadFailed(status: error.raw, strips: strips,
                                                stripsReadWhole: readWhole,
                                                diagnostics: diagnostics(note: "windows-read-failed"))
        }
        let windows = editors.map { window in
            Window(title: (AXHelpers.getTitle(window, runtime: runtime.ax) ?? "")
                        .trimmingCharacters(in: .whitespacesAndNewlines),
                   identifier: firstIdentifier(in: window, prefix: identifierPrefix,
                                               maxDepth: maxDepth, runtime: runtime.ax))
        }

        let note: String?
        if !strips.isEmpty || !windows.isEmpty {
            note = nil
        } else if appRoot == nil {
            note = "app-root-nil"
        } else if !mainWindowFound {
            note = "main-window-nil"
        } else if mixer == nil {
            note = "mixer-not-found"
        } else {
            note = "no-hosting-strips"
        }
        return AXSnapshot(strips: strips, stripsReadWhole: readWhole, windows: windows,
                          trackNames: AXLogicProElements.trackNames(runtime: runtime),
                          diagnostics: diagnostics(note: note))
    }

    /// A strip's readable name: the text field (or, failing that, static text)
    /// whose value is non-empty and is not a numeric level readout. The lookup
    /// is a census, not a first match: every candidate of the role is counted,
    /// and the name is returned only when the name-like readings agree on ONE
    /// string. Two distinct readings are an ambiguity a read-only census must
    /// not settle by tree order, so the strip keeps its ordinal (nil) and the
    /// join stays honest. Measured 12.3.1 docked Mixer: one name field per
    /// strip, the level and pan readouts are numeric static texts.
    static func stripName(_ strip: AXUIElement, runtime: AXHelpers.Runtime) -> String? {
        for role in [kAXTextFieldRole as String, kAXStaticTextRole as String] {
            let census = AXHelpers.censusDescendant(of: strip, role: role, maxDepth: 3, runtime: runtime)
            var readings: [String] = []
            for element in census.matches {
                guard let text = AXValueExtractors.extractTextValue(element, runtime: runtime)?
                        .trimmingCharacters(in: .whitespacesAndNewlines),
                      !text.isEmpty, Double(text) == nil, !readings.contains(text) else { continue }
                readings.append(text)
            }
            if readings.count == 1 { return readings[0] }
            if readings.count > 1 { return nil }
        }
        let title = AXHelpers.getTitle(strip, runtime: runtime)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (title?.isEmpty ?? true) ? nil : title
    }

    /// Depth-first search for the first descendant whose `kAXIdentifier` starts
    /// with `prefix`. Remote (out-of-process) view content is walked like any
    /// other subtree; an AX refusal at any node ends that branch, not the search.
    static func firstIdentifier(in root: AXUIElement, prefix: String, maxDepth: Int,
                                runtime: AXHelpers.Runtime) -> String? {
        guard maxDepth > 0 else { return nil }
        for child in AXHelpers.getChildren(root, runtime: runtime) {
            if let id = AXHelpers.getIdentifier(child, runtime: runtime), id.hasPrefix(prefix) {
                return id
            }
            if let found = firstIdentifier(in: child, prefix: prefix, maxDepth: maxDepth - 1, runtime: runtime) {
                return found
            }
        }
        return nil
    }
}
