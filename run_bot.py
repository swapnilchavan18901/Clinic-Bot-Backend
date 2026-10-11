"""Entry point — the voice receptionist.

    uv run run_bot.py      → open http://localhost:7860 and talk
"""

from app.ai.agent import bot  # noqa: F401  (Pipecat's runner looks up `bot` in __main__)

if __name__ == "__main__":
    from pipecat.runner.run import main

    main()