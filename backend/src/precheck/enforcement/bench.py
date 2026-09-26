"""Measure enforcement-proxy overhead: same tool call directly vs through the proxy.

python -m precheck.enforcement.bench [--n 50] [--tools URL] [--proxy URL]
"""

import argparse
import asyncio
import statistics
import time
from typing import Any, cast

from mcp import Client

CALL = ("lookup_order", {"order_id": "1234"})
JEV_CALL = ("issue_refund", {"order_id": "1234", "amount": 20, "destination": "Visa ending 4242"})


async def timed(
    client: Client, tool: str, args: dict[str, Any], n: int, meta: dict[str, Any] | None
) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        res = await client.call_tool(tool, args, meta=cast(Any, meta))
        out.append((time.perf_counter() - t0) * 1000)
        assert not res.is_error, res.content
    return out


def p(values: list[float], q: float) -> float:
    return statistics.quantiles(values, n=100)[int(q) - 1] if len(values) > 1 else values[0]


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--tools", default="http://127.0.0.1:8100/mcp")
    parser.add_argument("--proxy", default="http://127.0.0.1:8200/mcp")
    parser.add_argument("--jev", action="store_true", help="also time a call judged by Jev rules")
    args = parser.parse_args(argv)
    meta = {
        "precheck/session": "bench",
        "precheck/agent_id": "support-bot",
        "precheck/user_goal": "Customer returned an item from order 1234 and wants a refund",
    }
    async with Client(args.tools) as direct, Client(args.proxy) as proxy:
        await timed(direct, *CALL, 3, None)
        await timed(proxy, CALL[0], {**CALL[1], "reason": "warm up"}, 3, meta)
        d = await timed(direct, *CALL, args.n, None)
        v = await timed(
            proxy,
            CALL[0],
            {**CALL[1], "reason": "Check the order status the customer asked about"},
            args.n,
            meta,
        )
        print(f"direct   p50 {statistics.median(d):6.1f} ms  p95 {p(d, 95):6.1f} ms")
        v50, v95 = statistics.median(v), p(v, 95)
        print(f"proxy    p50 {v50:6.1f} ms  p95 {v95:6.1f} ms  (deterministic only)")
        print(f"overhead p50 {statistics.median(v) - statistics.median(d):6.1f} ms")
        if args.jev:
            j = await timed(
                proxy,
                JEV_CALL[0],
                {
                    **JEV_CALL[1],
                    "reason": "Customer returned the item; refund to the original Visa",
                },
                min(args.n, 10),
                meta,
            )
            j50, j95 = statistics.median(j), p(j, 95)
            print(f"jev-rule p50 {j50:6.1f} ms  p95 {j95:6.1f} ms  (2 Jev questions)")


if __name__ == "__main__":
    asyncio.run(main())
