"""Deterministic maximum-weight one-to-one assignment (Hungarian, stdlib)."""


def assignment(weights, forbidden=None):
    """Positive real edges only; zero-weight dummy vertices permit unmatched rows.

    Ascending gold/prediction traversal and strict improvements break ties. Return
    alternative-optimum information separately; a tie never certifies identity.
    """
    rows = len(weights)
    cols = len(weights[0]) if rows else 0
    n = rows + cols
    if not n:
        return [], 0
    costs = [[0] * n for _ in range(n)]
    for i in range(rows):
        for j in range(cols):
            costs[i][j] = -weights[i][j] if (i, j) != forbidden else 10**12
    u, v, p, way = ([0] * (n + 1) for _ in range(4))
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minimum, used = [10**15] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], 10**15, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minimum[j]:
                        minimum[j], way[j] = cur, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0], j0 = p[j1], j1
            if j0 == 0:
                break
    pairs = sorted((p[j] - 1, j - 1) for j in range(1, cols + 1)
                   if 0 < p[j] <= rows and weights[p[j] - 1][j - 1] > 0
                   and (p[j] - 1, j - 1) != forbidden)
    return pairs, sum(weights[i][j] for i, j in pairs)


def match(weights):
    pairs, score = assignment(weights)
    return [dict(gold=i, prediction=j, score=weights[i][j],
                 ambiguous=assignment(weights, (i, j))[1] == score)
            for i, j in pairs]
