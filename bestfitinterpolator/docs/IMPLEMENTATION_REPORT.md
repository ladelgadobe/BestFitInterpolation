# Best Fit Interpolator informe de desarrollo

Entrega incremental del 3 de octubre de 2026 sobre `local_build_v1_2_20260902/bestfitinterpolator`.
El código entregado está en `development_20261002/bestfitinterpolator`. Se conserva la copia base y se crea un ZIP nuevo; la instalación anterior está respaldada. No se ha publicado esta entrega. La revisión vigente se detalla en [UI_REVISION_REPORT.md](UI_REVISION_REPORT.md).

**Did any mathematical behavior change? NO**, para los métodos existentes con los mismos datos, parámetros, políticas y dependencias. Se añaden cálculos diagnósticos y una diferencia de ráster que antes no existían. Una decisión explícita **Exclude** cambia los datos de entrada de los modelos; cambiar parámetros avanzados cambia su configuración. Las correcciones de estado impiden presentar resultados de una configuración anterior como actuales. Estas diferencias de entrada/estado son intencionales y visibles; no se cambian las ecuaciones, métricas, semillas, criterios de selección ni perfiles de procesamiento existentes.

La equivalencia numérica comprobada corresponde al entorno local; no implica identidad binaria entre versiones diferentes de SciPy, NumPy o scikit-learn.

## 1. Initial architecture found

La clase principal carga la interfaz Designer y coordina Data, métodos determinísticos y validación. El dispatcher escoge el controlador MoM/REML de Geostatistics. Machine Learning y Regression Kriging tienen controladores propios. Framework ya dispone de `FrameworkDataState`, decisión, validación, despacho y figuras. Las funciones numéricas, políticas de rendimiento, validación, construcción de grillas y semivariogramas son reutilizables. La auditoría previa y los resultados iniciales se conservan en `AUDIT.md`.

## 2. Bugs identified

Se encontraron referencias del controlador OK al diálogo anterior, señales de controladores descartados todavía conectadas, canvases sin comprobación del objeto C++ subyacente, parámetros de lag/cutoff con resultados experimentales y validaciones obsoletas, errores de ciclo de vida ocultos y contenido distinto entre vista previa y PDF. También faltaba invalidar los modelos al editar atributos o geometrías de la misma capa.

## 3. Geostatistics bug root cause

`run()` creaba un diálogo nuevo mientras `ok_ctrl` podía conservar el anterior. El dispatcher desactivaba el controlador viejo, pero no desconectaba todas sus señales. Así podían ejecutarse slots sobre widgets invisibles o destruidos, reutilizando también arrays y validaciones anteriores. La combinación explica que abrir Geostatistics de nuevo dependiera de reiniciar el plugin.

## 4. Geostatistics fix

Se reutiliza el diálogo mientras permanece abierto. Al cerrar, se cancelan tareas, se desconectan señales y se marca el reinicio; la siguiente apertura destruye el diálogo anterior y crea una sesión limpia en Data. Cuando hace falta sustituir un controlador, se desconectan solamente sus conexiones, se detienen sus temporizadores y tareas y se liberan sus canvases. Los slots comprueban actividad y vida del diálogo mediante SIP. Se registran excepciones relevantes en el log de Python y en QGIS. Cambios de capa, variable, atributos, geometría y CRS invalidan los estados correspondientes.

La integración ejecutada comprueba tres reaperturas, cambios de pestaña, dataset A → B, REML → MoM, edición de la misma capa y retorno a Geostatistics después de IDW, OK, RF y RK.

## 5. Semivariogram verification

Cutoff, distancia de lag y número de lags invalidan el semivariograma y su validación. Un temporizador breve agrupa cambios de controles y actualiza el experimental. Los parámetros aplicados manualmente se conservan durante ese recálculo. La ventana avanzada rechaza resultados de tareas cuyo conjunto de datos o configuración haya cambiado.

Los perfiles `ok_mom`, `ok_reml`, `residual`, `framework` y `framework_sdi` conservan sus heurísticas originales, incluido el pequeño límite diferente de Framework SDI. OK mantiene LCCC/RMSE/R²; RK mantiene RMSE/SSE. Hay comparación numérica con tolerancia cero de ajustes y validaciones MoM, REML real y residuales.

