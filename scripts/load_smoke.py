"""Bounded HTTP load smoke with latency/error denominators; not a capacity claim."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx


async def run(base_url: str, requests: int, concurrency: int) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    latencies, statuses = [], []

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:

        async def one():
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get("/health/ready")
                    statuses.append(response.status_code)
                except Exception:
                    statuses.append(0)
                latencies.append((time.perf_counter() - started) * 1000)

        await asyncio.gather(*(one() for _ in range(requests)))
    ordered = sorted(latencies)
    return {
        "requests": requests,
        "concurrency": concurrency,
        "successes": sum(200 <= value < 300 for value in statuses),
        "errors": sum(not 200 <= value < 300 for value in statuses),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2),
            "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
            "max": round(max(latencies), 2),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 100 or not 1 <= args.requests <= 10000:
        parser.error("requests/concurrency vượt giới hạn smoke test")
    print(
        json.dumps(
            asyncio.run(run(args.base_url, args.requests, args.concurrency)), indent=2
        )
    )
