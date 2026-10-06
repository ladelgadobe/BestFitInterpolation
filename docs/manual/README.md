# Best Fit Interpolator user manual

The editable source for the current user manual is `main.tex`. The published
PDF has the stable repository-root filename `BestFitInterpolator_User_Manual.pdf`.
The README and the plugin's About metadata use that same name. The review date
belongs in the document; filenames do not carry a plugin release number.

The original project remains editable in
[Overleaf](https://www.overleaf.com/project/6a3d70b58524f4f5b382db3e).
Select `main.tex` as the main document and compile with pdfLaTeX. For a local
installation with TeX available, run `latexmk -pdf main.tex` in this directory.
The graphic search path allows images in `figures/` locally or in the Overleaf
project root, while retaining the existing logos and framework diagrams.

All plugin interface screenshots were captured from the updated plugin in
QGIS 4.2.3 using the original Paulínia study inputs: 114 soil observations,
the Clay attribute, the original boundary, ECa, elevation and NDCI, EPSG:32723,
and 5 m output pixels. These are actual plugin calculations with unchanged
measurements, rather than synthetic maps. Example parameters illustrate the
controls; they are not a reproduction of the published experiment or a claim
that those parameters are optimal. Study source files are not redistributed
with the manual.

`figure_provenance.json` records the environment, input hashes and figure
hashes. The original Quick Start Workflow, research-framework diagrams and
logos remain unchanged. The dense/massive workflow follows the original Quick
Start style: Arial, thin outlined cards, blue and green branches, circular step
numbers and yellow notes. Its editable SVG and Pillow renderer are in
`diagrams/`. Run `python diagrams/render_dense_massive_workflow.py` with Pillow
and Arial available to regenerate the SVG and referenced high-resolution PNG.
Old interface and
installation images are no longer referenced by the document.

When updating the manual, refresh the affected interface screenshots from a
coherent study session, match labels and button names to the current plugin,
compile the source, resolve references, and visually inspect every PDF page.
Check the MoM/REML distinction, outlier decisions, validation strategy, executed
interpolation provenance, map difference direction, and dense/massive processing
limits against the implementation before changing those explanations.
