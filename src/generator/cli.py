import argparse
from pathlib import Path
from .config import GeneratorConfig
from .export import write_exports
from .simulation import SalesDataGenerator
from .validation import validate
from .anomalies import inject_controlled_anomalies, detect_anomalies, detection_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic sales data.")
    parser.add_argument("--config", type=Path, default=Path("configs/generator_starter.json"))
    parser.add_argument("--output", type=Path, default=Path("output/starter"))
    parser.add_argument("--inject-anomalies", action="store_true", help="write a separate controlled-anomaly dataset")
    args = parser.parse_args()
    config = GeneratorConfig.from_json(args.config)
    generator = SalesDataGenerator(config)
    data = generator.generate(); validate(data); manifest = generator.manifest()
    if args.inject_anomalies:
        data = inject_controlled_anomalies(data)
        findings = detect_anomalies(data)
        metrics = detection_metrics(findings, data["ground_truth"])
        manifest.update({"anomaly_dataset": True, "detection_metrics": metrics})
    counts = write_exports(data, args.output, manifest)
    print("Baseline validation: PASS")
    for table, count in sorted(counts.items()): print(f"{table}: {count}")
    if args.inject_anomalies: print(f"Detection precision={metrics['precision']:.3f}, recall={metrics['recall']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
