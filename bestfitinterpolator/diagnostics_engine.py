"""Statistical and spatial diagnostics; flags are evidence, never deletions."""
from dataclasses import dataclass, field
import hashlib
import numpy as np
try:
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree=None
from .spatial_diagnostics import _knn_indices


@dataclass
class DiagnosticsState:
    layer_id: str
    field_name: str
    ids: np.ndarray
    coordinates: np.ndarray
    values: np.ndarray
    decisions: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    revision: int = 0

    @property
    def invalid_feature_ids(self):
        # Captured arrays are immutable snapshots; edits create a new state.
        # Cache only invalid IDs, avoiding an O(n) scan for each layer feature.
        if "_invalid_feature_ids" not in self.__dict__:
            valid=np.isfinite(self.values)&np.isfinite(self.coordinates).all(axis=1)
            self._invalid_feature_ids=frozenset(map(int,self.ids[~valid]))
        return self._invalid_feature_ids

    @property
    def analysis_mask(self):
        valid = np.isfinite(self.values) & np.isfinite(self.coordinates).all(axis=1)
        return valid & np.array([self.decisions.get(int(fid)) != "Exclude" for fid in self.ids],dtype=bool)

    def decide(self, ids, decision):
        if decision not in ("Keep", "Exclude", "Reset"):
            raise ValueError("Unknown user decision")
        for fid in ids:
            if decision == "Reset":
                self.decisions.pop(int(fid), None)
            else:
                self.decisions[int(fid)] = decision
        self.revision += 1


def statistical_flags(values, methods=("IQR", "MAD"), k=1.5, mad_limit=3.5,
                      z_limit=3.0, consensus="Any", at_least=2):
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    v = values[valid]
    flags = {key: np.zeros(values.size, dtype=bool) for key in ("IQR", "MAD", "Z")}
    scores = {key: np.full(values.size, np.nan) for key in ("MAD", "Z")}
    summary = {"valid": int(v.size), "invalid": int(values.size-v.size)}
    if v.size:
        q1, median, q3 = np.percentile(v, (25, 50, 75))
        iqr = q3-q1
        lower, upper = q1-k*iqr, q3+k*iqr
        flags["IQR"][valid] = (v < lower) | (v > upper)
        mad = np.median(np.abs(v-median))
        # Zero MAD has no finite standardized scale. Equal values score zero;
        # unequal values score signed infinity and remain explicitly reviewable.
        modified = .6744897501960817*(v-median)/mad if mad > 0 else np.copysign(np.full(v.size,np.inf),v-median)
        if mad == 0:
            modified[v == median] = 0.
        std = float(np.std(v))
        z = (v-np.mean(v))/std if std > 0 else np.zeros(v.size)
        scores["MAD"][valid], scores["Z"][valid] = modified, z
        flags["MAD"][valid] = np.abs(modified) > mad_limit
        flags["Z"][valid] = np.abs(z) > z_limit
        summary.update(mean=float(np.mean(v)), median=float(median), std=std, min=float(np.min(v)),
            max=float(np.max(v)), q1=float(q1), q3=float(q3), iqr=float(iqr), mad=float(mad),
            lower=float(lower), upper=float(upper))
    selected = tuple(method for method in methods if method in flags)
    votes = np.sum([flags[key] for key in selected], axis=0) if selected else np.zeros(values.size, dtype=int)
    required = len(selected) if consensus == "All" else int(at_least) if consensus == "At least N" else 1
    flagged = valid & (votes >= required) if selected else np.zeros(values.size, dtype=bool)
    return dict(flags=flags, scores=scores, votes=votes, statistical=flagged, summary=summary, methods=selected)


