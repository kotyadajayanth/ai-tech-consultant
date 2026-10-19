"""python -m app.cli ingest [--limit 20]   (cron-friendly alternative to the in-process scheduler)"""
import argparse
import asyncio

from .brain import Brain
from .config import Settings
from .ingestion.crawler import HttpFetcher, ingest
from .llm import ClaudeLLM


async def _main(limit):
    s = Settings()
    brain = Brain(s, llm=ClaudeLLM())
    f = HttpFetcher(s)
    try:
        print(await ingest(brain, f, limit))
    finally:
        await f.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["ingest"])
    p.add_argument("--limit", type=int, default=None, help="only process N pages (start with 10-20)")
    asyncio.run(_main(p.parse_args().limit))
