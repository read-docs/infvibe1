def approx(expected: float, epsilon: float = 1.192092896e-05):
    """doctest's Approx: |a - b| < epsilon * (1 + max(|a|, |b|)), so the C++
    tests' tolerances carry over unchanged."""
    return _Approx(expected, epsilon)


class _Approx:
    def __init__(self, expected: float, epsilon: float):
        self.expected, self.epsilon = expected, epsilon

    def __eq__(self, actual) -> bool:
        a, b = float(actual), self.expected
        return abs(a - b) < self.epsilon * (1 + max(abs(a), abs(b)))

    def __repr__(self) -> str:
        return f"Approx({self.expected}, epsilon={self.epsilon})"

