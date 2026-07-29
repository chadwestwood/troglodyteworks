#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database
from twe.services.knowledge_rail import sync_approved_sources


def main():
    config = load_config()
    result = sync_approved_sources(
        Database(config.database_url),
        config.knowledge_manifest_path,
    )
    print(f"knowledge sources={result['sources']} chunks={result['chunks']}")


if __name__ == "__main__":
    main()
