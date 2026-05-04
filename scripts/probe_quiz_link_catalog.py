from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_mapping(links_path: Path) -> dict[str, object]:
    payload = json.loads(links_path.read_text())
    mapping = payload.get("by_name") if isinstance(payload, dict) and "by_name" in payload else payload
    if not isinstance(mapping, dict):
        raise SystemExit(f"Unsupported quiz links structure in {links_path}")
    return mapping


def _collect_relative_paths(mapping: dict[str, object], links_path: Path) -> list[str]:
    relative_paths: set[str] = set()
    for record in mapping.values():
        if not isinstance(record, dict):
            continue
        relative_path = record.get("relative_path")
        if isinstance(relative_path, str) and relative_path:
            relative_paths.add(Path(relative_path).name)
        links = record.get("links")
        if isinstance(links, list):
            for item in links:
                if not isinstance(item, dict):
                    continue
                relative_path = item.get("relative_path")
                if isinstance(relative_path, str) and relative_path:
                    relative_paths.add(Path(relative_path).name)
    if not relative_paths:
        raise SystemExit(f"No quiz relative_path entries found in {links_path}")
    return sorted(relative_paths)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe a committed quiz link catalog and emit a reusable sample/count pair."
    )
    parser.add_argument("--links-file", required=True, help="Path to quiz_links.json")
    args = parser.parse_args()

    links_path = Path(args.links_file)
    mapping = _load_mapping(links_path)
    relative_paths = _collect_relative_paths(mapping, links_path)
    print(len(relative_paths))
    print(relative_paths[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
