"""Download riproducibile dei dataset esterni elencati in configs/external_datasets.yaml.

Uso:
    python -m plantcare.data.download            # tutti
    python -m plantcare.data.download ip102 agml_grape
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs" / "external_datasets.yaml"
OUT = ROOT / "data" / "external"


def load_registry() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["datasets"]


def download(entry: dict) -> list[Path]:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    all_files = api.list_repo_files(entry["repo"], repo_type="dataset")
    wanted = [f for f in all_files if any(fnmatch.fnmatch(f, pat) for pat in entry["files"])]
    if not wanted:
        raise RuntimeError(f"{entry['name']}: nessun file corrisponde a {entry['files']}")
    dest = OUT / entry["name"]
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in wanted:
        p = hf_hub_download(entry["repo"], f, repo_type="dataset", local_dir=dest)
        paths.append(Path(p))
        print(f"  {entry['name']}: {f}", flush=True)
    return paths


def main(names: list[str]) -> int:
    reg = load_registry()
    selected = [e for e in reg if not names or e["name"] in names]
    for e in selected:
        print(f"== {e['name']} ({e['repo']})", flush=True)
        try:
            download(e)
        except Exception as exc:  # un dataset che fallisce non blocca gli altri
            print(f"  ERRORE {e['name']}: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
