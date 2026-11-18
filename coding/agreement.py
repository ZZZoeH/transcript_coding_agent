# The bootstrap resamples whole CALLS (not turns), because turns in one call depend on each other.

import random


def kappa(a, b):
    # agreement between two label lists, corrected for chance (1 = perfect, 0 = chance level)
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in set(a) | set(b))
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def f1(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f


def bootstrap_ci(call_ids, stat, rounds=1000, seed=598):
    # stat(list_of_call_ids) -> number. Returns the 95% interval.
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        sample = [rng.choice(call_ids) for _ in call_ids]
        v = stat(sample)
        if v is not None:
            values.append(v)
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values)) - 1], 3)]
