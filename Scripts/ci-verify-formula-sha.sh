#!/usr/bin/env bash
# The Formula's sha256 must be the hash of the release its own version names.
#
# #775: v3.15.0 shipped with the v3.14.0 hash still in the Formula, so every `brew install
# logic-pro-mcp` failed on the install path the README documents. `version` and `sha256` are one
# edit and only one of them was mechanically required — `Scripts/release-verify-formula-install-
# paths.sh` verifies this same file, but it checks the install PATHS and never looks at the hash.
#
# This is a CI step rather than a `check-*.py` on purpose. `run-repo-guards.py` states its contract
# as "plain Python needing neither Xcode nor a network", and the only way to know a hash is right is
# to ask the release what it published. So the network lives here, where CI already has it.
#
# Usage:
#   ci-verify-formula-sha.sh                       # fetch the named release from GitHub
#   ci-verify-formula-sha.sh <SHA256SUMS.txt>      # compare against a local file (used by the test)
#
# `LPM_GH_BIN` overrides the `gh` binary, `LPM_FORMULA_RETRY_DELAY` the pause between retries, and
# `LPM_FORMULA_RELEASE_PREPARATION=1` declares a run that is preparing a release; the self-test uses
# all three.
#
# `LPM_FORMULA_PATH` overrides which Formula is read; the self-test uses it.
#
# Exit 0 clean, 1 on mismatch or on any state where the answer could not be established, 2 if the
# Formula could not be parsed.
#
# WHAT WAS WRONG HERE
# -------------------
# The lookup was `if ! gh release view "v$VERSION"; then ... exit 0`, which classified EVERY failure
# of that command as "not published yet". An expired token, a 403, a rate limit, a DNS failure, a
# 502 -- each one printed "this check becomes meaningful once the release exists" and exited 0. The
# comment above it claimed fail-closed; the code was the opposite, and the one state it was written
# for (a release-prep version bump) is indistinguishable from every state it was not.
#
# So the release is now looked up through `gh api -i`, and the decision is made on the HTTP STATUS
# rather than on a human sentence:
#
#   200                       compare the hashes
#   404, ordinary run         FAIL -- the Formula names a release that is not there
#   404, release preparation  NOT APPLICABLE (exit 0), only when asked for explicitly
#   401 403 429               FAIL -- could not ask, which is not an answer
#   5xx, or no status at all  FAIL after a short bounded retry
#
# Release preparation is `LPM_FORMULA_RELEASE_PREPARATION=1`, and it has to be set by the caller
# that knows it is preparing a release. It is deliberately NOT the default: a 404 on an ordinary
# build means the committed Formula points at a release nobody published, which is the state that
# makes `brew install` fail.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# A named test seam rather than an argument, so the two things a caller passes stay "which sums" and
# nothing else. The self-test needs to point the rule at a Formula it wrote, and a guard that cannot
# be aimed at a fixture cannot be shown to fail.
FORMULA="${LPM_FORMULA_PATH:-$ROOT/Formula/logic-pro-mcp.rb}"
ASSET="LogicProMCP-macOS-universal.tar.gz"
LOCAL_SUMS="${1:-}"

[ -f "$FORMULA" ] || { echo "no Formula at $FORMULA"; exit 2; }

VERSION=$(grep -m1 -E '^[[:space:]]*version[[:space:]]+"' "$FORMULA" | sed -E 's/.*"([^"]+)".*/\1/')

# One artifact, one hash. Today the Formula ships a single universal tarball, and reading only the
# first `sha256` would be exactly right and would go on looking right if someone added an arm64
# block underneath — the second hash would never be compared to anything, silently, which is the
# same shape as the defect this guard exists for. Refuse instead of checking half.
SHA_LINES=$(grep -cE '^[[:space:]]*sha256[[:space:]]+"' "$FORMULA")
if [ "$SHA_LINES" -gt 1 ]; then
  echo "the Formula carries $SHA_LINES sha256 lines; this rule only understands one artifact."
  echo "Teach it which url each hash belongs to before adding another, or it will check one and"
  echo "ignore the rest."
  exit 2
fi

PINNED=$(grep -m1 -E '^[[:space:]]*sha256[[:space:]]+"' "$FORMULA" | sed -E 's/.*"([0-9a-f]{64})".*/\1/')

[ -n "$VERSION" ] || { echo "could not read version from the Formula"; exit 2; }
printf '%s' "$PINNED" | grep -qE '^[0-9a-f]{64}$' || { echo "could not read a sha256 from the Formula"; exit 2; }

if [ -n "$LOCAL_SUMS" ]; then
  [ -f "$LOCAL_SUMS" ] || { echo "no such sums file: $LOCAL_SUMS"; exit 2; }
  SUMS=$(cat "$LOCAL_SUMS")