## 6. Files created

Se añaden módulos pequeños al paquete existente: `compat.py`, `theme.py`, `async_jobs.py`, `diagnostics_engine.py`, `diagnostics_ui.py`, `diagnostics_table.py`, `diagnostics_plot.py`, `semivariogram_engine.py`, `semivariogram_dialog.py`, `map_controls.py`, `map_comparison.py`, `map_comparison_ui.py`, `report_model.py`, `report_builder.py`, `ui_refinement.py` e `interpolation_result.py`.

Se añaden cinco archivos de pruebas: `test_development_diagnostics.py`, `test_development_maps_reports.py`, `test_development_numerical_baseline.py`, `test_development_tasks.py` y `test_development_ui_refinement.py`. El inventario completo con hashes está en `CHANGE_INVENTORY.md` y `BUILD_MANIFEST.json`.

## 7. Files modified

La coordinación principal, dispatcher, ambos controladores OK, RK, lectores ML y Framework se adaptan al ciclo de vida, máscara y componentes compartidos. `mpl_compat.py`, notificaciones, bootstrap de dependencias, vistas de Framework y metadatos incorporan adaptadores de compatibilidad y estilo. Se corrigen pruebas antiguas que no cargaban y contratos de presentación que apuntaban a implementaciones movidas.

`CHANGE_INVENTORY.md` enumera todos los archivos creados, modificados y retirados respecto a la base. Las funciones matemáticas de nueve módulos centrales mantienen el mismo AST; cambiar imports Qt o comentarios no modifica esas funciones.

## 8. UI/theme changes

La paleta central utiliza azul oscuro, turquesa y naranja del icono existente. La revisión vigente usa superficies neutras y radios moderados. IDW/TPS y los dos paneles de RK tienen bordes discretos para distinguir sus opciones. `InfoButton` dibuja el icono con QPainter. El branding repetido de las figuras está desactivado por defecto; el logo se conserva en About y en la cabecera del informe.

Los controles compartidos se abren desde el engranaje del mapa en un popup: escala 1:n, Fit to layer, ocho paletas con gradientes visibles y rango automático/manual. Los gráficos de validación conservan colores científicos fijos y no muestran ajustes de paleta, tampoco en Larger View. Larger View conserva y sincroniza la configuración del mapa. La escala numérica requiere CRS proyectado con unidades lineales conocidas. Turbo utiliza Viridis como fallback en Matplotlib que no lo incluye.

Run Random Forest aparece únicamente en Interpolation. RF y kriging residual se mantienen uno al lado del otro en RK, con estado legible en su propia fila, opciones de búsqueda visibles solo en Grid search y el botón Interpolate fuera del scroll. Las figuras copiadas normalizan DPI y transformación física; los dibujos temporales de exportación no sustituyen la vista activa ni fuerzan el tamaño mínimo del diálogo.

## 9. Spatial Diagnostics implementation

Se abre desde **Data → Outlier diagnostic**, sin pestaña principal nueva. Integra mapa, histograma, boxplot, estadísticas, tabla de 19 columnas, selección sincronizada y decisiones Keep/Exclude/Reset. Los IDs son los IDs originales de las features, antes de deduplicar o validar.

El icono de información abre con clic una ventana redimensionable con secciones, texto seleccionable y scroll. Resume cómo funcionan los métodos, las clases HL/LH/HH/LL/NS, los parámetros generales y el flujo Run/selección/Keep/Exclude/Reset; reserva la explicación completa para el manual. Se reutiliza al volver a pulsarlo y se cierra al salir de diagnósticos.

`DiagnosticsState` mantiene valores originales, resultados, decisiones y `analysis_mask`. Las banderas nunca excluyen automáticamente. Los valores/coordenadas no finitos conservan clasificación Missing/Invalid. La máscara se aplica a los lectores de Data/OK/ML/RK/Framework y, por tanto, a sus validaciones e interpolaciones. El informe declara el número utilizado y las exclusiones; no se edita la capa original.

## 10. Global Moran implementation

El Global Moran existente de Data/Framework se conserva con sus políticas anteriores. El nuevo submódulo también muestra un Global Moran diagnóstico con la vecindad y permutaciones seleccionadas: un resultado global, claramente separado de las clases individuales. No sustituye ni altera las decisiones anteriores de Framework.

