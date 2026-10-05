# Best Fit Interpolator — matriz de compatibilidad

Estado al 3 de octubre de 2026. Objetivo: una única implementación para QGIS >=3.14 y 4.x. Un máximo declarado en metadata no certifica ejecución.

| Versión | Estado | Evidencia | Pendiente / limitación |
|---|---|---|---|
| QGIS 3.14 | statically reviewed / not tested | Parser Python 3.7, imports qgis.PyQt, enums legacy, Qt5Agg, límites de dependencias Python antiguo | Carga/UIC/resources, cálculos, tareas y PDF en la distribución real |
| QGIS 3.22 LTR | statically reviewed / not tested | Adaptadores Qt5/API antigua, revisión de dependencia del Python de la distribución | Batería e integración física |
| QGIS 3.28 LTR | statically reviewed / not tested | Mismos adaptadores y revisión de rutas | Batería e integración física |
| QGIS 3.34+ | statically reviewed / not tested | Implementación compartida QGIS 3, detección de capacidades | Batería en 3.34; no inferir resultados de 3.44 |
| QGIS 3.44.8 | tested | 100/100 pruebas y sesión integral offscreen con QGIS/Qt reales | Ensayo manual en el perfil de producción, datasets mayores y otros sistemas |
| QGIS 4.0 / 4.x | statically reviewed / not tested | Enums scoped, QAction QtGui, exec/print, QtAgg, adaptadores geometría/unidades; máximo 4.99 | Qt6, UIC/resources, APIs QGIS, tareas e integración física |

El entorno ejecutado utiliza Windows, QGIS 3.44.8-Solothurn, Python 3.12, Qt 5.15.13, NumPy 2.4.2 y SciPy 1.17.0. El ensayo usa perfil aislado y una interfaz simulada; no reemplaza el plugin del perfil default.

## Reproducir en este workspace

Desde `C:\Users\ladel\OneDrive\Documentos\Plugin`, usando el runtime distribuido con QGIS:

```powershell
& 'C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat' 'tools\run_qgis_checks.py' 'development_20261002\bestfitinterpolator'
& 'C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat' 'tools\run_qgis_checks.py' 'development_20261002\bestfitinterpolator' 'tools\qa_bfi_session.py'
```

Para otra instalación, ajustar `BFI_QGIS_INSTALL` y ejecutar su launcher Python, con el nombre que realmente tenga esa distribución. La ruta del runner no obliga a usar una instalación 3.44 cuando se aporta esta variable.

```powershell
$env:BFI_QGIS_INSTALL = 'C:\Program Files\QGIS <version>'
```

Las pruebas de equivalencia cargan funciones de la copia original. Para reproducir fuera de este workspace, conservar esa base y definir `BFI_BASELINE_ROOT` con la ruta a su carpeta `bestfitinterpolator`. La base no se importa ni usa durante el funcionamiento del plugin entregado.

La revisión de interfaz también verifica cinco reaperturas con reset, todas las pestañas a 1000×700/800×600, paletas gráficas, sincronización de Larger View, seis métodos realmente validados en Comparison y método ejecutado independiente del recomendado. Full Covariates conserva una correlación escalar editable y se prueba a 760×540 y 640×480. Evidencia: `UI_SESSION_RESULTS.json`.

La revisión posterior verifica validación sin paleta, IDW/TPS separados, RF limitado a Interpolation, RK lado a lado con Adjust, aislamiento de ejecuciones externas a Framework, comparaciones con covariable real TPS/SVM/RF/RK, resumen navegable y HTML portable. Las pruebas de canvas cubren escalas de píxeles 1/1.5/2 y exports temporales sin desbordar la figura copiada; no sustituyen un ensayo manual con cada monitor/DPI real.

El ZIP tiene raíz `bestfitinterpolator/`, assets y documentos. El código, tests y herramientas de reproducción permanecen en el workspace. No incluye entornos/dependencias binarias ni perfiles QGIS de QA.

## Checklist para cada runtime pendiente

1. Cargar el plugin y los assets/UIC/resources; abrir Data y las seis pestañas principales.
2. Abrir/cerrar Geostatistics tres veces; cambiar A → B, variable, MoM → REML → MoM; cambiar pestañas y retornar después de interpolar.
3. Editar cutoff/lag/número de lags y comprobar experimental actualizado, validación invalidada y parámetros manuales preservados.
4. Validar/aplicar candidatos desde la ventana avanzada de OK y de residuales RK; rechazar resultados obsoletos.
5. Ejecutar los diagnósticos sintéticos, seleccionar en tabla/mapa/distribuciones, Exclude/Keep/Reset; verificar conteos en cada lector y capa original intacta.
6. Ejecutar IDW/TPS/OK/REML/RF/SVM/RK y su CV con datos comunes; comparar resultados con la base dentro del mismo entorno.
7. Generar mapas validados de Framework; comparar A−B/NoData; bloquear grillas distintas; pan/zoom, escala y compartir paleta/rango/extensión.
8. Generar dos previews y PDF en una sesión, con y sin opciones. Revisar todas las páginas, tablas, captions, leyendas y numeración.
9. Cancelar tareas y cerrar ventanas durante cálculos; comprobar logs, ausencia de slots duplicados/objetos C++ destruidos y respuesta de GUI.
10. Medir rendimiento con datos grandes y registrar versiones de Python/Qt/NumPy/SciPy/GDAL/Matplotlib/sklearn. No marcar la fila tested hasta ejecutar estos ensayos.

## Adaptaciones y referencias

La implementación utiliza detección de capacidades en `compat.py` en lugar de ramas repetidas por número de versión. La sintaxis se comprueba con el parser 3.7; esto no ejecuta un intérprete Python 3.7. Las anotaciones de la base que usan sintaxis de tipos moderna están pospuestas con `from __future__ import annotations`.

Los bounds de instalación para Python 3.7/3.8 se limitan a familias de dependencias que soportan esos intérpretes; no implican igualdad de resultados entre distintas generaciones de sklearn/SciPy. Se conserva la configuración matemática y se requiere comparar dentro de cada entorno.

La base y la entrega necesitan NumPy >=1.17 por `default_rng`. Un QGIS antiguo con NumPy anterior requiere un entorno de dependencias compatible; no se cambia silenciosamente a otro generador aleatorio, porque cambiaría sus secuencias reproducibles. No se instalaron ni actualizaron dependencias durante esta entrega.

Referencias oficiales: [migración Qt5/Qt6 de QGIS](https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6), [metadatos y migración QGIS 4](https://plugins.qgis.org/docs/migrate-qgis4), [toolchain de SciPy](https://docs.scipy.org/doc/scipy/dev/toolchain.html), [historial de soporte Python de scikit-learn](https://scikit-learn.org/stable/install.html).
