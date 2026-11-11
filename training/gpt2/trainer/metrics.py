import numpy as np
from scipy.special import expit, logsumexp
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score


def metrics(y, p, prefix="validation"):
    y, p = np.asarray(y), np.asarray(p, dtype=float)
    if y.ndim != 1 or p.shape != y.shape or len(y) == 0:
        raise ValueError("Metric arrays must be nonempty and aligned")
    if (
        set(np.unique(y)) != {0, 1}
        or not np.isfinite(p).all()
        or ((p < 0) | (p > 1)).any()
    ):
        raise ValueError("Undefined labels or invalid probabilities")
    result = {
        prefix + "_auc": float(roc_auc_score(y, p)),
        prefix + "_average_precision": float(average_precision_score(y, p)),
        prefix + "_logloss": float(log_loss(y, p)),
        prefix + "_rows": len(y),
    }
    if not all(np.isfinite(v) for v in result.values()):
        raise ValueError("Nonfinite metric")
    return result


def probabilities(likelihoods, prior_mode, training_prior):
    ll = np.asarray(likelihoods, dtype=np.float64)
    if (
        ll.ndim != 3
        or ll.shape[2] != 2
        or ll.shape[1] == 0
        or not np.isfinite(ll).all()
    ):
        raise ValueError("Expected finite [row, order, label] likelihoods")
    if prior_mode == "reference_no_prior":
        offset = 0.0
    elif prior_mode == "fold_training_prior" and 0 < training_prior < 1:
        offset = np.log(training_prior) - np.log1p(-training_prior)
    else:
        raise ValueError("Invalid prior policy")
    return expit(
        logsumexp(ll[:, :, 1], axis=1) - logsumexp(ll[:, :, 0], axis=1) + offset
    )
