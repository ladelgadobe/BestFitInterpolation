"""Session-only reuse of completed tuning, never of performance-validation fits.

Each final model is still fitted on all supplied valid observations. Exact data,
feature order and search settings must match; spatial outer folds never use this.
"""
from copy import deepcopy
import hashlib
import json
import numpy as np


def lookup(owner, method, frame, target, features, grid, folds, iterations, requested_budget=None):
    columns = list(dict.fromkeys(['x', 'y', target] + list(features)))
    clean = frame[columns].replace([np.inf, -np.inf], np.nan).dropna()
    values = np.ascontiguousarray(clean.to_numpy(dtype='<f8'))
    header = dict(version=2, method=method, target=target, features=list(features),
                  columns=columns, shape=values.shape, grid=grid,
                  folds=int(folds), iterations=int(iterations), seed=20,
                  requested_budget=requested_budget)
    digest = hashlib.sha256(json.dumps(header, sort_keys=True).encode('utf-8'))
    digest.update(values.tobytes())
    key = digest.hexdigest()
    cached = getattr(owner, '_framework_search_cache', {}).get(method)
    return key, deepcopy(cached) if cached and cached['key'] == key else None


def remember(owner, method, key, parameters, record):
    if not record or not record.get('executed') or record.get('status') != 'completed':
        return
    if not hasattr(owner, '_framework_search_cache'):
        owner._framework_search_cache = {}
    owner._framework_search_cache[method] = dict(key=key, parameters=deepcopy(parameters),
                                               record=deepcopy(record))


def reuse_record(cached):
    original = deepcopy(cached['record'])
    result = deepcopy(original)
    result.update(status='reused', algorithm='reused_search', executed=False,
                  evaluated_combinations=0, effective_folds=0, search_sample_count=0,
                  validation_design='Not repeated; completed search reused',
                  origin_search=original, training_fingerprint=cached['key'])
    return result


def reuse_progress(callback):
    if callback is None:
        return None
    def progress(done, total, label=None):
        if label and 'manual' in label.lower():
            label = 'Refitting the model with parameters selected by the completed grid search'
        return callback(done, total, label)
    return progress


def fit(owner, method, frame, target, features, tune, kwargs, requested_budget=None):
    """Run automatic tuning or refit selected parameters from an exact match."""
    from .search_provenance import model_search_record
    key, cached = lookup(owner, method, frame, target, features, kwargs['grid_params'],
                         kwargs['cv_folds'], kwargs['max_iterations'], requested_budget)
    generation = getattr(owner, '_analysis_generation', 0)
    if cached:
        kwargs = dict(kwargs, use_grid_search=False, manual_params=cached['parameters'])
        if 'progress_fn' in kwargs:
            kwargs['progress_fn'] = reuse_progress(kwargs['progress_fn'])
    model, parameters = tune(**kwargs)
    if generation != getattr(owner, '_analysis_generation', 0):
        raise KeyboardInterrupt('Data changed; the old search was discarded.')
    if cached:
        parameters = cached['parameters']
        model._bfi_search_summary = reuse_record(cached)
    else:
        remember(owner, method, key, parameters, model_search_record(model))
    return model, parameters