Las ponderaciones se estandarizan por fila y las permutaciones globales reordenan el vector completo. La multiplicación utiliza una matriz dispersa; existe alternativa NumPy si SciPy no está disponible.

## 11. Anselin Local Moran implementation

Se calcula `I_i = (x_i - mean) * lag_i / m2`, con `m2 = sum((x - mean)^2) / n` y pesos binarios estandarizados por fila. La aleatorización condicional mantiene el valor focal y toma vecinos sin reemplazo entre los demás puntos. El pseudo p usa la cola empírica plegada con corrección +1; no es un p ajustado por comparaciones múltiples. Se documenta esta convención; no se afirma identidad de magnitudes con bibliotecas que usan el momento muestral n−1.

Defaults: KNN 8, 499 permutaciones, seed 42 y alpha 0.05; también 99/999 y umbral de distancia en unidades del CRS. HH/LL significativos son clusters; solamente HL/LH significativos se marcan como potenciales outliers espaciales. Islas, variables constantes y permutaciones degeneradas permanecen NS. Se presentan vecinos min/media/max e islas, mediana local, residual local y desviación robusta local.

## 12. Statistical outlier implementation

IQR/Tukey usa k=1.5; MAD usa modified Z con umbral absoluto 3.5; Z clásico opcional usa 3. IQR y MAD son los métodos iniciales. Con MAD=0, valores iguales a la mediana puntúan cero y los diferentes tienen desviación infinita para revisión explícita.

El consenso permite Any, All o At least N entre métodos seleccionados, con banderas individuales y votos. Las clases combinadas separan Normal, Statistical only, Spatial only, Statistical + Spatial, HH cluster, LL cluster y Missing/Invalid.

## 13. Regression Kriging semivariogram integration

**Adjust semivariogram** abre el componente compartido de ajuste y validación de residuales. Se ha retirado el botón adicional Advanced Semivariogram de OK y RK para evitar duplicar el flujo existente. Expone cutoff, distancia/número de lags, candidatos, preview, validación y aplicación manual en una única ventana. El engine utiliza el perfil residual existente; no reemplaza su criterio por el de OK.

La integración local ejecuta regresión RF, ajuste residual, interpolación RK y CV. Se comparan además los tres ajustes residuales y sus métricas con las funciones originales.

## 14. Map Comparison implementation

Está en **Framework → Comparison**. La tabla y los selectores muestran todas las alternativas realmente validadas. Compare maps genera los mapas que falten; estas ejecuciones independientes no sustituyen el resultado final. Rango, paleta y extensión compartidos están activados inicialmente; se pueden desactivar para comparar representaciones independientes.

Se registra el resultado realmente generado por las rutas RF/SVM y el ID de su capa. Al cambiar métodos se descartan referencias de ejes anteriores para no heredar límites 0–1 que ocultaban mapas en coordenadas proyectadas. La integración verifica mapas TPS/SVM, TPS/RF y TPS/RK con una covariable GeoTIFF real y la extensión completa de cada grilla.

La comparación verifica CRS, dimensiones, transformación afín y alineación. Grillas incompatibles producen un mensaje explícito; no se remuestrean. Se escribe un GeoTIFF Float64 con **A − B**, en bloques, excluyendo NoData/máscaras/no finitos de ambos mapas. Media, mediana exacta, mínimo, máximo y conteo utilizan todos los píxeles comunes. El preview puede tomar cada N píxeles de forma declarada; sus extremos visuales usan la grilla completa, no la muestra del preview.

La diferencia utiliza una paleta divergente centrada en cero. Hay pan/zoom, Fit, escala y opción explícita de inclusión en el informe. Cambiar métodos invalida una comparación anterior.

## 15. Report Builder implementation

**Framework → Report** muestra un resumen navegable de la sesión: Overview, Validation, Interpolation y Diagnostics. Los enlaces llevan a las pestañas correspondientes. **PDF preview / options** captura un `ReportState` de datos, tablas y figuras. Conserva el contenido técnico anterior como secciones obligatorias y permite escoger figuras y diagnósticos disponibles. Incluye opciones para diagnósticos/outliers, Global Moran, LISA/distribuciones, metodología y comparación de mapas cuando se autorizó su inclusión.

