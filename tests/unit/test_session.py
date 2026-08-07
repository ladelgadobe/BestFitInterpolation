# -*- coding: utf-8 -*-
"""Behavioral tests for the shared BFISession."""

import numpy as np
import pytest

from bestfitinterpolator.core.exceptions import InvalidDataError
from bestfitinterpolator.core.types import TrainingData
from bestfitinterpolator.services.session import BFISession


def test_require_training_data_raises_when_empty():
    with pytest.raises(InvalidDataError, match="Data tab"):
        BFISession().require_training_data()


def test_training_data_roundtrip():
    s = BFISession()
    data = TrainingData(xy=np.zeros((3, 2)), values=np.ones(3))
    s.training_data = data
    assert s.require_training_data() is data


def test_selected_covariate_paths_follow_selection_order():
    s = BFISession()
    s.covariate_paths = {"ndvi": "a.tif", "elev": "b.tif", "slope": "c.tif"}
    s.covariate_selection = ["slope", "ndvi", "missing"]
    assert s.selected_covariate_paths() == ["c.tif", "a.tif"]


def test_results_store_and_reset():
    s = BFISession()
    s.store_fit("idw", object())
    s.store_cv("idw", object())
    assert "idw" in s.fit_results and "idw" in s.cv_results
    s.reset_results()
    assert not s.fit_results and not s.cv_results
