from ..core.harness import Harness
from ..core.loop import last_assistant_text


def repl(harness: Harness) -> None:
    messages = harness.new_session()
    print("blh — type 'exit' to quit")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("exit", "quit"):
            break
        harness.run_turn(messages, text)
        reply = last_assistant_text(messages)
        if reply:
            print(reply)
