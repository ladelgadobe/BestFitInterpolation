# -*- coding: utf-8 -*-
"""About page — faithful port of the legacy code-built About tab
(BestFitInterpolator._add_about_tab). Presentation-only: buttons open
external URLs from metadata.txt."""

from __future__ import annotations

import os

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QPixmap
from qgis.PyQt.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .common import tr


def _open_external_url(parent, url):
    try:
        opened = QDesktopServices.openUrl(QUrl(url))
    except Exception:
        opened = False
    if not opened:
        QMessageBox.warning(
            parent,
            tr("Unable to open link"),
            tr("The link could not be opened:") + f"\n{url}",
        )


def _url_button(dialog, parent, object_name, text, url, tooltip=None, min_height=30):
    button = QPushButton(text, parent)
    button.setObjectName(object_name)
    button.setMinimumHeight(min_height)
    button.setToolTip(tooltip or url or tr("Link not configured in metadata.txt"))
    button.setEnabled(bool(url))
    if url:
        button.clicked.connect(
            lambda _checked=False, target=url: _open_external_url(dialog, target)
        )
    return button


def setup_about_page(dialog, page, plugin_dir, metadata):
    plugin_name = metadata.get("name", "Best Fit Interpolator")
    version = metadata.get("version", "Unknown")
    authors = metadata.get("author", "Not specified")
    email = metadata.get("email", "")
    linkedin_laura = metadata.get("linkedin_laura", "")
    linkedin_lucas = metadata.get("linkedin_lucas", "")
    repository = metadata.get("repository", metadata.get("homepage", ""))
    tracker = metadata.get("tracker", "")
    manual = metadata.get("manual", "")
    article = metadata.get("article", "")
    article_title = metadata.get(
        "article_title",
        "Performance of interpolation methods in digital soil mapping: "
        "the influence of data characteristics",
    )
    article_citation = metadata.get(
        "article_citation",
        "Laura Delgado Bejarano, Agda Loureiro Gonçalves Oliveira, "
        "João Vitor Fiolo Pozzuto, Dario Castañeda Sánchez, and Lucas "
        f"Rios do Amaral (2026). {article_title}. Precision Agriculture, "
        "27, Article 10. https://doi.org/10.1007/s11119-025-10311-8",
    )
    description = metadata.get(
        "description",
        "Decision-support plugin for selecting, validating, and applying "
        "spatial interpolation methods in QGIS.",
    )

    page.setObjectName("tabAbout")
    root_layout = QVBoxLayout(page)
    root_layout.setContentsMargins(22, 18, 22, 18)
    root_layout.setSpacing(12)
    root_layout.setAlignment(Qt.AlignTop)

    header_layout = QHBoxLayout()
    header_layout.setSpacing(14)
    header_layout.setAlignment(Qt.AlignTop)
    icon_label = QLabel(page)
    icon_label.setFixedSize(64, 64)
    icon_label.setAlignment(Qt.AlignCenter)
    icon_pixmap = QPixmap(os.path.join(plugin_dir, "icon.png"))
    if not icon_pixmap.isNull():
        icon_label.setPixmap(
            icon_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
    header_layout.addWidget(icon_label)

    heading_layout = QVBoxLayout()
    heading_layout.setSpacing(2)
    title_label = QLabel(plugin_name, page)
    title_label.setObjectName("lblAboutPluginName")
    title_label.setStyleSheet("font-size: 20px; font-weight: 600;")
    version_label = QLabel(f"Version {version}", page)
    version_label.setObjectName("lblAboutVersion")
    version_label.setStyleSheet("color: palette(mid);")
    heading_layout.addWidget(title_label)
    heading_layout.addWidget(version_label)
    description_label = QLabel(description, page)
    description_label.setObjectName("lblAboutDescription")
    description_label.setWordWrap(True)
    description_label.setStyleSheet("margin-top: 5px;")
    heading_layout.addWidget(description_label)
    header_layout.addLayout(heading_layout)
    header_layout.addStretch()
    root_layout.addLayout(header_layout)

    information_group = QGroupBox(tr("Plugin information"), page)
    information_layout = QGridLayout(information_group)
    information_layout.setContentsMargins(12, 10, 12, 10)
    information_layout.setHorizontalSpacing(14)
    information_layout.setVerticalSpacing(7)
    information_layout.addWidget(QLabel("Version:", information_group), 0, 0)
    information_layout.addWidget(QLabel(version, information_group), 0, 1)
    information_layout.addWidget(QLabel("Authors:", information_group), 1, 0)
    authors_label = QLabel(authors, information_group)
    authors_label.setWordWrap(True)
    information_layout.addWidget(authors_label, 1, 1)
    information_layout.addWidget(QLabel("Contact:", information_group), 2, 0)
    information_layout.addWidget(QLabel(email or "Not specified", information_group), 2, 1)
    information_layout.addWidget(QLabel("LinkedIn:", information_group), 3, 0)
    linkedin_layout = QHBoxLayout()
    linkedin_layout.setSpacing(8)
    linkedin_layout.addWidget(_url_button(
        dialog, information_group, "btnAboutLinkedInLaura",
        "Laura Delgado Bejarano", linkedin_laura,
        "Open Laura Delgado Bejarano's LinkedIn profile to send a message",
    ))
    linkedin_layout.addWidget(_url_button(
        dialog, information_group, "btnAboutLinkedInLucas",
        "Lucas Rios do Amaral", linkedin_lucas,
        "Open Lucas Rios do Amaral's LinkedIn profile to send a message",
    ))
    information_layout.addLayout(linkedin_layout, 3, 1)
    information_layout.setColumnStretch(1, 1)

    article_group = QGroupBox(tr("Reference publication"), page)
    article_layout = QVBoxLayout(article_group)
    article_layout.setContentsMargins(12, 10, 12, 10)
    article_layout.setSpacing(6)
    reference_label = QLabel(tr("Complete reference:"), article_group)
    reference_label.setStyleSheet("font-weight: 600;")
    article_citation_label = QLabel(article_citation, article_group)
    article_citation_label.setObjectName("lblAboutArticleCitation")
    article_citation_label.setWordWrap(True)
    citation_request_label = QLabel(
        tr("If you use this plugin in academic work, please cite the reference article."),
        article_group,
    )
    citation_request_label.setObjectName("lblAboutCitationRequest")
    citation_request_label.setWordWrap(True)
    citation_request_label.setStyleSheet("font-style: italic;")
    article_layout.addWidget(reference_label)
    article_layout.addWidget(article_citation_label)
    article_layout.addWidget(citation_request_label)
    article_layout.addWidget(_url_button(
        dialog, article_group, "btnAboutArticle", tr("Open reference article"),
        article, min_height=34,
    ))

    details_layout = QHBoxLayout()
    details_layout.setSpacing(12)
    details_layout.addWidget(information_group, 1)
    details_layout.addWidget(article_group, 1)
    root_layout.addLayout(details_layout)

    resources_group = QGroupBox(tr("Documentation and support"), page)
    resources_layout = QGridLayout(resources_group)
    resources_layout.setContentsMargins(10, 10, 10, 10)
    resources_layout.setHorizontalSpacing(10)
    resource_buttons = (
        ("btnAboutManual", tr("User manual (PDF)"), manual),
        ("btnAboutRepository", tr("GitHub repository"), repository),
        ("btnAboutIssues", tr("Report an issue"), tracker),
        ("btnAboutEmail", tr("Contact by email"), f"mailto:{email}" if email else ""),
    )
    for index, (object_name, text, url) in enumerate(resource_buttons):
        resources_layout.addWidget(
            _url_button(dialog, resources_group, object_name, text, url, min_height=36),
            0, index,
        )
        resources_layout.setColumnStretch(index, 1)
    root_layout.addWidget(resources_group)
    root_layout.addStretch()
