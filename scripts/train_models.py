#!/usr/bin/env python3
"""
scripts/train_models.py

Runs the full ML training pipeline:
  1. HistoricalPatternAnalyzer  -- percentile + hourly + correlation profiles
  2. ScenarioGenerator          -- KMeans workload scenario discovery
  3. BehaviorModel              -- RF Regressors per node per metric (forecasting)
  4. AnomalyDetector            -- Isolation Forest (detection) + RF Classifier (type)

Usage:
  python scripts/train_models.py              # uses 30d history, 7d anomaly data
  python scripts/train_models.py --days 7     # shorter window (faster)
"""
import sys, os, argparse, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING)

from core.analytics.model_registry import registry

SEP = "=" * 65


def section(title):
    print("\n  " + "-" * 55)
    print("  " + title)
    print("  " + "-" * 55)


def main(days, anomaly_days):
    print(SEP)
    print("  HPE Digital Twin -- ML Analytics Training Pipeline")
    print(SEP)
    print("  History window  : {} days".format(days))
    print("  Anomaly window  : {} days".format(anomaly_days))
    print()

    t0 = time.time()

    # Step 1-3: run each component directly for granular output
    registry.analyzer.analyze(days=days)
    registry.scenario_gen.generate(days=days)
    registry.behavior_model.train_all(days=days)

    # Step 4: Anomaly Detector (train fresh regardless of saved model)
    ad = registry.anomaly_detector
    ad_summary = ad.train(days=anomaly_days)

    registry._trained = True
    elapsed = time.time() - t0

    # ---- Results ---------------------------------------------------------

    section("1. WORKLOAD SCENARIOS  (KMeans)")
    print("  Best k = {}".format(registry.scenario_gen.best_k))
    for s in registry.get_scenarios():
        m = s.get("metrics", {})
        print("    [{:<16s}]  CPU={:5.1f}%  MEM={:5.1f}%  IOPS={:6.0f}  LAT={:5.1f}ms  ({} pts)".format(
            s["name"],
            m.get("cpu_percent", 0),
            m.get("memory_percent", 0),
            m.get("disk_iops", 0),
            m.get("latency_ms", 0),
            s.get("cluster_size", 0),
        ))

    section("2. BEHAVIOR MODEL  (RF Regressor -- forecasting)")
    summary = registry.behavior_model.training_summary
    if summary:
        for node_id, targets in summary.items():
            scores = "  ".join(
                "{}:R2={:.3f}".format(t, v["r2"]) for t, v in targets.items()
            )
            print("    {:<20s}  {}".format(node_id, scores))
    else:
        print("    (no models trained -- insufficient data)")

    section("3. ANOMALY DETECTOR  (Isolation Forest + RF Classifier)")
    if_res  = ad_summary.get("isolation_forest", {})
    clf_res = ad_summary.get("classifier", {})

    if if_res.get("status") == "trained":
        print("    Isolation Forest  [OK]  (contamination={:.0%}, per role group)".format(ad.contamination))
        print("      Total samples   : {:,}".format(if_res.get("samples", 0)))
        for group, g in if_res.get("groups", {}).items():
            print("      [{:<10s}]  samples={:<6,}  anomaly_rate={:.1%}".format(
                group, g.get("samples", 0), g.get("detected_anomaly_rate", 0)))
    else:
        print("    Isolation Forest  [WARN] {} -- run seed_influx_history.py or keep scraper running".format(
            if_res.get("status")))

    if clf_res.get("status") == "trained":
        print("    RF Classifier     [OK]")
        print("      Samples         : {:,}".format(clf_res.get("samples", 0)))
        print("      F1 (macro)      : {:.3f}".format(clf_res.get("f1_macro", 0)))
        print("      Anomaly classes : {}".format(clf_res.get("classes", [])))
    else:
        print("    RF Classifier     [WARN] {} -- run inject_anomaly_windows.py --days 7 first".format(
            clf_res.get("status")))

    print("\n  Total training time : {:.1f}s".format(elapsed))
    print(SEP)
    print("  Models saved to:  models/")
    print("  Next step:        python run.py  -->  POST /api/v1/analytics/anomalies/detect")
    print(SEP)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Train all HPE Digital Twin ML models")
    p.add_argument("--days",         type=int, default=30,
                   help="Days of history for BehaviorModel + ScenarioGenerator (default: 30)")
    p.add_argument("--anomaly-days", type=int, default=7,
                   help="Days of anomaly_training_data for IF + Classifier (default: 7)")
    args = p.parse_args()
    main(days=args.days, anomaly_days=args.anomaly_days)