def build_neighbors(coordinates, mode="KNN", k=8, distance=1.0):
    coords = np.asarray(coordinates, dtype=float)
    n = len(coords)
    if n < 2:
        return [np.array([], dtype=int) for _ in range(n)]
    if mode == "KNN":
        return [row for row in _knn_indices(coords, min(max(1, int(k)), n-1))]
    if distance <= 0:
        raise ValueError("Distance threshold must be positive (in layer CRS units).")
    if cKDTree is None:
        # A cell index avoids a dense all-pairs matrix when SciPy is unavailable.
        cells=[tuple(int(np.floor(c/distance)) for c in point) for point in coords]
        buckets={}
        for i,cell in enumerate(cells): buckets.setdefault(cell,[]).append(i)
        result=[]
        for i,(cx,cy) in enumerate(cells):
            candidates=[j for dx in (-1,0,1) for dy in (-1,0,1) for j in buckets.get((cx+dx,cy+dy),()) if j!=i]
            close=[j for j in candidates if np.hypot(*(coords[j]-coords[i]))<=distance]
            result.append(np.asarray(sorted(close),dtype=int))
        return result
    tree = cKDTree(coords)
    return [np.array([j for j in row if j != i], dtype=int)
            for i, row in enumerate(tree.query_ball_point(coords, float(distance)))]


