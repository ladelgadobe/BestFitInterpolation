# Revisión de interfaz Best Fit Interpolator

Entrega actualizada al 5 de octubre de 2026. Refinamiento incremental de los widgets y controladores existentes. Se conserva la base local 1.2; la revisión se empaqueta con un nombre nuevo y la instalación anterior se guarda en una copia de seguridad. El informe de compatibilidad actual registra la matriz ejecutada en nueve versiones de QGIS.

**Did any mathematical behavior change? NO.** Esta revisión modifica presentación, layouts, ciclo de vida y procedencia de resultados. Conserva ecuaciones, interpoladores, semillas, métricas, reglas de selección y parámetros automáticos. Las decisiones explícitas Exclude siguen cambiando solamente los datos de entrada, sin eliminar features de la capa original.

## Cambios solicitados

| Solicitud | Comportamiento final |
|---|---|
| 1. Dirección visual | Fondos claros, contenedores sin marcos clásicos, radios moderados y tipografía legible; estructura de pestañas conservada. |
| 2. Identidad | Colores del logo en acciones principales, selección, iconos y pestañas activas. |
| 3. Indicadores | Progreso discreto con el gradiente de identidad; sin barras adicionales que amplíen la ventana. |
| 4. Tamaño | Tamaño inicial ajustado a pantalla, mínimo controlado y scroll interno; la validación no fuerza crecimiento externo. La ventana Full Covariates también se ajusta a pantalla y permite reducirla a 640×480. |
| 5. Configuración | Engranaje en la esquina de mapas; controles en popup, sin barras permanentes. Los gráficos de validación, sus Larger View y la ventana de validación de semivariogramas no tienen paleta. |
| 6. Paletas | Ocho paletas estándar con gradientes reales: Viridis, Plasma, Inferno, Magma, Cividis, Turbo, Spectral y RdYlGn. Se conserva una paleta previa diferente cuando corresponde. |
| 7. Larger View | Copia de los mismos artistas, datos, máscaras, normalización y límites. Cambios de paleta/rango se sincronizan desde el popup compartido, incluida la barra de colores. La correlación de Full Covariates conserva datos escalares editables. El tamaño de render se adapta al canvas ampliado. |
| 8. Información | Iconos generados con QPainter, independientes de fuentes y rutas externas; SDI y RK también usan la iconografía común. |
| 9. Logo | Se desactiva la marca repetida en figuras; About muestra el logo ampliado de 64 a 144 px lógicos, conservando proporción y nitidez en pantallas de alta densidad. También permanece en la cabecera del informe técnico. |
| 10. IDW | Grupo exclusivo de Automatic/Manual/TPS; vecinos y potencia quedan desactivados inmediatamente en Automatic y TPS. IDW y TPS tienen bordes discretos independientes. |
| 11. Geostatistics | Sin botón duplicado Advanced Semivariogram; se mantiene el flujo existente de parámetros y View validation. |
| 12. RK | RF y kriging de residuales lado a lado. Manual muestra los parámetros pertinentes; Grid search muestra rangos, pasos y búsqueda. Adjust semivariogram abre la ventana compartida de distancia, lags, preview y validación. Interpolate permanece en el pie, fuera del scroll. |
| 13. Validation | Canvases con hints estables y resultados dentro del espacio disponible; validación repetida no cambia el tamaño exterior. |
| 14. Interpolation | Se retiran el título Report y los controles PDF del panel antiguo. Report tiene un resumen navegable, enlaces al workflow, opciones PDF y View HTML. El HTML abre automáticamente como archivo temporal en el navegador, sin solicitar descarga, con enlaces funcionales y secciones que se pueden cerrar, expandir y colapsar. |
| 15. Comparison | Solo comparación espacial con selectores de todas las alternativas válidas. La tabla de resultados y métricas permanece en Validation. |
| 16. Método ejecutado | Registro explícito e inmutable de método, parámetros, ráster, capa e ID de ejecución. Framework comienza sin mapa y solo publica ejecuciones iniciadas allí. Interpolar desde RK/ML/Deterministics o comparar otro método no reemplaza el resultado final de Framework. |
| 17. Botones | Acciones principales con acento turquesa; acciones secundarias suaves; engranajes e información compactos. Run Random Forest aparece solo en Interpolation; Validation conserva su botón CV. |
| 18. Espaciado | Márgenes y separación consistentes; desaparecen las cajas pesadas y las barras de configuración bajo los gráficos. |
| 19. Lógica científica | Sin cambios de algoritmos. Las comprobaciones numéricas contra la base siguen aprobadas. |
| 20. Refinamiento | Se reutilizan widgets, señales y controladores; la adaptación de layouts reside en ui_refinement.py. |
| 21. Resultado visual | Interfaz nativa Qt clara, neutra y con acentos de identidad; sin paneles completos de colores intensos. |
| 22. Revisión final | Capturas reales de Data, Deterministics, Kriging, ML, RK y cada sección de Framework; revisión a 1000×700 y 800×600. |
| Reset al cerrar | Cancelación de tareas, cierre de ventanas dependientes y desconexión de señales. La reapertura crea un diálogo nuevo, activa Data y limpia selecciones, configuraciones, validaciones, modelos y diagnósticos de sesión. |
| Outlier diagnostic | Acceso junto a las entradas de Data: Outlier diagnostic; Global Moran, Anselin Local Moran/LISA, IQR/MAD/Z y decisiones Keep/Exclude/Reset. Analysis settings abre sus parámetros en una ventana compacta. El info se abre con clic y resume funcionamiento, HL/LH/HH/LL/NS, vecindad, permutaciones, seed, alpha, umbrales, consenso y uso; el detalle se remite al manual. La ventana permite seleccionar texto y usar scroll, permanece abierta hasta cerrarla y se cierra al salir de diagnósticos. |
| Nombres limpios | Títulos, botones, pestañas, menús de gráficos, ventanas ampliadas e informe sin puntos suspensivos ni guiones decorativos. Los nombres largos de los gráficos usan saltos de línea en lugar de truncarse con puntos. |

