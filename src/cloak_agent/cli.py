"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from .agent import AgentLimitError, BrowserAgent
from .browser import CloakBrowserTools
from .config import AgentConfig, Provider
from .providers import ProviderConfigError, create_provider_client
from .safety import ApprovalMode, SafetyPolicy
from .trace import TraceLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloak-agent",
        description="Run a controlled AI browser agent on CloakBrowser.",
    )
    parser.add_argument("task", help="Natural-language browsing task")
    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in Provider],
        default=os.getenv("CLOAK_AGENT_PROVIDER", Provider.OPENAI.value),
    )
    parser.add_argument("--model", help="Provider model id; defaults by provider")
    parser.add_argument("--base-url", help="Override the provider API base URL")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--no-humanize", action="store_true")
    parser.add_argument("--proxy", default=os.getenv("CLOAK_AGENT_PROXY"))
    parser.add_argument("--geoip", action="store_true")
    parser.add_argument("--locale")
    parser.add_argument("--timezone")
    parser.add_argument(
        "--allow-domain",
        action="append",
        default=[],
        help="Limit browsing to this domain and its subdomains; repeatable",
    )
    parser.add_argument("--allow-private-network", action="store_true")
    parser.add_argument(
        "--approval",
        choices=[mode.value for mode in ApprovalMode],
        default=ApprovalMode.ASK.value,
        help="Handling for consequential actions: ask (default), deny, or allow",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="JSONL trace path (typed values are redacted)",
    )
    parser.add_argument("--screenshot-dir", type=Path, default=Path("artifacts"))
    return parser


def load_environment() -> None:
    """Load project-local .env values without overriding shell variables."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def configure_console_encoding() -> None:
    """Prevent model output from crashing on legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


async def run_from_args(args: argparse.Namespace) -> int:
    provider = Provider(args.provider)
    config = AgentConfig(
        provider=provider,
        model=args.model or "",
        base_url=args.base_url,
        max_steps=args.max_steps,
        headless=not args.headed,
        humanize=not args.no_humanize,
        proxy=args.proxy,
        geoip=args.geoip,
        locale=args.locale,
        timezone=args.timezone,
        allowed_domains=tuple(args.allow_domain),
        allow_private_network=args.allow_private_network,
        approval_mode=ApprovalMode(args.approval),
        trace_path=args.trace,
        screenshot_dir=args.screenshot_dir,
    )
    try:
        client = create_provider_client(config)
    except ProviderConfigError as exc:
        print(f"{exc}.", file=sys.stderr)
        return 2

    trace_path = args.trace
    if trace_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        trace_path = Path("logs") / f"agent-{timestamp}.jsonl"

    config.trace_path = trace_path
    policy = SafetyPolicy(
        allowed_domains=config.allowed_domains,
        allow_private_network=config.allow_private_network,
        approval_mode=config.approval_mode,
    )
    trace = TraceLogger(config.trace_path)

    try:
        async with CloakBrowserTools(config, policy) as browser_tools:
            agent = BrowserAgent(
                client=client,
                browser_tools=browser_tools,
                model=config.model,
                provider=config.provider,
                max_steps=config.max_steps,
                trace=trace,
            )
            answer = await agent.run(args.task)
    except AgentLimitError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Agent failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(answer)
    print(f"\nTrace: {trace_path.resolve()}", file=sys.stderr)
    return 0


def main() -> None:
    configure_console_encoding()
    load_environment()
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run_from_args(args)))


if __name__ == "__main__":
    main()