else
  # A named seam so the classification below can be driven by a fake `gh` that prints a chosen
  # status. Without it the only way to test a 403 is to have one.
  GH="${LPM_GH_BIN:-gh}"
  command -v "$GH" >/dev/null 2>&1 || { echo "gh is not available, so the Formula's hash could not be checked"; exit 1; }
  SLUG="${GITHUB_REPOSITORY:-MongLong0214/logic-pro-mcp}"
  RETRY_DELAY="${LPM_FORMULA_RETRY_DELAY:-2}"

  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT

  # Bounded, and only for the states that are actually transient. An auth failure retried three
  # times is an auth failure; a retry loop over it only delays the same answer.
  STATUS=""
  for attempt in 1 2 3; do
    RESP=$("$GH" api "repos/$SLUG/releases/tags/v$VERSION" -i 2>"$TMP/gh-err") || true
    STATUS=$(printf '%s\n' "$RESP" | head -1 | awk '{print $2}')
    case "$STATUS" in
      5??|"")
        if [ "$attempt" -lt 3 ]; then sleep "$RETRY_DELAY"; continue; fi ;;
    esac
    break
  done

  case "$STATUS" in
    200)
      : ;;
    404)
      if [ "${LPM_FORMULA_RELEASE_PREPARATION:-0}" = "1" ]; then
        echo "NOT APPLICABLE: v$VERSION is not published and this run declared itself a release"
        echo "preparation. Nothing was compared. This is NOT confirmation that the pinned hash is"
        echo "right -- the candidate tarball's own hash is what proves that, before publication."
        exit 0
      fi
      echo "v$VERSION has no published release (HTTP 404), and the committed Formula points at it."
      echo "brew install fails for everyone in this state. Either the release was never published,"
      echo "or the Formula was bumped ahead of it -- if this run IS preparing a release, say so with"
      echo "LPM_FORMULA_RELEASE_PREPARATION=1 rather than letting every run treat 404 as fine."
      exit 1 ;;
    401|403|429)
      echo "the release lookup answered HTTP $STATUS, so the Formula's hash could not be checked."
      echo "That is a failure, not a pass: 'could not ask' and 'the answer was yes' are the same"
      echo "exit code only if this rule lets them be."
      sed -n '1,5p' "$TMP/gh-err" 2>/dev/null
      exit 1 ;;
    5??)
      echo "the release lookup answered HTTP $STATUS on all 3 attempts, so nothing was checked."
      echo "A server failure is a failure to ask, and this rule does not read that as an answer."
      sed -n '1,5p' "$TMP/gh-err" 2>/dev/null
      exit 1 ;;
    "")
      echo "the release lookup returned no HTTP status after 3 attempts, so nothing was checked."
      sed -n '1,5p' "$TMP/gh-err" 2>/dev/null
      exit 1 ;;
    *)
      echo "the release lookup answered HTTP $STATUS, which this rule does not read as an answer."
      sed -n '1,5p' "$TMP/gh-err" 2>/dev/null
      exit 1 ;;
  esac

  if ! "$GH" release download "v$VERSION" -p 'SHA256SUMS.txt' -O "$TMP/sums.txt" --clobber >/dev/null 2>&1; then
    echo "v$VERSION exists but its SHA256SUMS.txt could not be downloaded, so the Formula's hash"
    echo "could not be checked. That is a failure rather than a pass: the release is there and the"
    echo "check could not be made."
    exit 1
  fi
  SUMS=$(cat "$TMP/sums.txt")
fi

# `head -1` used to pick the first of however many rows named this asset. A manifest with the
# asset twice is a manifest nobody can read as one answer, and silently taking the first is the
# same shape as the defect above: a state that cannot be resolved, resolved anyway.
MATCHES=$(printf '%s\n' "$SUMS" | awk -v a="$ASSET" '$2 == a || $2 == "*" a {print $1}')
COUNT=$(printf '%s\n' "$MATCHES" | grep -c . || true)

if [ "$COUNT" = "0" ]; then
  echo "v$VERSION publishes no $ASSET, so the Formula names an artifact that is not there"
  exit 1
fi
if [ "$COUNT" -gt 1 ]; then
  echo "the manifest lists $ASSET $COUNT times. Which hash is the artifact's is not a question this"
  echo "rule may answer by taking the first one."
  exit 1
fi
PUBLISHED=$(printf '%s\n' "$MATCHES" | head -1)
if ! printf '%s' "$PUBLISHED" | grep -qE '^[0-9a-f]{64}$'; then
  echo "the manifest's hash for $ASSET is not 64 hex characters: '$PUBLISHED'"
  exit 1
fi

if [ "$PINNED" != "$PUBLISHED" ]; then
  echo "Formula/logic-pro-mcp.rb pins a hash that is not v$VERSION's $ASSET:"
  echo "  Formula pins  $PINNED"
  echo "  v$VERSION has $PUBLISHED"
  echo
  echo "brew install fails for everyone until these agree. Copy the published hash into the Formula,"
  echo "or bump the version to the release the hash belongs to."
  exit 1
fi

echo "Formula sha256 matches v$VERSION's $ASSET"
exit 0
