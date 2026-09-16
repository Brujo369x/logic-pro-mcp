import ApplicationServices
import Foundation

extension AccessibilityChannel {
    enum MarkerRenameWriteResult: Sendable, Equatable {
        case notAttempted(HonestContract.FailureError)
        case attempted

        var writeAttempted: Bool { self == .attempted }

        var failureError: HonestContract.FailureError? {
            guard case .notAttempted(let error) = self else { return nil }
            return error
        }
    }

    static func renameSelectedMarker(
        _ name: String,
        in window: AXUIElement,
        runtime: AXLogicProElements.Runtime
    ) async -> MarkerRenameWriteResult {
        let madeMain = AXHelpers.setAttribute(
            window,
            kAXMainAttribute,
            kCFBooleanTrue,
            runtime: runtime.ax
        )
        let raised = AXHelpers.performAction(window, kAXRaiseAction, runtime: runtime.ax)
        guard madeMain || raised else { return .notAttempted(.axWriteFailed) }
        usleep(100_000)

        guard let showControl = markerTextAreaToggle(in: window, runtime: runtime.ax) else {
            return .notAttempted(.axWriteFailed)
        }
        let showValue: NSNumber? = AXHelpers.getAttribute(
            showControl,
            kAXValueAttribute,
            runtime: runtime.ax
        )
        if showValue?.boolValue != true {
            guard AXHelpers.performAction(showControl, kAXPressAction, runtime: runtime.ax) else {
                return .notAttempted(.axWriteFailed)
            }
            usleep(100_000)
        }

        guard let editControl = markerEditControl(in: window, runtime: runtime.ax),
              AXHelpers.performAction(editControl, kAXPressAction, runtime: runtime.ax) else {
            return .notAttempted(.axWriteFailed)
        }
        usleep(100_000)

        let textAreas = AXHelpers.findAllDescendants(
            of: window,
            role: kAXTextAreaRole,
            maxDepth: 8,
            runtime: runtime.ax
        )
        guard let editor = textAreas.first,
              AXHelpers.setAttribute(
                editor,
                kAXFocusedAttribute,
                kCFBooleanTrue,
                runtime: runtime.ax
              ) else {
            return .notAttempted(.axWriteFailed)
        }
        usleep(50_000)
        let focused: NSNumber? = AXHelpers.getAttribute(
            editor,
            kAXFocusedAttribute,
            runtime: runtime.ax
        )
        guard focused?.boolValue == true else { return .notAttempted(.axWriteFailed) }

        if AXHelpers.setAttribute(
            editor,
            kAXValueAttribute,
            name as CFString,
            runtime: runtime.ax
        ) {
            _ = AXHelpers.performAction(editControl, kAXPressAction, runtime: runtime.ax)
            usleep(200_000)
            return .attempted
        }

        guard let windowTitle = AXHelpers.getTitle(window, runtime: runtime.ax) else {
            return .notAttempted(.axWriteFailed)
        }
        guard markerWindows(named: windowTitle, runtime: runtime).count == 1 else {
            return .notAttempted(.axWriteFailed)
        }
        let escapedName = AppleScriptSafety.escapeForScript(name)
        let escapedWindowTitle = AppleScriptSafety.escapeForScript(windowTitle)
        let target = LogicProTarget.appleScriptTarget()
        // #892: the marker group and its Edit button, resolved from AXLocalePolicy rather than
        // from an English `try` with a Korean `on error` fallback. That pair covered two of the
        // ten languages Logic ships, and it failed in a way worth naming: `first group ... whose
        // description is` RAISES -1719 when nothing matches, so on a German or Japanese Logic both
        // arms errored and the rename reported a write failure about a window that was open. The
        // English arm being first also means an ENGLISH Logic was the one that worked -- the
        // Korean fallback existed because somebody hit it, and nobody hit the other eight.
        let markerGroupResolution = AppleScriptMenuResolution.groupWithDescription(
            AXLocalePolicy.markerContainerKeywords,
            of: "markerWindow",
            variableName: "markerGroup",
            notFoundError: "MARKER_GROUP_NOT_FOUND"
        )
        let editButtonResolution = AppleScriptMenuResolution.candidateResolution(
            elementKeyword: "button",
            labelSet: AXLocalePolicy.markerListEditMenuButton,
            existsSuffix: " of markerGroup",
            variableName: "editButtonName",
            notFoundError: "MARKER_EDIT_BUTTON_NOT_FOUND"
        )
        let script = """
        tell application "System Events"
            tell \(target.systemEventsProcessTarget)
                set markerWindow to first window whose name is "\(escapedWindowTitle)"
                \(markerGroupResolution)
                \(editButtonResolution)
                set editButton to button editButtonName of markerGroup
                set editor to first text area of first scroll area of markerGroup
                if focused of editor is false then error "marker editor is not focused"
                keystroke "a" using command down
                keystroke "\(escapedName)"
                delay 0.1
                click editButton
            end tell
        end tell
        return "renamed"
        """
        let result = await runtime.executeAppleScript(script)
        if !result.isSuccess,
           HonestContract.stateCErrorCode(result.message)
            == HonestContract.FailureError.systemEventsAutomationDenied.rawValue {
            return .notAttempted(.systemEventsAutomationDenied)
        }
        usleep(200_000)
        return .attempted
    }

    private static func markerWindows(
        named title: String,
        runtime: AXLogicProElements.Runtime
    ) -> [AXUIElement] {
        guard let app = AXLogicProElements.appRoot(runtime: runtime) else { return [] }
        let windows: [AXUIElement] = AXHelpers.getAttribute(
            app,
            kAXWindowsAttribute,
            runtime: runtime.ax
        ) ?? []
        return windows.filter { AXHelpers.getTitle($0, runtime: runtime.ax) == title }
    }

    private static func markerTextAreaToggle(
        in window: AXUIElement,
        runtime: AXHelpers.Runtime
    ) -> AXUIElement? {
        AXHelpers.findAllDescendants(
            of: window,
            role: kAXCheckBoxRole,
            maxDepth: 8,
            runtime: runtime
        ).first {
            AXLocalePolicy.markerEditToggle.matches(
                AXHelpers.getDescription($0, runtime: runtime))
        }
    }

    private static func markerEditControl(
        in window: AXUIElement,
        runtime: AXHelpers.Runtime
    ) -> AXUIElement? {
        AXHelpers.findAllDescendants(
            of: window,
            role: kAXButtonRole,
            maxDepth: 8,
            runtime: runtime
        ).first {
            AXLocalePolicy.markerListEditMenuButton.matches(
                AXHelpers.getDescription($0, runtime: runtime))
        }
    }
}
