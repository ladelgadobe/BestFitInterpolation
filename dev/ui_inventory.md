# UI inventory — BestFitInterpolator_dialog_base.ui

| path | class | properties |
|---|---|---|
| `/BestFitInterpolatorDialogBase` | QDialog |  |
| `/BestFitInterpolatorDialogBase/mainTabs` | QTabWidget | currentIndex=4 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/groupDataPreview` | QGroupBox | title=Preview |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/groupDataPreview/canvasData` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblDataCrsValue` | QLabel | text=CRS: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblMoranIndexValue` | QLabel | text=- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblSpatialStructure` | QLabel | text=Spatial structure |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/chkExportRaster` | QCheckBox | text=Export Rasters to project folder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/spinPixelSize` | QSpinBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblPixelSize` | QLabel | text=Pixel size: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblVariable` | QLabel | text=Variable |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblPolygonLayer` | QLabel | text=Polygon |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/btnLoad` | QPushButton | text=Load |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/cmbVariable` | QComboBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/lblPointsLayer` | QLabel | text=Load data points |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/cmbPolygonLayer` | QComboBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabData/cmbPointsLayer` | QComboBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetInterpolation/canvasDetInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics` | QGroupBox | title=Metrics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valRMSE_2` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblRMSE_2` | QLabel | text=RMSE%: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valLCCC` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblLCCC` | QLabel | text=LCCC: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblPearsonR` | QLabel | text=Pearson: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valR2` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/btnRunCV` | QPushButton | text=Run Cross-Validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/spinK` | QSpinBox | minimum=2; maximum=100; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/radCVLOOCV` | QRadioButton | text=Leave-One-Out (LOOCV) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/line` | Line |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblRMSE` | QLabel | text=RMSE: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblR2` | QLabel | text=R²: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/radCVKFold` | QRadioButton | text=K-Fold |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valPearsonR` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/lblMAE` | QLabel | text=MAE: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/radCVAuto` | QRadioButton | toolTip=Automatic uses LOOCV for n <= 100 and changes to K-Fold from n = 101 (10 folds through n = 1000; 5 folds above 1000).; text=Auto; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valMAE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/groupDetMetrics/valRMSE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/detSubTabs/tabDetValidation/canvasDetValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions` | QGroupBox | title=Options |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/btnInterpolate` | QPushButton | text=Interpolate |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupTPSOptions` | QGroupBox | title=TPS |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupTPSOptions/chkTPS` | QCheckBox | text=Thin plate spline |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions` | QGroupBox | title=IDW |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/chkOptimize` | QCheckBox | toolTip=If checked, n and p will be estimated automatically; manual inputs will be ignored.; text=Optimize IDW (p, n) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/spinPower` | QDoubleSpinBox | toolTip=IDW power controls how fast influence decreases with distance. Higher values give nearby points more weight; lower values produce smoother results.; decimals=2; minimum=0.010000000000000; maximum=10.000000000000000; singleStep=0.100000000000000; value=2.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/btnInfoIDWPower` | QLabel | toolTip=IDW power controls how fast influence decreases with distance. Higher values give nearby points more weight; lower values produce smoother results. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/lblPower` | QLabel | toolTip=IDW power controls how fast influence decreases with distance. Higher values give nearby points more weight; lower values produce smoother results.; text=Power (p) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/spinNeighbors` | QSpinBox | toolTip=Number of nearest sample points used for each IDW prediction. More neighbors usually smooth the surface; fewer neighbors emphasize local variation.; minimum=1; maximum=200; value=12 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/btnInfoIDWNeighbors` | QLabel | toolTip=Number of nearest sample points used for each IDW prediction. More neighbors usually smooth the surface; fewer neighbors emphasize local variation. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/lblNeighbors` | QLabel | toolTip=Number of nearest sample points used for each IDW prediction. More neighbors usually smooth the surface; fewer neighbors emphasize local variation.; text=Neighbors (n) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabDeterministic/groupDetOptions/groupIDWOptions/radManualParams` | QRadioButton | text=Manual parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/btnOKInterpolate` | QPushButton | text=Interpolate… |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/CanvasOKInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/CanvasOKVariogram` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel` | QGroupBox | title=Model Adjust |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lblSDI_value` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lbl_SDI` | QLabel | text=Spatial Dependence Index (SDI) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lblOKPsill` | QLabel | text=Partial Sill (C1) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/spinOKNugget` | QDoubleSpinBox | decimals=4; minimum=0.000000000000000; maximum=1000000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/spinOKPsill` | QDoubleSpinBox | decimals=4; minimum=0.000000000000000; maximum=1000000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/spinOKRange` | QDoubleSpinBox | decimals=4; minimum=0.000000000000000; maximum=1000000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lblOKNugget` | QLabel | text=Nugget (Co) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/btnOKModelValidation` | QPushButton | toolTip=View the automatic validation used to compare the Spherical, Exponential, and Gaussian kriging models.; text=View validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/cmbOKModel` | QComboBox | items=Automatic | Sph | Exp | Gau |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lblOKModelSel` | QLabel | text=Model: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKModel/lblOKRange` | QLabel | text=Range (a) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram` | QGroupBox | title=Semivariogram |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/btnOKCalculate` | QPushButton | text=Calculate… |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/btnOKReset` | QPushButton | text=Reset… |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/spinOKLag` | QDoubleSpinBox | decimals=12; minimum=0.000000000000000; maximum=1000000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKLag` | QLabel | text=Lag (h): |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/spinOKCutoff` | QDoubleSpinBox | decimals=12; minimum=0.000000000000000; maximum=1000000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKCut` | QLabel | text=Maximum distance: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKFitMethodInfo` | QLabel | toolTip=MoM uses the experimental semivariogram and fits the model curve from binned semivariance values. REML estimates the variogram parameters statistically from the data and can be heavier computationally, so manual REML is limited to fewer than 500 valid samples. In Automatic mode, the original REML rule remains fewer than 100 valid samples. In REML mode the experimental semivariogram is not shown. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/cmbOKFitMethod` | QComboBox | toolTip=Automatic keeps the original rule: REML is used only when available and the dataset has fewer than 100 valid samples; otherwise MoM is used. If REML is selected manually, it is allowed only for fewer than 500 valid samples to avoid overloading the system. MoM fits the theoretical variogram to the experimental semivariogram and shows experimental points. REML estimates variogram parameters by restricted maximum likelihood and does not display the experimental semivariogram.; items=Automatic | MoM | REML |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKFitMethod` | QLabel | text=Fit method: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/valOKModel` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKFit` | QLabel | text=Fit: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/valOKSamples` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKN` | QLabel | text=Samples: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/valOKZName` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKInterpolation/groupOKVariogram/lblOKZ` | QLabel | text=Z: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics` | QGroupBox | title=Validation metrics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/btn_OKRunCV` | QPushButton | text=Run Cross-Validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/line_2` | Line |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKR2` | QLabel | text=R² |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKLCCC` | QLabel | text=LCCC |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKPearsonR` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/radCV_OK_LOOCV` | QRadioButton | text=Leave-One-Out (LOOCV) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKMAE` | QLabel | text=MAE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKRMSE` | QLabel | text=RMSE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKMAE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKR2` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/radCV_OK_Auto` | QRadioButton | text=Auto |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKRMSEpct` | QLabel | text=RMSE% |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/spin_k_ok` | QSpinBox | minimum=2; maximum=100 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKLCCC` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/radCV_OK_Kfold` | QRadioButton | text=K-Fold |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKRMSEpct` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/lblvalOKPearsonR` | QLabel | text=Pearson |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/groupOKMetrics/valOKRMSE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabKriging/tabWidgetOK/tabOKValidation/CV_Kriging_widget/canvasOKValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs` | QTabWidget | currentIndex=3 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/btnExportCorrCSV` | QPushButton | text=Export correlations CSV |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/btnComputeCorrelations` | QPushButton | text=Compute correlations |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/CorPlot` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/labelCorrTitle` | QLabel | text=Correlation Matrix |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling` | QGroupBox | title=Resampling |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/btnExportTable` | QPushButton | text=Export extractions CSV |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/BtnExtracted` | QPushButton | text=View data with extractions |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/BtnExtract` | QPushButton | text=Extract covariates to sample points |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/btnApplyStandardization` | QPushButton | text=Standardize covariates |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/cmbStandardizeMethod` | QComboBox | items=Z-score | Range [-1,1] |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/labelStandardization` | QLabel | text=Standardization: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/btnResampleCovariates` | QPushButton | text=Resample covariates |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/spinTargetPixelSize` | QDoubleSpinBox | decimals=4; minimum=0.000100000000000; maximum=99999999.000000000000000; value=0.010000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/labelTargetPixelSize` | QLabel | text=Target pixel size: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupResampling/labelResamplingInfo` | QLabel | text=Resample all covariate rasters to a common pixel size. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovPreproc` | QGroupBox | title=Covariates preprocessing |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovPreproc/btnClear` | QPushButton | text=Clear |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovPreproc/btnRemoveCovariates` | QPushButton | text=Remove selected |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovPreproc/listCovariates` | QListWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovPreproc/labelLoadedCovariates` | QLabel | text=Loaded covariates: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters` | QGroupBox | title=Covariate rasters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters/px_import` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters/lblMLPixelSize` | QLabel | text=Pixel size: (from Data) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters/btnMLLoadRaster` | QPushButton | text=Load |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters/cmbMLRaster` | QComboBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLCovariables/groupCovRasters/labelRaster` | QLabel | text=Raster: |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/btnRFRun` | QPushButton | text=Run Random Forest interpolation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFInterpolation` | QGroupBox | title=RF interpolation map |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFInterpolation/RFMap` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFImportance` | QGroupBox | title=Variable importance |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFImportance/RFImportance` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams` | QGroupBox | title=Random Forest parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/btnInfoRFSearchIter` | QToolButton | toolTip=Only used when Grid Search is enabled. Explains how to choose the number of search iterations.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRFSearchIter` | QSpinBox | toolTip=Only used when Grid Search is enabled. Maximum number of random-search iterations to try. Lower values are faster. Recommended: 10 for normal use, 15 to 20 for smaller datasets if you want a more complete search.; minimum=1; maximum=200; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFSearchIter` | QLabel | text=Max iterations |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/btnInfoRFSearchK` | QToolButton | toolTip=Only used when Grid Search is enabled. Explains how to choose the number of folds.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRFSearchK` | QSpinBox | toolTip=Only used when Grid Search is enabled. Number of cross-validation folds used to evaluate candidate hyperparameters. Lower values are faster. Recommended: 3 for most computers, 5 only for smaller datasets or more robust tuning.; minimum=2; maximum=10; value=3 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFSearchK` | QLabel | text=Search folds (k) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/chkRFUseGrid` | QRadioButton | text=Grid Search; checked=false |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/chkRFUseManual` | QRadioButton | text=Manual parameters; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFHeader3` | QLabel | text=Grid max |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_ntree_max` | QSpinBox | minimum=1; maximum=100000; value=1000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_ntree_min` | QSpinBox | minimum=1; maximum=100000; value=200 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFHeader2` | QLabel | text=Grid min |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFHeader1` | QLabel | text=Manual/Selected |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_mtry_min` | QSpinBox | minimum=1; maximum=100000; value=2 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRF_nodesize` | QLabel | text=Minimum node size (nodesize) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFHeader0` | QLabel | text=Parameter |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_ntree_step` | QSpinBox | minimum=1; maximum=100000; value=100 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRFHeader4` | QLabel | text=Step |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_mtry_manual` | QSpinBox | minimum=1; maximum=100000; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_nodesize_max` | QSpinBox | minimum=1; maximum=100000; value=20 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_nodesize_manual` | QSpinBox | minimum=1; maximum=100000; value=5 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_mtry_max` | QSpinBox | minimum=1; maximum=100000; value=50 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRF_ntree` | QLabel | text=Number of trees (ntree) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_nodesize_step` | QSpinBox | minimum=1; maximum=100000; value=1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_mtry_step` | QSpinBox | minimum=1; maximum=100000; value=2 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_ntree_manual` | QSpinBox | minimum=1; maximum=100000; value=500 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/spinRF_nodesize_min` | QSpinBox | minimum=1; maximum=100000; value=1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFInterpolation/groupRFParams/labelRF_mtry` | QLabel | text=Number of variables at each split (mtry) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics` | QGroupBox | title=Validation metrics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/btnRFRunCV` | QPushButton | text=Run Cross-Validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/spinRF_k` | QSpinBox | minimum=2; maximum=100; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/radRF_CV_KFold` | QRadioButton | text=K-Fold |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/radRF_CV_LOOCV` | QRadioButton | text=Leave-One-Out (LOOCV) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/radRF_CV_Auto` | QRadioButton | text=Auto; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/line_RF` | Line |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFPearsonR` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFPearsonR` | QLabel | text=Pearson |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFMAE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFMAE` | QLabel | text=MAE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFR2` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFR2` | QLabel | text=R² |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFLCCC` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFLCCC` | QLabel | text=LCCC |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFRMSEpct` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFRMSEpct` | QLabel | text=RMSE% |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/valRFRMSE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/groupRFMetrics/labelRFRMSE` | QLabel | text=RMSE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLRF/tabWidgetRF/tabRFValidation/CV_RF_widget/canvasRFValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationRightPanel` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationRightPanel/groupSVMInterpolation` | QGroupBox | title=SVM interpolation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationRightPanel/groupSVMInterpolation/canvasSVMInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters` | QGroupBox | title=SVM parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/btnSVMRun` | QPushButton | text=Run SVM |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid` | QGroupBox | title=Grid search |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/btnInfoSVMSearchIter` | QToolButton | toolTip=Only used when Grid Search is enabled. Maximum number of candidate parameter combinations tested during the search. More iterations explore the search space better, but increase processing time.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/btnInfoSVMSearchK` | QToolButton | toolTip=Only used when Grid Search is enabled. Number of cross-validation folds used to compare candidate SVM hyperparameters. Lower values are faster; higher values are usually more robust but slower.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVMSearchIter` | QSpinBox | toolTip=Only used when Grid Search is enabled. Maximum number of candidate combinations tested during the search.; minimum=1; maximum=100; value=12 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMSearchIter` | QLabel | text=Max iterations |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVMSearchK` | QSpinBox | toolTip=Only used when Grid Search is enabled. Number of folds used to evaluate candidate hyperparameters.; minimum=2; maximum=10; value=3 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMSearchFolds` | QLabel | text=Search folds |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_epsilon_step` | QDoubleSpinBox | toolTip=Step used to generate epsilon candidates during the search.; decimals=4; minimum=0.010000000000000; maximum=1000.000000000000000; singleStep=0.050000000000000; value=0.100000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_epsilon_max` | QDoubleSpinBox | toolTip=Maximum value explored for epsilon during grid/random search.; decimals=4; minimum=0.000000000000000; maximum=1000.000000000000000; singleStep=0.050000000000000; value=0.500000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_epsilon_min` | QDoubleSpinBox | toolTip=Minimum value explored for epsilon during grid/random search.; decimals=4; minimum=0.000000000000000; maximum=1000.000000000000000; singleStep=0.050000000000000; value=0.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVM_epsilon_grid` | QLabel | text=epsilon |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_gamma_step` | QDoubleSpinBox | toolTip=Multiplicative or incremental step used to generate gamma candidates, depending on the search logic.; decimals=4; minimum=0.000000000000000; maximum=999999.000000000000000; singleStep=0.500000000000000; value=2.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_gamma_max` | QDoubleSpinBox | toolTip=Maximum value explored for gamma during grid/random search.; decimals=6; minimum=0.000010000000000; maximum=999999.000000000000000; singleStep=0.100000000000000; value=2.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_gamma_min` | QDoubleSpinBox | toolTip=Minimum value explored for gamma during grid/random search.; decimals=6; minimum=0.000010000000000; maximum=999999.000000000000000; singleStep=0.003125000000000; value=0.003125000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVM_gamma_grid` | QLabel | text=gamma (log2) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_C_step` | QDoubleSpinBox | toolTip=Multiplicative or incremental step used to generate C candidates, depending on the search logic.; decimals=4; minimum=0.000000000000000; maximum=999999.000000000000000; singleStep=0.500000000000000; value=2.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_C_max` | QDoubleSpinBox | toolTip=Maximum value explored for C during grid/random search.; decimals=5; minimum=0.000010000000000; maximum=999999.000000000000000; singleStep=1.000000000000000; value=32.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/spinSVM_C_min` | QDoubleSpinBox | toolTip=Minimum value explored for C during grid/random search.; decimals=5; minimum=0.000010000000000; maximum=999999.000000000000000; singleStep=0.125000000000000; value=0.125000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVM_C_grid` | QLabel | text=C (log2) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMGridStep` | QLabel | text=Step |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMGridMax` | QLabel | text=Max |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMGridMin` | QLabel | text=Min |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMGrid/labelSVMGridParameter` | QLabel | text=Parameter |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual` | QGroupBox | title=Manual |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/btnInfoSVMEpsilonManual` | QToolButton | toolTip=epsilon defines the width of the insensitive zone around the regression function. Errors smaller than epsilon are ignored during training. Smaller values fit the data more tightly; larger values produce a smoother model.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/btnInfoSVMGammaManual` | QToolButton | toolTip=gamma controls how local the influence of each sample is in the radial basis function (RBF) kernel. Higher gamma values create more local and complex responses; lower values create smoother and broader responses.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/btnInfoSVMCManual` | QToolButton | toolTip=C controls the penalty for prediction errors in Support Vector Regression. Larger values force the model to fit the training data more strictly, while smaller values allow a smoother and more tolerant fit.; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/spinSVM_epsilon_manual` | QDoubleSpinBox | toolTip=Insensitive margin around the regression function. Smaller values fit the data more tightly; larger values ignore small errors and smooth the model.; decimals=4; minimum=0.000000000000000; maximum=999999.000000000000000; singleStep=0.050000000000000; value=0.100000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/labelSVM_epsilon_manual` | QLabel | text=epsilon |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/spinSVM_gamma_manual` | QDoubleSpinBox | toolTip=RBF kernel influence radius. Higher values create more local and complex responses; lower values create smoother responses.; decimals=5; minimum=0.000010000000000; maximum=999999.000000000000000; singleStep=0.010000000000000; value=0.100000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/labelSVM_gamma_manual` | QLabel | text=gamma |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/spinSVM_C_manual` | QDoubleSpinBox | toolTip=Penalty for prediction errors in SVR. Higher values fit the training data more strictly; lower values allow a smoother fit.; decimals=4; minimum=0.000000000000000; maximum=999999.000000000000000; singleStep=0.100000000000000; value=1.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/grpSVMManual/labelSVM_C_manual` | QLabel | text=C |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/chkSVMUseGrid` | QRadioButton | toolTip=Search several candidate values for C, gamma and epsilon and keep the best combination found.; text=Grid search; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMInterpolation/svmInterpolationLeftPanel/groupSVMParameters/chkSVMUseManual` | QRadioButton | toolTip=Use the manual values currently defined for C, gamma and epsilon.; text=Manual parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics` | QGroupBox | title=Metrics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/btnSVMRunCV` | QPushButton | text=Run cross-validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/spinSVM_k` | QSpinBox | minimum=2; maximum=100; value=5 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/radSVM_CV_KFold` | QRadioButton | text=K-Fold |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/radSVM_CV_LOOCV` | QRadioButton | text=LOOCV |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/radSVM_CV_Auto` | QRadioButton | text=Auto; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMPearsonR` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMPearsonR` | QLabel | text=Pearson |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMMAE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMMAE` | QLabel | text=MAE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMR2` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMR2` | QLabel | text=R² |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMLCCC` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMLCCC` | QLabel | text=LCCC |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMRMSEpct` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMRMSEpct` | QLabel | text=RMSE% |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/valSVMRMSE` | QLabel | text=— |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/groupSVMMetrics/labelSVMRMSE` | QLabel | text=RMSE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLSVM/tabWidgetSVM/tabSVMValidation/canvasSVMValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKInterpolationMap` | QGroupBox | title=Regression Kriging map |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKInterpolationMap/RKMap` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics` | QGroupBox | title=Diagnostics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics/tabWidgetRKDiagnostics` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics/tabWidgetRKDiagnostics/tabRKVariogram` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics/tabWidgetRKDiagnostics/tabRKVariogram/RKVariogram` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics/tabWidgetRKDiagnostics/tabRKImportance` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKDiagnostics/tabWidgetRKDiagnostics/tabRKImportance/RKImportance` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams` | QGroupBox | title=Regression Kriging parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging` | QGroupBox | title=Residual kriging |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/spinRKNugget` | QDoubleSpinBox | decimals=6; maximum=1000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/labelRKNugget` | QLabel | text=Nugget (Co) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/cmbRKModel` | QComboBox | items=Spherical | Exponential | Gaussian |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/spinRKRange` | QDoubleSpinBox | decimals=6; minimum=0.000001000000000; maximum=1000000000.000000000000000; value=1.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/labelRKPsill` | QLabel | text=Partial sill (C1) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/btnRKApplyVariogram` | QPushButton | text=Interpolate RK |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/labelRKVarModel` | QLabel | text=Residual variogram model |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/spinRKPsill` | QDoubleSpinBox | decimals=6; maximum=1000000000.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKKriging/labelRKRange` | QLabel | text=Range (a) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF` | QGroupBox | title=Random Forest |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/valRKBestParams` | QLabel | text=Best RF params: -- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/btnRKFitRF` | QPushButton | text=Fit RF parameters |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/btnInfoRKSearchIter` | QToolButton | text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRKSearchIter` | QSpinBox | minimum=1; maximum=1000; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKSearchIter` | QLabel | text=Max search iterations |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/btnInfoRKSearchK` | QToolButton | text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRKSearchK` | QSpinBox | minimum=2; maximum=20; value=3 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKSearchK` | QLabel | text=Search folds (k) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_nodesize_step` | QSpinBox | minimum=1; maximum=100000; value=1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_nodesize_max` | QSpinBox | minimum=1; maximum=100000; value=20 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_nodesize_min` | QSpinBox | minimum=1; maximum=100000; value=1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_nodesize_manual` | QSpinBox | minimum=1; maximum=100000; value=5 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRK_nodesize` | QLabel | text=Minimum node size (nodesize) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_ntree_step` | QSpinBox | minimum=1; maximum=100000; value=100 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_ntree_max` | QSpinBox | minimum=1; maximum=100000; value=800 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_ntree_min` | QSpinBox | minimum=1; maximum=100000; value=200 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_ntree_manual` | QSpinBox | minimum=1; maximum=100000; value=500 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRK_ntree` | QLabel | text=Number of trees (ntree) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_mtry_step` | QSpinBox | minimum=1; maximum=100000; value=2 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_mtry_max` | QSpinBox | minimum=1; maximum=100000; value=50 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_mtry_min` | QSpinBox | minimum=1; maximum=100000; value=1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/spinRK_mtry_manual` | QSpinBox | minimum=1; maximum=100000; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRK_mtry` | QLabel | text=Number of variables at each split (mtry) |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKHeader4` | QLabel | text=Step |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKHeader3` | QLabel | text=Max |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKHeader2` | QLabel | text=Min |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKHeader1` | QLabel | text=Manual / Selected |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/grpRKRF/labelRKHeader0` | QLabel | text=Parameter |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/valRKStatus` | QLabel | text=RF not fitted |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/labelRKStatusTitle` | QLabel | text=Status |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/chkRKUseGrid` | QRadioButton | text=Grid search |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKInterpolation/groupRKParams/chkRKUseManual` | QRadioButton | text=Manual parameters; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics` | QGroupBox | title=Metrics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/btnRKRunCV` | QPushButton | text=Run RK cross-validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/spinRK_k` | QSpinBox | minimum=2; maximum=20; value=10 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/radRK_CV_KFold` | QRadioButton | text=K-Fold |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/radRK_CV_LOOCV` | QRadioButton | text=LOOCV |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/radRK_CV_Auto` | QRadioButton | text=Automatic CV; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/lineRKValidation` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKPearsonR` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKPearsonR` | QLabel | text=Pearson |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKMAE` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKMAE` | QLabel | text=MAE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKR2` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKR2` | QLabel | text=R² |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKLCCC` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKLCCC` | QLabel | text=LCCC |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKRMSEpct` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKRMSEpct` | QLabel | text=RMSE% |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/valRKRMSE` | QLabel | text=-- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/groupRKMetrics/labelRKRMSE` | QLabel | text=RMSE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabMachineLearning/mlSubTabs/tabMLKriging/tabWidgetRK/tabRKValidation/canvasRKValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs` | QTabWidget | currentIndex=0 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom` | QSplitter |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkPointMap` | QGroupBox | title=Point map |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkPointMap/frameFrameworkPointMap` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkPointMap/frameFrameworkPointMap/lblFrameworkPointMapPlaceholder` | QLabel | text=Point map preview placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkVariogramPreview` | QGroupBox | title=Semivariogram |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkVariogramPreview/frameFrameworkVariogramPreview` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewBottom/groupFrameworkVariogramPreview/frameFrameworkVariogramPreview/lblFrameworkVariogramPlaceholder` | QLabel | text=Semivariogram preview placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop` | QSplitter |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary` | QGroupBox | title=Data |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSDIStatusValue` | QLineEdit | text=Pending |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSDIStatusValue_title` | QLabel | text=SDI status |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSDIValue` | QLineEdit | text=Not calculated |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSDIValue_title` | QLabel | text=SDI |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPatternValue` | QLineEdit | text=- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPatternValue_title` | QLabel | text=Spatial pattern |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPValueValue` | QLineEdit | text=- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPValueValue_title` | QLabel | text=p-value |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkMoranValue` | QLineEdit | text=- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkMoranValue_title` | QLabel | text=Moran's I |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSamplesValue` | QLineEdit | text=- |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkSamplesValue_title` | QLabel | text=Number of samples |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPixelValue` | QLineEdit | text=From Data |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkPixelValue_title` | QLabel | text=Pixel size |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkVariableValue` | QLineEdit | text=From Data |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkDataSummary/lblFrameworkVariableValue_title` | QLabel | text=Variable |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkOverviewActions` | QGroupBox | title=Actions |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkOverviewActions/frameFrameworkOverviewNotes` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkOverviewActions/frameFrameworkOverviewNotes/lblFrameworkOverviewHelp` | QLabel | text=Review the current dataset here. The point map and semivariogram below provide a quick visual diagnosis before moving to the framework decision. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkOverview/splitterFrameworkOverviewTop/groupFrameworkOverviewActions/btnFrameworkOpenSDIWindow` | QPushButton | text=Semivariogram settings |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision` | QSplitter |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionLeft` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionLeft/groupFrameworkDecisionFigure` | QGroupBox | title=Framework figure |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionLeft/groupFrameworkDecisionFigure/frameFrameworkFigure` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionLeft/groupFrameworkDecisionFigure/frameFrameworkFigure/lblFrameworkFigurePlaceholder` | QLabel | text=Framework image from the article will be displayed here according to the selected mode. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/btnFrameworkGoToValidation` | QPushButton | text=Go to validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/btnFrameworkEvaluateMethods` | QPushButton | text=Evaluate available methods |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/groupFrameworkEligibilityPreview` | QGroupBox | title=Suggested methods |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/groupFrameworkEligibilityPreview/lblFrameworkEligibilityPreview` | QLabel | text=No methods evaluated yet. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/groupFrameworkDecisionSummary` | QGroupBox | title=Decision summary |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/splitterFrameworkDecision/pageFrameworkDecisionRight/groupFrameworkDecisionSummary/txtFrameworkDecisionSummary` | QPlainTextEdit |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/groupFrameworkMode` | QGroupBox | title=Framework mode |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/groupFrameworkMode/radFrameworkFull` | QRadioButton | text=Full framework |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkDecision/groupFrameworkMode/radFrameworkUnivariate` | QRadioButton | text=Univariate framework; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain` | QSplitter |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions` | QGroupBox | title=Covariate options |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/btnFrameworkComputeCorrelation` | QPushButton | text=Compute correlation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/btnFrameworkExtractCovariates` | QPushButton | text=Extract covariates to sample points |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/btnFrameworkResampleCovariates` | QPushButton | text=Resample covariates |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/spinFrameworkCovPixelSize` | QDoubleSpinBox | decimals=2; maximum=999999.000000000000000 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/lblFrameworkCovPixelSize` | QLabel | text=Pixel size |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/cmbFrameworkStandardization` | QComboBox | items=None | Z-score | -1 to 1 |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariateOptions/lblFrameworkStandardization` | QLabel | text=Standardization |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates` | QGroupBox | title=Covariate list |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates/btnFrameworkClearCovariates` | QPushButton | text=Clear all |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates/btnFrameworkRemoveCovariate` | QPushButton | text=Remove selected |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates/btnFrameworkLoadCovariates` | QPushButton | text=Load covariates |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates/btnFrameworkReuseCovariates` | QPushButton | text=Reuse from ML |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesLeft/groupFrameworkCovariates/listFrameworkCovariates` | QListWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCovariateMaps` | QGroupBox | title=Covariate maps |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCovariateMaps/frameFrameworkCovariateMaps` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCovariateMaps/frameFrameworkCovariateMaps/lblFrameworkCovariateMapsPlaceholder` | QLabel | text=Covariate map preview placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCorrelationPlot` | QGroupBox | title=Correlation plot |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCorrelationPlot/frameFrameworkCorrelationPlot` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/splitterFrameworkCovariatesMain/pageFrameworkCovariatesRight/groupFrameworkCorrelationPlot/frameFrameworkCorrelationPlot/lblFrameworkCorrelationPlaceholder` | QLabel | text=Correlation plot placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkCovariates/lblFrameworkCovariatesInfo` | QLabel | text=This page mirrors the Machine Learning covariates workflow when the full framework requires multivariate methods. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs` | QTabWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationResults` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationResults/groupFrameworkValidationSummary` | QGroupBox | title=Validation summary |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationResults/groupFrameworkValidationSummary/lblFrameworkValidationSummary` | QLabel | text=The best method and alternatives within the threshold will be summarized here. |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationResults/groupFrameworkValidationResults` | QGroupBox | title=Validation results |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationResults/groupFrameworkValidationResults/tableFrameworkValidation` | QTableWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlot` | QGroupBox | title=Validation plot |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlot/frameFrameworkValidationPlot` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlot/frameFrameworkValidationPlot/lblFrameworkValidationPlotPlaceholder` | QLabel | text=Validation plot placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlotControls` | QGroupBox | title=Plot controls |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlotControls/cmbFrameworkValidationMethod` | QComboBox |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlotControls/lblFrameworkValidationMethod` | QLabel | text=Method |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlotControls/cmbFrameworkValidationPlotType` | QComboBox | items=LCCC comparison | RMSE comparison | Observed vs Predicted |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/frameworkValidationSubTabs/tabFrameworkValidationPlot/groupFrameworkValidationPlotControls/lblFrameworkValidationPlotType` | QLabel | text=Plot type |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection` | QGroupBox | title=Method selection |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/btnFrameworkGraph` | QPushButton | text=Graph |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/btnFrameworkRunValidation` | QPushButton | text=Run validation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/btnFrameworkSelectSuggested` | QPushButton | text=Select suggested |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkRK` | QCheckBox | text=RK |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkRFE` | QCheckBox | text=RFE |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkSVM` | QCheckBox | text=SVM |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkOK` | QCheckBox | text=OK |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkIDW` | QCheckBox | text=IDW |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkValidation/groupFrameworkMethodSelection/chkFrameworkTPS` | QCheckBox | text=TPS |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport` | QGroupBox | title=PDF report |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/btnFrameworkExportPDF` | QPushButton | text=Export PDF report |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/btnFrameworkPreviewReport` | QPushButton | text=Preview report structure |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportFinalMap` | QCheckBox | text=Include final interpolation map; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportObsPred` | QCheckBox | text=Include observed vs predicted plots; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportLCCCPlot` | QCheckBox | text=Include LCCC plot; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportMetricsTable` | QCheckBox | text=Include metrics table; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportCorrelationPlot` | QCheckBox | text=Include correlation plot; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportCovariateMaps` | QCheckBox | text=Include covariate maps; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportCovariates` | QCheckBox | text=Include covariate list; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportSemivariogram` | QCheckBox | text=Include semivariogram; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/groupFrameworkReport/chkFrameworkReportPointMap` | QCheckBox | text=Include point map; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop` | QSplitter |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary` | QGroupBox | title=Final summary |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/txtFrameworkSummaryMethods` | QPlainTextEdit |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/lblFrameworkSummaryMethodsTitle` | QLabel | text=Validated methods |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/txtFrameworkSummaryDiagnostics` | QPlainTextEdit |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/lblFrameworkSummaryDiagnosticsTitle` | QLabel | text=Diagnostics |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/txtFrameworkSummaryWinner` | QLineEdit |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/lblFrameworkSummaryWinnerTitle` | QLabel | text=Selected |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/txtFrameworkSummaryMode` | QLineEdit |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkFinalSummary/lblFrameworkSummaryModeTitle` | QLabel | text=Mode |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkInterpolationOptions` | QGroupBox | title=Interpolation options |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkInterpolationOptions/btnFrameworkRunInterpolation` | QPushButton | text=Run interpolation |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkInterpolationOptions/chkFrameworkUseBestMethod` | QCheckBox | text=Use best validated method; checked=true |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkInterpolationOptions/cmbFrameworkFinalMethod` | QComboBox | items=TPS | IDW | OK | SVM | RFE | RK |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalLeft/groupFrameworkInterpolationOptions/lblFrameworkFinalMethod` | QLabel | text=Final method |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalRight` | QWidget |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalRight/groupFrameworkInterpolationMap` | QGroupBox | title=Interpolation map |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalRight/groupFrameworkInterpolationMap/frameFrameworkInterpolationMap` | QFrame |  |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/frameworkSubTabs/tabFrameworkInterpolation/splitterFrameworkFinalTop/pageFrameworkFinalRight/groupFrameworkInterpolationMap/frameFrameworkInterpolationMap/lblFrameworkInterpolationMapPlaceholder` | QLabel | text=Interpolation map placeholder |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/groupFrameworkHeader` | QGroupBox | title=Framework guidance |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/groupFrameworkHeader/lblFrameworkInfoText` | QLabel | text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/groupFrameworkHeader/btnFrameworkHeaderInfo` | QToolButton | toolTip=Framework article information; text= |
| `/BestFitInterpolatorDialogBase/mainTabs/tabFramework/groupFrameworkHeader/lblFrameworkIntro` | QLabel | text=This section guides method selection using the framework. Inputs are inherited from the Data tab, while SDI can be calculated here when needed. |
