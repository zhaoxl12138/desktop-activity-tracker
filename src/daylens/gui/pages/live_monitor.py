"""Live monitor page for the current foreground session."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QDialog,
    QMessageBox,
)

from ...utils import fmt_seconds, normalize_category_display_name
from .. import style as ui_style
from ..style import COLORS, get_category_color
from ..widgets.classification_dialog import ClassificationDialog, ChoiceDialog, CATEGORY_CHOICES


def classification_label(category_name: str, detail: dict) -> str:
    source = str(detail.get('source') or '规则')
    if source == 'AI待识别':
        return '待识别'
    if source == 'AI待确认':
        suggested = str(detail.get('suggested_category') or '')
        if suggested and suggested not in {'other', 'browser_general'}:
            label = normalize_category_display_name(suggested, '')
            return f'待确认 · 建议{label}'
        return '待确认'
    if source != '规则':
        return f'{category_name} · {source}'
    return category_name


def review_row_values(review: dict) -> tuple[str, str, str, str, str]:
    certainty = {'high': '高', 'medium': '中', 'low': '低', 'conflict': '冲突'}.get(
        str(review.get('certainty') or ''), '--')
    category = normalize_category_display_name(
        str(review.get('suggested_category') or 'other'), '')
    return (
        str(review.get('app') or ''),
        str(review.get('title') or ''),
        f'{category} · {certainty}',
        str(review.get('reason') or ''),
        f"{int(review.get('occurrences') or 0)}次 · {fmt_seconds(int(review.get('active_seconds') or 0))}",
    )


class LiveMonitorPage(QWidget):
    """Realtime foreground-window monitor."""

    classification_corrected = Signal()

    def __init__(self):
        super().__init__()
        self._samples = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        layout.addWidget(self._build_current_session_card())
        self.correct_button = QPushButton('纠正当前分类')
        self.correct_button.clicked.connect(self._correct_current)
        self.manage_patterns_button = QPushButton('管理已确认模式')
        self.manage_patterns_button.clicked.connect(self._manage_patterns)
        correction_actions = QHBoxLayout()
        correction_actions.addWidget(self.correct_button)
        correction_actions.addWidget(self.manage_patterns_button)
        self.correction_status = QLabel('可选择下方记录后纠正分类')
        self.correction_status.setTextFormat(Qt.PlainText)
        self.correction_status.setWordWrap(True)
        correction_actions.addWidget(self.correction_status, 1)
        correction_actions.addStretch()
        layout.addLayout(correction_actions)
        layout.addWidget(self._build_review_card())
        layout.addWidget(self._build_history_card(), 1)
        self._review_mtime = None
        self.refresh_reviews(force=True)

    def _correct_current(self):
        if not self._samples:
            self.correction_status.setText('暂无可纠正的前台记录')
            return
        row = self.table.currentRow()
        sample = dict(self._samples[row if 0 <= row < len(self._samples) else 0])
        dialog = ClassificationDialog(parent=self, app_name=sample.get('process_name', ''),
                                      title=sample.get('window_title', ''),
                                      current_category=sample.get('category_key', 'other'))
        if dialog.exec() != QDialog.Accepted:
            return
        category = dialog.selected_category()
        try:
            from ...services.intelligence_state import save_override
            save_override(self._review_directory(), sample.get('process_name'),
                          sample.get('window_title'), category)
            self.classification_corrected.emit()
            self.correction_status.setText(f'已纠正为{dict((key, name) for name, key in CATEGORY_CHOICES)[category]}，后续记录生效')
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', f'无法保存此标题的分类纠正：{exc}')

    def _manage_patterns(self):
        from ...services.intelligence_evidence import (
            delete_pattern, load_patterns, set_pattern_enabled, update_pattern_category,
        )
        patterns = load_patterns(self._review_directory())
        if not patterns:
            QMessageBox.information(self, '已确认模式', '还没有可管理的相似标题模式。')
            return
        labels = []
        by_id = {}
        for pattern in patterns:
            state = '启用' if pattern.get('enabled', True) else '停用'
            category = normalize_category_display_name(str(pattern.get('category') or ''), '')
            label = f"[{state}] {category} · {str(pattern.get('example') or '')[:70]}"
            labels.append((f"{pattern.get('app', '')} · {label}", pattern['id']))
            by_id[pattern['id']] = pattern
        picker = ChoiceDialog(self, heading='管理已确认模式', description='选择需要修改的模式', choices=labels)
        picker.buttons.button(picker.buttons.StandardButton.Save).setText('下一步')
        if picker.exec() != QDialog.Accepted:
            return
        pattern = by_id[picker.selected_category()]
        toggle = '停用' if pattern.get('enabled', True) else '启用'
        actions = ChoiceDialog(self, heading='模式操作', description=pattern.get('example', ''),
                               choices=[('修改分类', 'edit'), (toggle, 'toggle'), ('删除', 'delete')])
        actions.buttons.button(actions.buttons.StandardButton.Save).setText('确定')
        if actions.exec() != QDialog.Accepted:
            return
        try:
            action = actions.selected_category()
            if action == 'edit':
                dialog = ClassificationDialog(parent=self, app_name=pattern.get('app', ''),
                    title=pattern.get('example', ''), current_category=pattern['category'])
                if dialog.exec() != QDialog.Accepted:
                    return
                changed = update_pattern_category(self._review_directory(), pattern['id'], dialog.selected_category())
            elif action == 'delete':
                if QMessageBox.question(self, '删除模式', '确定删除此模式？', QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return
                changed = delete_pattern(self._review_directory(), pattern['id'])
            else:
                changed = set_pattern_enabled(self._review_directory(), pattern['id'], not pattern.get('enabled', True))
            if not changed:
                raise ValueError('模式已不存在，请重新打开列表')
            self.classification_corrected.emit()
            self.correction_status.setText('模式已更新，后续记录生效')
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', f'模式未能更新：{exc}')

    def _build_current_session_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())

        root = QVBoxLayout(card)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("当前前台活动")
        title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)

        header.addStretch()

        self.lbl_status = QLabel("等待采样")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"""
            QLabel {{
                color: {COLORS['text_muted']};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 14px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        self.lbl_title = QLabel("--")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {COLORS['text']};"
        )
        root.addWidget(self.lbl_title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self.lbl_process = self._make_badge("--", COLORS["primary"])
        self.lbl_category = self._make_badge("--", COLORS["idle_gray"])
        meta_row.addWidget(self.lbl_process)
        meta_row.addWidget(self.lbl_category)
        meta_row.addStretch()
        root.addLayout(meta_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.lbl_duration = QLabel("--")
        self.lbl_effective = QLabel("--")
        self.lbl_session_idle = QLabel("--")
        self.lbl_idle = QLabel("--")

        cards = [
            ("前台停留", self.lbl_duration, COLORS["primary"]),
            ("有效时间", self.lbl_effective, COLORS["coding_green"]),
            ("本会话挂机", self.lbl_session_idle, COLORS["warning_yellow"]),
            ("系统空闲", self.lbl_idle, COLORS["idle_gray"]),
        ]
        for col, (label, value_label, color) in enumerate(cards):
            grid.addWidget(self._make_metric_tile(label, value_label, color), 0, col)
        root.addLayout(grid)

        return card

    def _build_history_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())

        root = QVBoxLayout(card)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("最近采样记录")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["时间", "进程", "窗口标题", "分类", "有效"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(ui_style.get_table_style())
        root.addWidget(self.table, 1)

        return card

    def _build_review_card(self):
        card = QFrame()
        card.setObjectName('dashboardCard')
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        root = QVBoxLayout(card)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel('待确认分类')
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        hint = QLabel('只影响确认后的记录')
        hint.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        header.addWidget(hint)
        root.addLayout(header)

        self.review_table = QTableWidget()
        self.review_table.setColumnCount(5)
        self.review_table.setHorizontalHeaderLabels(['应用', '标题', 'AI建议', '依据', '累计'])
        self.review_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.review_table.verticalHeader().setVisible(False)
        self.review_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.review_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.review_table.setMaximumHeight(180)
        self.review_table.setStyleSheet(ui_style.get_table_style())
        root.addWidget(self.review_table)

        actions = QHBoxLayout()
        self.accept_review_button = QPushButton('接受建议')
        self.choose_review_button = QPushButton('选择分类')
        self.ignore_review_button = QPushButton('忽略')
        self.accept_review_button.clicked.connect(self._accept_review)
        self.choose_review_button.clicked.connect(self._choose_review)
        self.ignore_review_button.clicked.connect(self._ignore_review)
        actions.addWidget(self.accept_review_button)
        actions.addWidget(self.choose_review_button)
        actions.addWidget(self.ignore_review_button)
        actions.addStretch()
        root.addLayout(actions)
        self.review_card = card
        return card

    @staticmethod
    def _review_directory():
        from pathlib import Path
        from ... import get_data_dir
        return Path(get_data_dir()) / 'intelligence'

    def refresh_reviews(self, *, force=False):
        from ...services.intelligence_evidence import ReviewQueue
        path = self._review_directory() / 'classification_reviews.json'
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = None
        if not force and mtime == self._review_mtime:
            return
        self._review_mtime = mtime
        self._review_rows = ReviewQueue(self._review_directory()).items()
        self.review_table.setRowCount(len(self._review_rows))
        for row_index, review in enumerate(self._review_rows):
            for column, value in enumerate(review_row_values(review)):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, review.get('id'))
                self.review_table.setItem(row_index, column, item)
        self.review_card.setVisible(bool(self._review_rows))

    def _selected_review(self):
        row = self.review_table.currentRow()
        if row < 0 or row >= len(getattr(self, '_review_rows', [])):
            return None
        return dict(self._review_rows[row])

    def _resolve_review(self, category):
        review = self._selected_review()
        if review is None:
            return
        try:
            from ...services.intelligence_evidence import ReviewQueue
            ReviewQueue(self._review_directory()).resolve(review['id'], category)
            self._review_mtime = None
            self.refresh_reviews(force=True)
            self.classification_corrected.emit()
        except Exception:
            QMessageBox.warning(self, '保存失败', '无法保存此标题的分类确认')

    def _accept_review(self):
        review = self._selected_review()
        if review is not None:
            self._resolve_review(str(review.get('suggested_category') or ''))

    def _choose_review(self):
        review = self._selected_review()
        if review is None:
            return
        dialog = ClassificationDialog(parent=self, app_name=review.get('app', ''),
            title=review.get('title', ''), current_category=review.get('suggested_category', 'other'))
        if dialog.exec() == QDialog.Accepted:
            self._resolve_review(dialog.selected_category())

    def _ignore_review(self):
        review = self._selected_review()
        if review is None:
            return
        from ...services.intelligence_evidence import ReviewQueue
        ReviewQueue(self._review_directory()).ignore(review['id'])
        self._review_mtime = None
        self.refresh_reviews(force=True)

    def _make_badge(self, text: str, color: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        return label

    def _make_metric_tile(self, label_text: str, value_label: QLabel, color: str):
        tile = QFrame()
        tile.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 14px;
            }}
            """
        )

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"
        )
        layout.addWidget(label)

        value_label.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color};")
        layout.addWidget(value_label)
        return tile

    def on_sample_updated(self, sample):
        self._samples.insert(0, sample)
        if len(self._samples) > 20:
            self._samples = self._samples[:20]
        self.refresh_reviews()

        proc = sample.get("process_name", "--")
        title = (sample.get("window_title", "--") or "--")[:90]
        cat_key = sample.get("category_key", "other") or "other"
        cat_name = normalize_category_display_name(
            str(cat_key),
            str(sample.get("category_name", "--") or "--"),
        )
        dur = sample.get("duration_seconds", 0) or 0
        eff = sample.get("effective_seconds", 0) or 0
        sidle = sample.get("session_idle_seconds", 0) or 0
        persistent_idle = sample.get("persistent_idle", 0) or 0
        audio_playing = sample.get("audio_playing", False)
        category_color = get_category_color(cat_key)

        self.lbl_process.setText(proc)
        self.lbl_title.setText(title)
        detail = sample.get('classification_detail') or {}
        source = detail.get('source', '规则')
        self.lbl_category.setText(classification_label(cat_name, detail))
        reason = str(detail.get('reason') or '')
        # Qt tooltips can interpret HTML; escape all model-controlled text.
        import html
        self.lbl_category.setToolTip(html.escape(f'分类来源：{source}\n{reason}'))
        self.lbl_category.setStyleSheet(
            f"""
            QLabel {{
                color: {category_color};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        self.lbl_duration.setText(fmt_seconds(dur))
        self.lbl_effective.setText(fmt_seconds(eff))
        self.lbl_session_idle.setText(fmt_seconds(sidle))
        if cat_key == "video":
            self.lbl_idle.setText(f"{persistent_idle:.0f}s 🔊={'Y' if audio_playing else 'N'}")
        else:
            self.lbl_idle.setText(f"{persistent_idle:.0f}s")

        if sample.get("is_ignored"):
            self.lbl_status.setText("不计入统计")
            self.lbl_status.setStyleSheet(
                f"""
                QLabel {{
                    color: {COLORS['text_secondary']};
                    background: {COLORS['panel_bg']};
                    border: 1px solid {COLORS['border_light']};
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )
        elif sample.get("is_effective"):
            self.lbl_status.setText("有效记录中")
            self.lbl_status.setStyleSheet(
                f"""
                QLabel {{
                    color: {COLORS['success_green']};
                    background: {ui_style.COLORS['success_bg']};
                    border: 1px solid {COLORS['success_green']};
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )
        else:
            self.lbl_status.setText(f"挂机 {persistent_idle:.0f}s")
            self.lbl_status.setStyleSheet(
                f"""
                QLabel {{
                    color: {COLORS['warning_yellow']};
                    background: {ui_style.COLORS['warning_bg']};
                    border: 1px solid {COLORS['warning_yellow']};
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )

        self.table.setRowCount(len(self._samples))
        for row, item in enumerate(self._samples):
            timestamp = item.get("timestamp", "")
            time_text = timestamp[-8:] if len(timestamp) >= 8 else timestamp
            normalized_title = item.get("normalized_title", "") or item.get("window_title", "")
            is_effective = "是" if item.get("is_effective") else "否"
            row_cat_key = item.get("category_key", "other") or "other"
            row_color = get_category_color(row_cat_key)

            self.table.setItem(row, 0, QTableWidgetItem(time_text))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("process_name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(normalized_title))
            category_name = normalize_category_display_name(
                str(row_cat_key),
                str(item.get("category_name", "") or ""),
            )
            detail = item.get('classification_detail') or {}
            category_item = QTableWidgetItem(f"● {classification_label(category_name, detail)}")
            category_item.setForeground(QBrush(QColor(row_color)))
            import html
            reason = html.escape(str(detail.get('reason') or ''))
            evidence = html.escape('、'.join(str(value) for value in detail.get('evidence') or []))
            category_item.setToolTip(
                f"分类来源：{detail.get('source', '规则')}\n{reason}\n{evidence}".strip())
            self.table.setItem(row, 3, category_item)
            self.table.setItem(row, 4, QTableWidgetItem(is_effective))
