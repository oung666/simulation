from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BattleReportDialog(QDialog):
    def __init__(
        self,
        reports: list,
        open_replay_callback: Callable[[object], None],
        delete_report_callback: Callable[[object, bool], list],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BattleReportDialog")
        self.setWindowTitle("战绩")
        self.resize(1280, 760)
        self._reports = list(reports)
        self._open_replay_callback = open_replay_callback
        self._delete_report_callback = delete_report_callback
        self.report_list = QListWidget(self)
        self.summary_label = QLabel("请选择一条战绩", self)
        self.summary_label.setWordWrap(True)
        self.side_summary_label = QLabel("", self)
        self.side_summary_label.setWordWrap(True)
        self.unit_table = QTableWidget(self)
        self.view_replay_button = QPushButton("查看回放", self)
        self.clear_report_button = QPushButton("清除战绩记录", self)
        self.delete_all_button = QPushButton("彻底删除战绩+回放", self)
        self._build_ui()
        self._bind_events()
        self._load_reports()
        
    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog#BattleReportDialog {
                background: #ededed;
                color: #1f1f1f;
            }
            QWidget#BattleReportDetailPanel {
                background: #f7f7f7;
                border: 1px solid #dcdcdc;
                border-radius: 14px;
            }
            QLabel {
                background: transparent;
                color: #1f1f1f;
                font-size: 13px;
                font-weight: 700;
            }
            QListWidget, QTableWidget {
                background: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 12px;
                color: #111827;
            }
            QPushButton {
                background: #07c160;
                border: none;
                border-radius: 10px;
                color: #ffffff;
                font-weight: 900;
                padding: 9px 16px;
            }
            QPushButton:hover {
                background: #06ad56;
            }
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.report_list, 2)

        right = QWidget(self)
        right.setObjectName("BattleReportDetailPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)
        right_layout.addWidget(self.summary_label)
        right_layout.addWidget(self.side_summary_label)
        right_layout.addWidget(self.unit_table, 1)
        right_layout.addWidget(self.view_replay_button)
        right_layout.addWidget(self.clear_report_button)
        right_layout.addWidget(self.delete_all_button)
        layout.addWidget(right, 3)

    def _bind_events(self) -> None:
        self.report_list.currentRowChanged.connect(self._show_report)
        self.view_replay_button.clicked.connect(self._open_selected_replay)
        self.clear_report_button.clicked.connect(self._delete_report_only)
        self.delete_all_button.clicked.connect(self._delete_report_and_replay)

    def _load_reports(self) -> None:
        self.report_list.clear()
        for report in self._reports:
            blue_summary = report.side_summary.get("blue")
            red_summary = report.side_summary.get("red")
            blue_alive = 0 if blue_summary is None else blue_summary.alive_count
            red_alive = 0 if red_summary is None else red_summary.alive_count
            self.report_list.addItem(
                f"{report.finished_at} | {report.scenario_name} | {report.result_label} | 蓝{blue_alive} 红{red_alive}"
            )
        if self._reports:
            self.report_list.setCurrentRow(0)
        else:
            self.summary_label.setText("暂无战绩记录")
            self.side_summary_label.setText("")
            self.unit_table.clear()
            self.unit_table.setRowCount(0)
            self.unit_table.setColumnCount(0)

    def _show_report(self, row: int) -> None:
        if row < 0 or row >= len(self._reports):
            return
        report = self._reports[row]
        blue_summary = report.side_summary.get("blue")
        red_summary = report.side_summary.get("red")
        self.summary_label.setText(
            f"场景: {report.scenario_name}\n"
            f"结果: {report.result_label}\n"
            f"时长: {report.duration_seconds:.0f} 秒\n"
            f"结算原因: {report.settlement_reason}"
        )
        self.side_summary_label.setText(
            f"蓝方: 存活 {0 if blue_summary is None else blue_summary.alive_count} / "
            f"损失 {0 if blue_summary is None else blue_summary.lost_count} / "
            f"发射 {0 if blue_summary is None else blue_summary.launch_count} / "
            f"命中 {0 if blue_summary is None else blue_summary.hit_count} / "
            f"击毁 {0 if blue_summary is None else blue_summary.kill_count}\n"
            f"红方: 存活 {0 if red_summary is None else red_summary.alive_count} / "
            f"损失 {0 if red_summary is None else red_summary.lost_count} / "
            f"发射 {0 if red_summary is None else red_summary.launch_count} / "
            f"命中 {0 if red_summary is None else red_summary.hit_count} / "
            f"击毁 {0 if red_summary is None else red_summary.kill_count}"
        )
        self.unit_table.setColumnCount(7)
        self.unit_table.setHorizontalHeaderLabels(["阵营", "单位", "型号", "存活", "击毁", "发射", "命中"])
        self.unit_table.setRowCount(len(report.unit_rows))
        for index, item in enumerate(report.unit_rows):
            values = [
                item.side,
                item.name,
                item.class_name,
                "是" if item.alive else "否",
                str(item.kills),
                str(item.launches),
                str(item.hits),
            ]
            for column, value in enumerate(values):
                self.unit_table.setItem(index, column, QTableWidgetItem(value))
        self.unit_table.resizeColumnsToContents()

    def _open_selected_replay(self) -> None:
        row = self.report_list.currentRow()
        if row < 0 or row >= len(self._reports):
            return
        self._open_replay_callback(self._reports[row])

    def _delete_report_only(self) -> None:
        self._delete_selected_report(delete_replay=False)

    def _delete_report_and_replay(self) -> None:
        self._delete_selected_report(delete_replay=True)

    def _delete_selected_report(self, delete_replay: bool) -> None:
        row = self.report_list.currentRow()
        if row < 0 or row >= len(self._reports):
            return
        self._reports = list(self._delete_report_callback(self._reports[row], delete_replay))
        self._load_reports()
