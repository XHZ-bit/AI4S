"""Original teaching example of a single attention score before softmax.

This is a teaching implementation, with illustrative inputs, by PaperStride.
"""
import math


def scaled_dot_product(q_dot_k, d_k):
    if not math.isfinite(d_k) or d_k <= 0:
        raise ValueError('d_k must be finite and positive')
    return q_dot_k / math.sqrt(d_k)


parameters = globals().get('inputs', {})
score = scaled_dot_product(float(parameters.get('dot', 8)), float(parameters.get('d_k', 4)))
print(score)
