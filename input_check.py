"""ShadowPad step 2. Inspect saved PPSSPP bindings; explicitly arm one short test."""

import argparse
import sys

from ppsspp_input import ACTIONS, default_controls, execute_test, read_bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", default=default_controls())
    parser.add_argument("--button", choices=ACTIONS)
    parser.add_argument("--run", action="store_true", help="Explicitly arm the selected one-shot test")
    parser.add_argument("--delay", type=float, default=3, help="Time to focus PPSSPP, 1-10 seconds")
    parser.add_argument("--hold", type=float, help="Key hold, 0.03-1 second (directions default to 0.5)")
    args = parser.parse_args()
    bindings = read_bindings(args.controls)
    print("ShadowPad | PPSSPP input check\nSaved keyboard bindings:")
    for action, (_, label) in bindings.items():
        print(f"  {action:8s} -> {label}")
    if not args.run:
        print("PAUSED. No inputs sent. Add --button Left --run to arm one test.")
        return 0
    if not args.button:
        parser.error("--run requires --button.")
    hold = args.hold if args.hold is not None else (0.5 if args.button in ("Left", "Right") else 0.12)
    if not 1 <= args.delay <= 10 or not 0.03 <= hold <= 1:
        parser.error("--delay must be 1-10 seconds; --hold must be 0.03-1 second.")
    state = execute_test(args.button, bindings[args.button], args.delay, hold)
    return 0 if state == "DONE" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Test stopped; keys released.")
        sys.exit(2)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
