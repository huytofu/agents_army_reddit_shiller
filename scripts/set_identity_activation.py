"""Sync YAML `active:` flags from identities/activation.yaml (optional docs sync)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / "x_manager" / "identities"
ROSTER = IDENTITIES / "activation.yaml"


def main() -> None:
    data = yaml.safe_load(ROSTER.read_text(encoding="utf-8")) or {}
    active: set[str] = set()
    for group in (data.get("active") or {}).values():
        active.update(str(x) for x in (group or []))

    for path in sorted(IDENTITIES.glob("*.yaml")):
        if path.name == "activation.yaml":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        identity_id = path.stem
        for line in lines:
            if line.startswith("id:"):
                identity_id = line.split(":", 1)[1].strip()
                break
        want = "true" if identity_id in active else "false"
        out = []
        for line in lines:
            if line.startswith("active:"):
                out.append(f"active: {want}")
            else:
                out.append(line)
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"{identity_id}: active={want}")


if __name__ == "__main__":
    main()
