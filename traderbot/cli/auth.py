from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from traderbot.auth.apikeys import create_api_key, list_api_keys
from traderbot.auth.envfile import load_env_file, upsert_env_vars
from traderbot.auth.login import login_v2
from traderbot.auth.session import normalize_totp, token_from_env
from traderbot.nobitex.client import NobitexClient, NobitexClientError


def _prompt_username() -> str:
    if sys.stdin.isatty():
        return input("Nobitex email: ").strip()
    return ""


def _prompt_totp() -> str:
    if sys.stdin.isatty():
        return normalize_totp(getpass.getpass("2FA code (6 digits): "))
    return ""


def _resolve_totp(arg_totp: str | None) -> str | None:
    totp = arg_totp or os.environ.get("NOBITEX_TOTP")
    if not totp:
        totp = _prompt_totp()
    if not totp:
        return None
    return normalize_totp(totp)


def _redact_apikey_response(data: dict) -> dict:
    out = dict(data)
    if "privateKey" in out:
        out["privateKey"] = "<redacted; use --show-secrets or --write-env>"
    return out


def _cmd_check() -> None:
    load_env_file()
    data = NobitexClient.from_env().request("GET", "/users/profile")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _cmd_login(args: argparse.Namespace) -> None:
    load_env_file()
    username = args.username or os.environ.get("NOBITEX_USERNAME", "").strip()
    if not username:
        username = _prompt_username()
    if not username:
        print("pass --username, set NOBITEX_USERNAME, or run in a TTY", file=sys.stderr)
        raise SystemExit(2)
    password = args.password or os.environ.get("NOBITEX_PASSWORD", "")
    if not password:
        password = getpass.getpass("Nobitex password: ")
    totp = _resolve_totp(args.totp)
    result = login_v2(
        username=username,
        password=password,
        totp=totp,
        remember=args.remember,
    )
    token = result.get("key")
    if not token:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("login did not return a token (MFA step may be required)", file=sys.stderr)
        raise SystemExit(1)
    if args.write_env:
        upsert_env_vars(Path(args.env_file), {"NOBITEX_AUTH_TOKEN": token})
        print(f"saved NOBITEX_AUTH_TOKEN to {args.env_file}", file=sys.stderr)
    payload = {"status": result.get("status"), "expiresIn": result.get("expiresIn")}
    if args.show_token:
        payload["key"] = token
    else:
        payload["key"] = "<redacted; use --show-token or --write-env>"
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    load_env_file()
    return token_from_env()


def _cmd_apikeys_list(args: argparse.Namespace) -> None:
    token = _resolve_token(args)
    print(json.dumps(list_api_keys(token), ensure_ascii=False, indent=2))


def _cmd_apikeys_create(args: argparse.Namespace) -> None:
    totp = _resolve_totp(args.totp)
    if not totp:
        print("2FA code required: enter at prompt, --totp, or NOBITEX_TOTP", file=sys.stderr)
        raise SystemExit(2)
    token = _resolve_token(args)
    result = create_api_key(
        token,
        name=args.name,
        permissions=args.permissions,
        totp=totp,
        description=args.description,
    )
    if args.write_env and result.get("status") == "ok":
        public = (result.get("key") or {}).get("key") or ""
        private = result.get("privateKey") or ""
        if public and private:
            upsert_env_vars(
                Path(args.env_file),
                {
                    "NOBITEX_API_PUBLIC_KEY": public,
                    "NOBITEX_API_PRIVATE_KEY": private,
                },
            )
            print(f"saved API key pair to {args.env_file}", file=sys.stderr)
    if args.show_secrets:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(_redact_apikey_response(result), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Nobitex authentication: API key check, login (Token), API key create/list.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify NOBITEX_API_* in .env (GET /users/profile)")

    login = sub.add_parser("login", help="Session login (captcha=api); optional X-TOTP")
    login.add_argument("--username", default=None, help="Or NOBITEX_USERNAME in .env")
    login.add_argument("--password", default=None, help="Or NOBITEX_PASSWORD (avoid shell history)")
    login.add_argument(
        "--totp",
        default=None,
        help="2FA code; if omitted, prompts in the terminal (or NOBITEX_TOTP)",
    )
    login.add_argument("--remember", action="store_true", help="Request longer-lived token")
    login.add_argument("--show-token", action="store_true", help="Print session token in JSON")
    login.add_argument(
        "--write-env",
        action="store_true",
        help="Write NOBITEX_AUTH_TOKEN to .env",
    )
    login.add_argument("--env-file", type=Path, default=Path(".env"))

    keys = sub.add_parser("apikeys", help="Manage API keys (requires session Token)")
    keys_sub = keys.add_subparsers(dest="apikeys_cmd", required=True)

    list_p = keys_sub.add_parser("list", help="GET /apikeys/list")
    list_p.add_argument("--token", default=None, help="Or NOBITEX_AUTH_TOKEN in .env")

    create = keys_sub.add_parser("create", help="POST /apikeys/create (X-TOTP required)")
    create.add_argument("--name", default="traderbot-cli")
    create.add_argument("--description", default="Created via traderbot auth apikeys create")
    create.add_argument(
        "--permissions",
        default="READ",
        help="Comma-separated: READ, TRADE, WITHDRAW, … (fixed after create)",
    )
    create.add_argument(
        "--totp",
        required=False,
        help="6-digit 2FA; if omitted, prompts in the terminal (X-TOTP header)",
    )
    create.add_argument("--token", default=None)
    create.add_argument(
        "--write-env",
        action="store_true",
        help="Save public + privateKey to .env (private shown only once by Nobitex)",
    )
    create.add_argument("--show-secrets", action="store_true", help="Print privateKey in JSON")
    create.add_argument("--env-file", type=Path, default=Path(".env"))

    args = parser.parse_args(argv)
    load_env_file()

    try:
        if args.command == "check":
            _cmd_check()
            return
        if args.command == "login":
            _cmd_login(args)
            return
        if args.command == "apikeys":
            if args.apikeys_cmd == "list":
                _cmd_apikeys_list(args)
                return
            if args.apikeys_cmd == "create":
                _cmd_apikeys_create(args)
                return
    except NobitexClientError as e:
        print(e, file=sys.stderr)
        if e.body is not None:
            print(json.dumps(e.body, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1) from e

    print(f"unknown command {args.command!r}", file=sys.stderr)
    raise SystemExit(1)
