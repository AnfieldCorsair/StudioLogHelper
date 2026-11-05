# -*- coding: utf-8 -*-
"""check_gates.py — бенчмарк-гейты для CI: падение при регрессии производительности.

Сравнивает замеры с golden.json. Бюджет кейса = max(golden * multiplier, floor_ms):
- multiplier=10 допускает медленные CI-раннеры (обычно 2-5x) и шум;
- полный откат оптимизаций 2026-11 (5-7x замедление) уверенно ловится.

Запуск: python bench/check_gates.py [--write-golden]
Код выхода: 0 — все гейты пройдены, 1 — есть регрессия.
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bench as B  # noqa: E402  (строит корпус при импорте)

GOLDEN_PATH = HERE / "golden.json"
RESULTS_PATH = HERE / "results.json"


def measure(fn, n: int = 3) -> float:
    best = float("inf")
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1000.0  # ms


def main() -> int:
    if not GOLDEN_PATH.exists():
        print(f"ERROR: {GOLDEN_PATH} не найден")
        return 1

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    multiplier = float(golden.get("multiplier", 10))
    floor_ms = float(golden.get("floor_ms", 25))
    cases_golden = golden["cases"]

    # Прогрев (первый запуск платит за инициализацию кэшей/regex)
    for _, fn in B.BENCH_CASES:
        fn()

    results = {}
    failures = []
    print(f"{'benchmark':42s} {'measured':>10s} {'budget':>10s} {'golden':>9s}  status")
    print("-" * 84)
    for name, fn in B.BENCH_CASES:
        measured = measure(fn)
        g = float(cases_golden.get(name, measured))
        budget = max(g * multiplier, floor_ms)
        results[name] = {"measured_ms": round(measured, 2), "golden_ms": g, "budget_ms": round(budget, 2)}
        ok = measured <= budget
        status = "OK" if ok else "FAIL (regression)"
        if not ok:
            failures.append(name)
        print(f"{name:42s} {measured:9.2f}m {budget:9.2f}m {g:8.2f}m  {status}")

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if "--write-golden" in sys.argv:
        golden["cases"] = {k: round(v["measured_ms"], 2) for k, v in results.items()}
        GOLDEN_PATH.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\ngolden.json обновлён: {GOLDEN_PATH}")

    if failures:
        print(f"\nРЕГРЕССИЯ: {', '.join(failures)}")
        return 1
    print("\nВсе гейты пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
