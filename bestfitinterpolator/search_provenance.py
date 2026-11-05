"""Completed hyperparameter-selection records, independent of current widgets."""
from copy import deepcopy


def record_search(model, requested, parameters, full_n, algorithm="manual",
                  total=0, evaluated=0, folds=0, search_n=0, objective=None,
                  score=None, random_state=20, space=None):
    """Attach a record only after the tuning function successfully finishes."""
    model._bfi_search_summary = dict(
        requested=bool(requested), executed=bool(evaluated),
        status="completed" if evaluated else ("single_configuration" if requested else "manual"),
        algorithm=algorithm, total_combinations=int(total),
        evaluated_combinations=int(evaluated), effective_folds=int(folds),
        search_sample_count=int(search_n), full_sample_count=int(full_n),
        objective=objective, best_score=None if score is None else float(score),
        random_seed=int(random_state), search_space=deepcopy(space or {}),
        selected_parameters=deepcopy(parameters),
        validation_design="Shuffled K-fold cross-validation" if evaluated else "Not run",
        nested=False)


def model_search_record(model):
    return deepcopy(getattr(model, "_bfi_search_summary", None))


def search_details(configuration):
    """Readable fields for a frozen validation/interpolation configuration."""
    record = configuration.get("search_summary")
    if not record:
        return [("Hyperparameter selection", "Execution details not recorded; rerun this method to populate them.")]
    status = record["status"]
    if status == "reused":
        source = record['origin_search']
        rows = search_details(dict(search_summary=source))
        rows[0] = ("Hyperparameter selection", "Completed grid search reused")
        rows.insert(1, ("Additional search combinations evaluated", 0))
        titles = {"Evaluated / available combinations": "Original search combinations (evaluated / available)",
                  "Search validation": "Original search validation",
                  "Selection criterion and best search score": "Original search criterion and score"}
        rows = [(titles.get(title, title), value) for title, value in rows]
        return rows + coverage_details(configuration)
    if status == "manual":
        selection = "Manual parameters; search not run"
    elif status == "single_configuration":
        selection = "Search requested, but the grid contained one configuration; search CV not run"
    else:
        selection = {"random_search": "Reproducible random search over a finite grid",
                     "grid_search": "Grid search over the finite grid"}.get(record["algorithm"], record["algorithm"])
    def value_text(value):
        if isinstance(value, float):
            return "{:.6g}".format(value)
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(value_text(item) for item in value) + "]"
        return str(value)
    def pairs(values):
        return "; ".join("{}={}".format(key, value_text(value)) for key, value in values.items()) or "Not recorded"
    rows = [("Hyperparameter selection", selection),
            ("Selected parameters", pairs(record.get("selected_parameters", {}))),
            ("Observations supplied to the tuning/fitting routine", record["full_sample_count"])]
    if record["executed"]:
        rows += [("Evaluated / available combinations", "{} / {}".format(record["evaluated_combinations"], record["total_combinations"])),
                 ("Search validation", "{}; {} folds; n={}; seed={}".format(record["validation_design"], record["effective_folds"], record["search_sample_count"], record["random_seed"])),
                 ("Selection criterion and best search score", "Lowest cross-validation {} = {}".format(record["objective"], value_text(record["best_score"]))),
                 ("Search repeated inside performance-validation folds", "No; parameters selected before performance validation")]
        rows.append(("Effective search values", pairs(record.get("search_space", {}))))
    else:
        rows.append(("Evaluated search combinations", 0))
    return rows + coverage_details(configuration)


def coverage_details(configuration):
    rows = []
    for key, label in (("training_coverage", "Training observations with complete predictors"),
                       ("grid_coverage", "Prediction cells with complete predictors")):
        values = configuration.get(key)
        if values:
            rows.append((label, "{} / {} ({:.1f}%)".format(values['retained'], values['supplied'], 100*values['fraction'])))
    return rows
