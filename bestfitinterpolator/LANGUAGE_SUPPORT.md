# Interface languages — version 2.1

Choose **English**, **Español** or **Português** in the upper-right corner of the plugin window. Portuguese uses Brazilian scientific terminology. The first opening follows the QGIS language when supported, with English as the fallback. A manual selection is saved under the plugin's own `BestFitInterpolator/language` preference and persists when the plugin is reopened.

The selector updates the plugin interface, help texts, dialogs, plots, Framework flowchart and newly generated reports. Translations are bundled in the ZIP and do not require an internet connection or a translation service. A request received during a calculation is applied when the plugin's active jobs finish.

Changing language preserves loaded data, selected methods, hyperparameters, validation results and generated rasters. Fixed combo-box choices keep their English source identifiers in a separate Qt item role; calculations use those identifiers independently of their displayed translation. File paths, layer and field selectors, numerical values, scientific symbols and method abbreviations retain their meaning. Bibliographic citations and external reference documents retain their original language. Unrecognized messages from third-party components fall back to their original text.

New report exports use the selected language. Already exported files are retained. CSV/JSON parameter identifiers remain stable for reproducibility. Reports and plots translate presentation text without rewriting the completed execution's parameter snapshots or numerical arrays.

`localization.py` provides a plugin-scoped Qt translator, presentation-call registration and language controller. `i18n/catalog.json` contains English source strings and Spanish/Portuguese translations. `{p0}`, `{p1}`, etc. represent protected formatted values. New interface strings should be added to both catalogs; use `_new`/`_ui` for presentation text and `_combo_text`, `_item_text`, `_find_text`, `_select_text` or `_tab_text` when reading fixed controls for program logic. User-supplied names should bypass translation. No application-wide Qt translation or QGIS locale change is installed.
