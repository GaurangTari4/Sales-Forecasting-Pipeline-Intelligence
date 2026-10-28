from __future__ import annotations
import argparse
from pathlib import Path
from src.validation.io import load_csv_dataset
from .builder import build_feature_dataset, build_labels
from .persistence import persist_feature_dataset


def main():
    parser = argparse.ArgumentParser(description="Build leak-free point-in-time feature and label datasets.")
    parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    features = build_feature_dataset(load_csv_dataset(args.input)); labels = build_labels(load_csv_dataset(args.input), features)
    print(persist_feature_dataset(features, labels, args.output))


if __name__ == "__main__": main()