**Export HTML** produce un documento portable con navegación, secciones desplegables e imágenes incorporadas, sin dependencias de archivos temporales ni recursos externos. El resultado ejecutado en Framework está separado del recomendado, del seleccionado para la próxima ejecución y de las ejecuciones independientes; abrir Framework no reutiliza un mapa de RK/RF/SVM ejecutado en otra pestaña. Las figuras del informe corresponden a esa misma captura de Framework.

Preview paginado y PDF usan el mismo documento/renderizador, A4, márgenes, tipografía, captions, icono y números de página. Los encabezados y la tabla de validación se mantienen juntos. La sesión ejecutada genera dos PDF y dos previews consecutivos. El PDF de QA es un estudio sintético con todas las figuras disponibles; contiene resultados reales de esa sesión y los campos no calculados figuran como Pending. Las figuras se exportan mediante una función común que incluye el branding completo en el bounding box y respeta su desactivación.

El informe es una captura: cerrar y volver a abrir Report Builder obtiene los resultados actuales. Cambiar opciones del documento no vuelve a ajustar modelos.

## 16. QGIS compatibility changes

Se usan `qgis.PyQt`, detección de enums scoped/legacy, QAction en QtGui/QtWidgets, `exec`/`exec_`, interfaces de impresión y enums de QGIS para geometría/unidades. Matplotlib prueba QtAgg y después Qt5Agg. Las dependencias ML se acotan según Python antiguo sin cambiar las dependencias ya usadas en el entorno moderno.

Se revisa sintaxis con el parser de Python 3.7 y se comprueba que las anotaciones nuevas de la base usan `from __future__ import annotations`. Los adaptadores no certifican runtimes ausentes. `qgisMinimumVersion=3.14` y `qgisMaximumVersion=4.99` expresan elegibilidad en metadatos, no una prueba de ejecución. El paquete conserva version=1.2 y se identifica como desarrollo por su nombre y documentación.

## 17. QGIS 3.14 compatibility status

**statically reviewed / not tested**. No está instalado. Se revisan Python 3.7, Qt5, backend antiguo, enums legacy, comparaciones NumPy con NaN y versiones instalables de dependencias. Quedan pendientes carga real, UIC/resources, cálculos, tareas y exportación PDF con el runtime distribuido por esa versión.

## 18. QGIS 3.22/3.28 compatibility status

**statically reviewed / not tested** para ambas versiones. Igual estado para 3.34. Se conservan APIs de QGIS 3 y fallback Qt5; cada distribución tiene que comprobarse con sus propias versiones de Python, GDAL, Matplotlib y sklearn. Ver `COMPATIBILITY_MATRIX.md`.

## 19. QGIS 3.44 compatibility status

**tested**, específicamente QGIS **3.44.8-Solothurn**, Windows, Python 3.12, Qt 5.15.13, NumPy 2.4.2 y SciPy 1.17.0. Se ejecutan 100 pruebas aprobadas, cero fallos, y una sesión integral con objetos reales de QGIS/Qt en modo offscreen e interfaz de QGIS simulada. No equivale a un ensayo manual exhaustivo dentro del perfil de producción del usuario. La instalación anterior está respaldada y la actualización local se registra en INSTALLATION_RECORD.json.

## 20. QGIS 4.0 compatibility status

**statically reviewed / not tested**. Se han preparado importaciones, enums, QAction, diálogos, impresión y backend Qt6. No hay QGIS 4/Qt6 local; siguen pendientes la carga completa, recursos/UIC, tareas, APIs QGIS y salidas gráficas en ese runtime. No se declara compatibilidad físicamente probada.

## 21. Tests added

Pruebas sintéticas de extremos, consenso, MAD=0, constantes, missing, coordenadas duplicadas, muestras pequeñas, HH/LL/HL/LH, clases combinadas, islas, reproducibilidad y decisiones. Casos de grilla idéntica, signo A−B, NoData, CRS/alineación/dimensiones incompatibles, extrema fuera del preview y estadísticas completas. Pruebas de control visual que conserva píxeles y máscaras. Preview/PDF/secciones opcionales, enums, dependencias por Python y transporte/cancelación de QgsTask.

