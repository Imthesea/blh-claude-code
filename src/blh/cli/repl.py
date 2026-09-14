from ..core.harness import Harness
from ..core.loop import last_assistant_text


def repl(harness: Harness) -> None:
    messages = harness.new_session()
    jobs = harness.jobs
    agents = harness.agents
    if jobs is not None:
        jobs.set_cron_turn(lambda: harness.run_scheduled_turn(messages))
        jobs.start()
    if agents is not None:
        agents.set_team_turn(lambda: harness.run_team_turn(messages))
        agents.start()
    print("blh — type 'exit' to quit")
    try:
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
            if jobs is not None:
                with jobs.agent_lock:
                    harness.run_turn(messages, text)
            else:
                harness.run_turn(messages, text)
            reply = last_assistant_text(messages)
            if reply:
                print(reply)
    finally:
        if agents is not None:
            agents.stop()
        if jobs is not None:
            jobs.stop()