def spatial_statistics(values, neighbors, permutations=499, seed=42, cancelled=lambda: False):
    """Anselin I_i with row-standardized binary weights and conditional permutations.

    Local null draws hold the focal value fixed and sample its neighbor count
    without replacement from all other observations. Common random draws are
    reused across sites, with each site's self index omitted. Global Moran uses
    whole-vector permutations; it never classifies an individual observation.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    counts = np.array([len(row) for row in neighbors], dtype=int)
    centered = values-np.mean(values) if n else values.copy()
    m2 = float(np.mean(centered**2)) if n else 0.
    lag = np.array([np.mean(centered[row]) if len(row) else 0. for row in neighbors])
    local = centered*lag/m2 if m2 > 0 else np.zeros(n)
    pseudo = np.ones(n)
    medians = np.array([np.median(values[row]) if len(row) else np.nan for row in neighbors])
    residual = values-medians
    robust = np.full(n, np.nan)
    for i, row in enumerate(neighbors):
        if len(row):
            scale = float(np.median(np.abs(values[row]-medians[i])))
            robust[i] = .6744897501960817*residual[i]/scale if scale > 0 else (0. if residual[i] == 0 else np.copysign(np.inf, residual[i]))
    s0 = int(np.count_nonzero(counts))
    global_i = float(n*np.sum(local)/(s0*n)) if s0 and m2 > 0 else 0.
    global_p = 1.
    p = int(permutations)
    if p < 1:
        raise ValueError("At least one permutation is required")
    if n > 2 and m2 > 0 and s0:
        columns=np.concatenate(neighbors) if s0 else np.array([],dtype=int)
        indptr=np.concatenate(([0],np.cumsum(counts)))
        weights=np.concatenate([np.full(len(row),1./len(row)) for row in neighbors if len(row)])
        try:
            from scipy.sparse import csr_matrix
            matrix=csr_matrix((weights,columns,indptr),shape=(n,n))
            spatial_dot=matrix.dot
        except ImportError:
            rows=np.repeat(np.arange(n),counts)
            spatial_dot=lambda array:np.bincount(rows,weights=weights*array[columns],minlength=n)
        rng = np.random.default_rng(seed)
        max_k = int(np.max(counts))
        draws = np.array([rng.choice(n-1, size=max_k, replace=False) for _ in range(p)])
        for i, row in enumerate(neighbors):
            if cancelled():
                raise InterruptedError("Spatial diagnostics cancelled")
            if not len(row):
                continue
            idx = draws[:, :len(row)]
            idx = idx+(idx >= i)
            sim = centered[i]*np.mean(centered[idx], axis=1)/m2
            if np.ptp(sim) <= np.finfo(float).eps * max(1.,abs(local[i])):
                pseudo[i] = 1.
                continue
            larger = int(np.count_nonzero(sim >= local[i]))
            pseudo[i] = (min(larger, p-larger)+1.)/(p+1.)
        simulations = np.empty(p)
        for r in range(p):
            if cancelled():
                raise InterruptedError("Spatial diagnostics cancelled")
            z = rng.permutation(centered)
            numerator = float(np.dot(z,spatial_dot(z)))
            simulations[r] = n*numerator/(s0*np.sum(centered**2))
        expected = -1./(n-1)
        global_p = (np.count_nonzero(np.abs(simulations-expected) >= abs(global_i-expected))+1.)/(p+1.)
    return dict(local_i=local, pseudo_p=pseudo, centered=centered, spatial_lag=lag,
                neighbors=counts, local_median=medians, local_residual=residual, robust_local_score=robust,
                global_moran=dict(I=global_i, p=global_p, permutations=p, seed=seed),
                neighborhood=dict(min=int(np.min(counts)) if n else 0, mean=float(np.mean(counts)) if n else 0.,
                    max=int(np.max(counts)) if n else 0, isolated=int(np.count_nonzero(counts == 0))))


def classify(statistical, spatial, alpha=.05):
    centered, lag = spatial["centered"], spatial["spatial_lag"]
    significant = (spatial["pseudo_p"] <= alpha) & (spatial["neighbors"] > 0) & (centered != 0)
    lisa = np.full(len(centered), "NS", dtype="U2")
    for token, mask in (("HH", (centered > 0)&(lag > 0)), ("LL", (centered < 0)&(lag < 0)),
                        ("HL", (centered > 0)&(lag < 0)), ("LH", (centered < 0)&(lag > 0))):
        lisa[significant & mask] = token
    outlier = np.isin(lisa, ("HL", "LH"))
    combined = np.full(len(lisa), "Normal", dtype="U24")
    combined[lisa == "HH"] = "HH cluster"
    combined[lisa == "LL"] = "LL cluster"
    combined[statistical & ~outlier] = "Statistical only"
    combined[~statistical & outlier] = "Spatial only"
    combined[statistical & outlier] = "Statistical + Spatial"
    return lisa, outlier, combined


class DiagnosticsEngine:
    def __init__(self):
        self._neighbors_key = self._spatial_key = None
        self._neighbors = self._spatial = None

    def calculate(self, coordinates, values, settings=None, cancelled=lambda: False):
        settings = dict(settings or {})
        coordinates, values = np.asarray(coordinates, float), np.asarray(values, float)
        valid = np.isfinite(values) & np.isfinite(coordinates).all(axis=1)
        v, xy = values[valid], coordinates[valid]
        stat = statistical_flags(np.where(valid,values,np.nan), **{k:settings[k] for k in ("methods", "k", "mad_limit", "z_limit", "consensus", "at_least") if k in settings})
        signature = hashlib.sha256(xy.tobytes()).hexdigest()
        key = (signature, settings.get("neighborhood", "KNN"), settings.get("neighbors", 8), settings.get("distance", 1.))
        if key != self._neighbors_key:
            self._neighbors = build_neighbors(xy, key[1], key[2], key[3])
            self._neighbors_key = key
        spatial_key = (key, hashlib.sha256(v.tobytes()).hexdigest(), settings.get("permutations", 499), settings.get("seed", 42))
        if spatial_key != self._spatial_key:
            self._spatial = spatial_statistics(v, self._neighbors, spatial_key[2], spatial_key[3], cancelled)
            self._spatial_key = spatial_key
        sp = self._spatial
        lisa, outlier, combined = classify(stat["statistical"][valid], sp, settings.get("alpha", .05))
        result = dict(stat, valid=valid, neighborhood=sp["neighborhood"], global_moran=sp["global_moran"], settings=settings)
        for key in ("local_i", "pseudo_p", "neighbors", "local_median", "local_residual", "robust_local_score"):
            a = np.full(values.size, np.nan)
            a[valid] = sp[key]
            result[key] = a
        result["lisa"] = np.full(values.size, "Invalid", dtype="U7")
        result["lisa"][valid] = lisa
        result["spatial_outlier"] = np.zeros(values.size, bool)
        result["spatial_outlier"][valid] = outlier
        result["combined"] = np.full(values.size, "Missing/Invalid", dtype="U24")
        result["combined"][valid] = combined
        return result