La integración comprueba ventanas repetidas, selección, exclusiones, edición de capas, validación/aplicación avanzada, rechazo de estado obsoleto, mapas generados, estilos/extensión compartidos, dos informes y ausencia de excepciones de slots o avisos inesperados.

## 22. Regression tests

La base inicial dio 60 pruebas aprobadas y tres errores de importación en pruebas antiguas. La batería final da **100 aprobadas / 0 fallos**. La prueba que provoca una excepción deliberada verifica transporte/logging del error; su traceback esperado no es un fallo de la batería. `TEST_RESULTS.json` registra el runtime y la fecha de la ejecución; también se comprueba que el branding exportado no quede recortado y que su desactivación persista. La sesión incluye SVM y OK con validación, Comparison con seis métodos y la correlación editable de Full Covariates, incluida su barra de colores. Las nuevas comprobaciones cubren separación de resultados independientes/Framework, ausencia de paletas en validación, HTML portable y escalado físico con ratios de píxel 1, 1.5 y 2.

Se comparan los ajustes y CV MoM de ambos perfiles, una validación REML real, los tres ajustes/CV de residuales y heurísticas de Framework/SDI con la base original, con rtol=0 y atol=0. Se comparan AST de las funciones centrales de IDW, TPS, OK, REML, RF, SVM, rendimiento, validación y variograma. Los contratos existentes de decisión, perfiles densos y rutas se conservan. Estas comprobaciones son amplias pero no cubren cada dataset ni cada combinación de hiperparámetros.

## 23. Performance optimizations

Las nuevas permutaciones, previews/validación avanzada y comparación se ejecutan mediante QgsTask con arrays capturados en la GUI; los workers numéricos no tocan widgets ni capas vivas. Las tareas se cancelan al cerrar y sus resultados se comprueban antes de aplicarlos.

Se cachean vecinos y permutaciones independientemente de alpha/umbrales; cambiar paleta/rango/escala solo cambia representación. Hay índices espaciales, pesos dispersos y alternativa indexada por celdas para distancias sin SciPy. La tabla Qt evalúa las celdas bajo demanda. La diferencia de ráster usa bloques de 128 filas, valores finitos empaquetados en memmap para la mediana exacta y previews acotados. Los scatter grandes se rasterizan conservando todos los puntos.

## 24. Known limitations

- Solo se ejecutó QGIS 3.44.8. QGIS 3.14/3.22/3.28/3.34/4.x y otros sistemas operativos requieren ensayos reales. Como la base, la entrega necesita NumPy >=1.17 para mantener el mismo generador aleatorio `default_rng`.
- Los workflows anteriores de interpolación y captura/exportación de figuras de informe conservan su progresión en la GUI. Algunos ajustes largos o informes con muchísimas filas pueden seguir provocando pausas dentro de esas etapas; no se trasladan objetos Qt/QGIS a workers inseguros. Las nuevas operaciones numéricas costosas sí están separadas.
- No se realizó un benchmark completo de LISA con 10.000+ puntos ni de informes con millones de observaciones. Una vecindad de distancia casi completa puede ser grande; 999 permutaciones cuestan más que 99/499. La mediana exacta requiere disco temporal proporcional a los píxeles y su partición no se interrumpe a mitad de la llamada NumPy.
- Los pseudo p locales no llevan ajuste FDR; el informe lo declara. La distancia utiliza unidades del CRS; grados no equivalen a una distancia métrica. Para escala 1:n se requiere CRS proyectado.
- Decisiones y capturas se conservan dentro de la sesión del plugin, no como campos modificados ni como persistencia nueva en el proyecto QGIS.
- Los rásteres de diferencias e imágenes de captura usan archivos temporales; el PDF incorpora sus imágenes. La disponibilidad futura de un archivo temporal no debe tratarse como almacenamiento permanente.
- No se instalaron dependencias ni se publicó una versión. Se actualizó el plugin del perfil default conservando una copia de seguridad de los archivos reemplazados. El ZIP es una entrega de desarrollo para revisión/pruebas y QGIS debe reiniciarse para cargar los módulos actualizados.

Los comandos reproducibles y el checklist de versiones se encuentran en `COMPATIBILITY_MATRIX.md`. `BUILD_MANIFEST.json` registra los archivos de la entrega y la base usada por las pruebas.
