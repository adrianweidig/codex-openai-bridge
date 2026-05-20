#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_MODELS = "coder,codex,gpt-5.5,gpt-5.4,gpt-5.4-mini,gpt-5.3-codex,gpt-5.3-codex-spark"


def request_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register Codex OpenAI Bridge as an OpenWebUI Responses provider.")
    parser.add_argument("--openwebui-url", default=os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000"))
    parser.add_argument("--admin-token", default=os.getenv("OPENWEBUI_ADMIN_TOKEN"))
    parser.add_argument("--bridge-url", default=os.getenv("CODEX_BRIDGE_OPENWEBUI_URL", "http://codex-openai-bridge:4010/v1"))
    parser.add_argument("--bridge-api-key", default=os.getenv("CODEX_BRIDGE_API_KEY", ""))
    parser.add_argument("--models", default=os.getenv("CODEX_BRIDGE_MODELS", DEFAULT_MODELS))
    parser.add_argument("--tag", default="Codex Bridge")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.admin_token:
        raise SystemExit("Set OPENWEBUI_ADMIN_TOKEN or pass --admin-token.")

    base_url = args.openwebui_url.rstrip("/")
    bridge_url = args.bridge_url.rstrip("/")
    models = [item.strip() for item in args.models.split(",") if item.strip()]

    config = request_json("GET", f"{base_url}/openai/config", args.admin_token)
    urls = list(config.get("OPENAI_API_BASE_URLS") or [])
    keys = list(config.get("OPENAI_API_KEYS") or [])
    api_configs = dict(config.get("OPENAI_API_CONFIGS") or {})

    if bridge_url in urls:
        idx = urls.index(bridge_url)
        while len(keys) < len(urls):
            keys.append("")
        keys[idx] = args.bridge_api_key
    else:
        urls.append(bridge_url)
        keys.append(args.bridge_api_key)
        idx = len(urls) - 1

    api_configs[str(idx)] = {
        "enable": True,
        "tags": [args.tag],
        "prefix_id": "",
        "model_ids": models,
        "connection_type": "local",
        "auth_type": "bearer",
        "provider": "codex-bridge",
        "api_type": "responses",
    }

    payload = {
        "ENABLE_OPENAI_API": True,
        "OPENAI_API_BASE_URLS": urls,
        "OPENAI_API_KEYS": keys,
        "OPENAI_API_CONFIGS": api_configs,
    }
    request_json("POST", f"{base_url}/openai/config/update", args.admin_token, payload)
    print(f"Registered Codex Bridge provider at index {idx}: {bridge_url}")
    print("Provider API type: responses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
