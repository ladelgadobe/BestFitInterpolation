<div align="center">

<img src="bestfitinterpolator/icon.png" alt="Best Fit Interpolator icon" width="150">

# Best Fit Interpolator

### QGIS plugin for spatial interpolation method selection, validation, and mapping

Best Fit Interpolator helps users compare deterministic, geostatistical, machine-learning, and hybrid interpolation methods for digital soil mapping, environmental monitoring, and precision agriculture.

[![QGIS](https://img.shields.io/badge/QGIS-3.14%2B-589632?style=for-the-badge&logo=qgis&logoColor=white)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Version](https://img.shields.io/badge/version-1.1-1565C0?style=for-the-badge)](https://github.com/ladelgadobe/BestFitInterpolation/releases/tag/v1.1)
[![Article](https://img.shields.io/badge/Reference%20Article-Precision%20Agriculture-1B5E20?style=for-the-badge)](https://doi.org/10.1007/s11119-025-10311-8)

[Reference article](https://doi.org/10.1007/s11119-025-10311-8) |
[Tutorial PDF](BestFitInterpolation_PluginV1.1.pdf) |
[Issues](https://github.com/ladelgadobe/BestFitInterpolation/issues) |
[Contact](mailto:ladelgadobe@unal.edu.co)

</div>

---

## Project Snapshot

| What it does | Why it matters |
| --- | --- |
| Compares interpolation methods in QGIS | Helps users choose a method instead of relying on a single default interpolator |
| Runs validation metrics and observed-vs-predicted plots | Supports transparent model comparison before map generation |
| Includes deterministic, geostatistical, ML, and hybrid workflows | Covers small datasets, dense sampling, clustered patterns, and covariate-based modeling |
| Provides a framework-guided decision tab | Brings the article-based selection logic directly into the plugin interface |

---

## Methods Included

<table>
  <tr>
    <td><strong>Deterministic</strong></td>
    <td>IDW, optimized IDW, Thin Plate Spline (TPS)</td>
  </tr>
  <tr>
    <td><strong>Geostatistical</strong></td>
    <td>Ordinary Kriging, MoM variogram fitting, REML-assisted kriging</td>
  </tr>
  <tr>
    <td><strong>Machine Learning</strong></td>
    <td>Random Forest, Support Vector Machine</td>
  </tr>
  <tr>
    <td><strong>Hybrid</strong></td>
    <td>Regression Kriging</td>
  </tr>
</table>

---

## Framework Guidance

The Framework tab translates the method-selection logic from the reference article into an interactive QGIS workflow. It considers sample size, spatial pattern, covariate availability, validation performance, and interpolation purpose.

### Univariate Framework

Use this workflow when interpolation is based mainly on the target variable sampled in the field.

<p align="center">
  <img src="bestfitinterpolator/framework_univariate.png" alt="Univariate interpolation framework" width="920">
</p>

### Full Framework With Covariates

Use this workflow when auxiliary raster layers or environmental covariates are available for machine-learning or hybrid modeling.

<p align="center">
  <img src="bestfitinterpolator/framework_full.png" alt="Full interpolation framework with covariates" width="920">
</p>

---

## Main Features

| Data and Diagnostics | Validation and Maps | Reporting |
| --- | --- | --- |
| Point sample reading | LOOCV and K-fold validation | Framework report preview |
| Variable selection | RMSE, RMSE %, MAE, Pearson r, R², LCCC | PDF report export |
| Polygon boundary support | Observed-vs-predicted plots | Article citation included |
| Pixel size control | Interpolation raster generation | Visual framework figures |
| Moran's I support | Semivariogram preview | Method-selection summary |

---

## Typical Workflow

```text
1. Select point layer, variable, polygon boundary, and pixel size.
2. Inspect data diagnostics and spatial behavior.
3. Review semivariogram and framework guidance.
4. Validate candidate methods.
5. Compare metrics and observed-vs-predicted plots.
6. Generate the final interpolation map.
7. Export a report when needed.
```

---

## Version 1.1

- Keeps the Framework semivariogram preview synchronized with the active Geostatistics model.
- Prevents interpolation when the point and polygon layers have incompatible CRS or no usable spatial overlap.
- Uses popup windows for warnings and errors while keeping routine information in the QGIS message bar.
- Shows incomplete-data warnings only once per selected layer and variable.
- Fixes TPS interpolation routing and the REML prediction matrix error.
- Standardizes R² labels and explains when automatic validation changes from LOOCV to K-fold.
- Adds an About tab with version, authors, manual, article, GitHub, Issues, email, and LinkedIn links.

---

## Installation

### From the QGIS Plugin Repository

1. Open **Plugins > Manage and Install Plugins** in QGIS.
2. Search for **Best Fit Interpolator**.
3. Select the plugin and click **Install Plugin**.

### From a ZIP release

1. Download the plugin ZIP from the [latest GitHub release](https://github.com/ladelgadobe/BestFitInterpolation/releases/latest).
2. In QGIS, open **Plugins > Manage and Install Plugins > Install from ZIP**.
3. Select the downloaded ZIP and click **Install Plugin**.

Machine-learning and hybrid methods require additional Python packages. If they
are not already available, the plugin asks for permission to install them into
its local `_deps` directory the first time one of these methods is used. This
step requires an internet connection but does not require administrator access.

Developers can also clone this repository and copy the `bestfitinterpolator`
folder into their QGIS plugins directory.

Typical QGIS plugin directory on Windows:

```text
C:\Users\<user>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

---

## Authors and Contact

<table>
  <tr>
    <td><strong>Laura Delgado Bejarano</strong></td>
    <td><a href="https://www.linkedin.com/in/laura-delgado-bejarano-09b6681a2/">LinkedIn</a></td>
  </tr>
  <tr>
    <td><strong>Lucas Rios do Amaral</strong></td>
    <td><a href="https://www.linkedin.com/in/lucas-rios-do-amaral-bb302449/">LinkedIn</a></td>
  </tr>
</table>

Contact: [ladelgadobe@unal.edu.co](mailto:ladelgadobe@unal.edu.co)

---

## Cite this article

If you use this plugin in academic work, please cite the reference article. Expand a citation style below, then use the copy button in the citation box.

<details open>
<summary><strong>APA 7th edition</strong></summary>

```text
Delgado Bejarano, L., Loureiro Gonçalves Oliveira, A., Fiolo Pozzuto, J. V., Castañeda Sánchez, D., & Rios do Amaral, L. (2026). Performance of interpolation methods in digital soil mapping: The influence of data characteristics. Precision Agriculture, 27(1), Article 10. https://doi.org/10.1007/s11119-025-10311-8
```

</details>

<details>
<summary><strong>Vancouver</strong></summary>

```text
Delgado Bejarano L, Loureiro Gonçalves Oliveira A, Fiolo Pozzuto JV, Castañeda Sánchez D, Rios do Amaral L. Performance of interpolation methods in digital soil mapping: the influence of data characteristics. Precision Agriculture. 2026;27(1):10. doi:10.1007/s11119-025-10311-8.
```

</details>

<details>
<summary><strong>ISO 690</strong></summary>

```text
DELGADO BEJARANO, Laura; LOUREIRO GONÇALVES OLIVEIRA, Agda; FIOLO POZZUTO, João Vitor; CASTAÑEDA SÁNCHEZ, Dario; RIOS DO AMARAL, Lucas. Performance of interpolation methods in digital soil mapping: the influence of data characteristics. Precision Agriculture, 2026, vol. 27, no. 1, article 10. DOI 10.1007/s11119-025-10311-8. Available at: https://doi.org/10.1007/s11119-025-10311-8.
```

</details>

<details>
<summary><strong>ABNT NBR 6023:2018</strong></summary>

```text
DELGADO BEJARANO, Laura; LOUREIRO GONÇALVES OLIVEIRA, Agda; FIOLO POZZUTO, João Vitor; CASTAÑEDA SÁNCHEZ, Dario; RIOS DO AMARAL, Lucas. Performance of interpolation methods in digital soil mapping: the influence of data characteristics. Precision Agriculture, v. 27, n. 1, art. 10, 2026. DOI: https://doi.org/10.1007/s11119-025-10311-8.
```

</details>

### Download citation files

[Download BibTeX (.bib)](CITATION.bib) | [Download RefMan / RIS (.ris)](CITATION.ris) | [Open the article DOI](https://doi.org/10.1007/s11119-025-10311-8)

GitHub also provides its native **Cite this repository** option from [`CITATION.cff`](CITATION.cff).

---

<div align="center">

**Best Fit Interpolator**  
Spatial interpolation support for digital soil mapping and precision agriculture.

</div>