## Verificación ejecutada

- **104 pruebas aprobadas, cero fallos**, en QGIS 3.44.8, Qt 5.15.13, Python 3.12.13, Windows. TEST_RESULTS.json registra hashes del código y de los assets usados.
- Sesión integral en QGIS/Qt reales, modo offscreen y perfil aislado: cinco ciclos de cierre/reapertura, cambio de datos y MoM/REML, edición de la capa, diagnósticos y decisiones, interpolación/validación IDW/TPS/OK/RF/SVM/RK, comparación espacial y dos PDFs con preview. Los selectores de Comparison ofrecen los seis métodos realmente validados; las métricas permanecen en Validation.
- Full Covariates probado con un ráster real de la sesión: correlación escalar, paleta/barra de colores coherentes, Larger View y ventanas de 760×540/640×480. Una prueba verifica que cambiar colores y rango de la copia no modifica datos, máscaras, normalización ni artistas de la figura original.
- Revisión de todas las pestañas y comprobación del tamaño exterior después de validar, navegar y abrir vistas ampliadas. En ventanas pequeñas, los contenidos extensos usan scroll; los botones principales quedan accesibles y RK conserva su acción en el pie.
- Larger View comprobada con datos enmascarados, límites manuales, colormap y normalización. Cambiar Magma → Plasma conserva los datos y los límites −2/4.
- Caso de procedencia: TPS interpolado, IDW seleccionado/recomendado después, comparación IDW independiente. El resultado final, el informe, la capa QGIS y el GeoTIFF continúan indicando TPS.
- Correcciones reproducidas con covariable real: TPS/SVM, TPS/RF y TPS/RK generan mapas alineados y muestran su extensión completa. Las rutas ML de Framework registran su ráster; cambiar de métodos limpia los ejes anteriores para evitar heredar límites 0–1 y mostrar mapas vacíos.
- Escalas de píxeles 1, 1.5 y 2: canvas y figura mantienen dimensiones coherentes. Se corrige la transformación física conservada por deepcopy aunque Figure restablece su DPI. Los draws temporales de exportación no sustituyen el mapa visible ni su vista ampliada.
- Report se revisa en sus cuatro secciones. HTML exportado desde el widget incluye navegación, secciones desplegables e imágenes incrustadas, sin depender de rutas temporales locales. El PDF mantiene su configuración y preview existentes.
- UI_SESSION_RESULTS.json conserva las comprobaciones y hashes de la sesión. Capturas en qa/ui_revision; PDFs y previews sintéticos en qa.

## Archivos y límites

Cambios principales: theme.py, map_controls.py, mpl_compat.py, larger_view.py, ui_refinement.py, interpolation_result.py, BestFitInterpolator.py, diagnostics_ui.py, framework_tab.py, map_comparison_ui.py y los puntos de integración de cada controlador. Inventario completo y hashes en CHANGE_INVENTORY.md y BUILD_MANIFEST.json.

La revisión visual detallada se limita al runtime local QGIS 3.44.8. La matriz funcional adicional ejecutó QGIS 3.14, 3.16, 3.22, 3.28, 3.34, 3.40, 3.44, 4.0 y 4.2, con 13 bloques aprobados en cada uno y checker oficial QGIS 4 limpio. Los entornos, dependencias y límites están en QGIS_COMPATIBILITY_REPORT.md. El render offscreen usa widgets Qt reales y una interfaz QGIS simulada; no sustituye la prueba con los datos y la pantalla del usuario. Matplotlib puede avisar que un layout de un gráfico oculto es demasiado pequeño; al mostrarlo se ajusta al canvas. No hubo excepciones críticas de slots Qt.

La instalación y su copia de seguridad se registran por separado en INSTALLATION_RECORD.json cuando se despliega en el perfil local. Para cargar módulos ya importados por QGIS se requiere reiniciar QGIS después de actualizar el plugin.
