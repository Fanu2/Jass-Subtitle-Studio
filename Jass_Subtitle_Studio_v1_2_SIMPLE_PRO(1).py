import sys
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QImage, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QSlider, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox, QFrame, QProgressBar,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QColorDialog, QSplitter, QTabWidget, QAbstractItemView, QDialog,
    QDialogButtonBox, QFormLayout, QStyleFactory, QToolButton, QSizePolicy
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink


APP_NAME = "Jass Subtitle Studio"
VERSION = "1.2 Simple Pro"

TIME_RE = re.compile(r"^(\d+):([0-5]\d):([0-5]\d)[,.](\d{3})$")


@dataclass
class Subtitle:
    index: int
    start: int
    end: int
    text: str


def parse_time(value):
    m = TIME_RE.match(value.strip())
    if not m:
        raise ValueError(f"Invalid timestamp: {value}")
    h, mi, s, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + s) * 1000 + ms


def fmt_time(ms):
    ms = max(0, int(ms))
    milli = ms % 1000
    total = ms // 1000
    sec = total % 60
    total //= 60
    minute = total % 60
    hour = total // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{milli:03d}"


def short_time(ms):
    total = max(0, int(ms)) // 1000
    return f"{total // 3600:02d}:{(total % 3600)//60:02d}:{total % 60:02d}"


def parse_srt(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    result = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if not lines:
            continue
        ti = next((i for i, line in enumerate(lines[:6]) if "-->" in line), None)
        if ti is None:
            continue
        try:
            number = int(lines[0].strip())
        except ValueError:
            number = len(result) + 1
        left, right = [x.strip() for x in lines[ti].split("-->", 1)]
        right = right.split()[0]
        start, end = parse_time(left), parse_time(right)
        if end < start:
            raise ValueError(f"Subtitle {number}: end precedes start.")
        text_value = "\n".join(lines[ti + 1:]).strip()
        result.append(Subtitle(number, start, end, text_value))
    for i, item in enumerate(result, 1):
        item.index = i
    return result


def write_srt(entries):
    return "\n\n".join(
        f"{i}\n{fmt_time(s.start)} --> {fmt_time(s.end)}\n{s.text}"
        for i, s in enumerate(entries, 1)
    ) + ("\n" if entries else "")


def txt_to_srt(text, seconds=3.0, chars=42, split_sentences=False):
    lines = [x.strip() for x in text.replace("\r\n", "\n").split("\n") if x.strip()]
    processed = []
    for line in lines:
        if split_sentences:
            parts = re.split(r"(?<=[.!?])\s+", line)
        else:
            parts = [line]
        for part in parts:
            if not part:
                continue
            if chars and len(part) > chars:
                words, current = part.split(), ""
                for word in words:
                    candidate = f"{current} {word}".strip()
                    if current and len(candidate) > chars:
                        processed.append(current)
                        current = word
                    else:
                        current = candidate
                if current:
                    processed.append(current)
            else:
                processed.append(part)
    dur = max(250, int(seconds * 1000))
    return [Subtitle(i, (i-1)*dur, i*dur, line) for i, line in enumerate(processed, 1)]


def validate(entries):
    issues = []
    previous_end = -1
    for i, s in enumerate(entries, 1):
        if s.start < 0:
            issues.append(f"{i}: negative start time.")
        if s.end <= s.start:
            issues.append(f"{i}: end must be after start.")
        if s.start < previous_end:
            issues.append(f"{i}: overlaps the previous subtitle.")
        if not s.text.strip():
            issues.append(f"{i}: empty subtitle text.")
        if len(s.text.replace("\n", " ")) > 180:
            issues.append(f"{i}: unusually long text.")
        previous_end = max(previous_end, s.end)
    return issues


class VideoPreview(QWidget):
    """Reliable Windows preview: render video frames and subtitles in one QWidget.

    QVideoWidget may use a native video surface on Windows, which can cover
    normal child overlays. QVideoSink gives us the decoded frame, so this
    widget paints both the video and subtitle in the same paint operation.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sink = QVideoSink(self)
        self.frame_image = QImage()
        self.text = ""
        self.values = {
            "font": "Arial", "size": 32, "color": "#ffffff",
            "bold": True, "italic": False, "outline": True,
            "shadow": True, "background": False, "position": "Bottom"
        }
        self.sink.videoFrameChanged.connect(self._frame_changed)
        self.setMinimumSize(400, 260)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def _frame_changed(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.frame_image = image.convertToFormat(QImage.Format_RGB32)
        self.update()

    def set_style(self, values):
        self.values = dict(values)
        self.update()

    def set_text(self, text):
        self.text = text or ""
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor("black"))

        # Keep the video's real aspect ratio and remember the exact rectangle
        # where the video is drawn. Subtitles are ALWAYS positioned inside
        # this rectangle, never in the surrounding black letterbox area.
        video_rect = None
        if not self.frame_image.isNull():
            scaled_size = self.frame_image.size()
            scaled_size.scale(self.size(), Qt.KeepAspectRatio)
            x = (self.width() - scaled_size.width()) // 2
            y = (self.height() - scaled_size.height()) // 2
            video_rect = self.rect().adjusted(x, y,
                                               -(self.width() - x - scaled_size.width()),
                                               -(self.height() - y - scaled_size.height()))
            p.drawImage(video_rect, self.frame_image)

        if not self.text or video_rect is None:
            return

        v = self.values
        # Style size is relative to the displayed video height so portrait,
        # landscape and square videos all get proportionally placed subtitles.
        scale = video_rect.height() / 720.0
        font_px = max(12, int(v.get("size", 32) * max(0.65, min(1.8, scale))))
        font = QFont(v.get("font", "Arial"), font_px)
        font.setBold(bool(v.get("bold", True)))
        font.setItalic(bool(v.get("italic", False)))
        p.setFont(font)

        margin = max(12, int(video_rect.width() * 0.055))
        usable = video_rect.adjusted(margin, 0, -margin, 0)
        rect_h = max(55, min(int(video_rect.height() * 0.24), 190))

        if v.get("position") == "Top":
            y = video_rect.top() + max(12, int(video_rect.height() * 0.055))
        elif v.get("position") == "Center":
            y = video_rect.center().y() - rect_h // 2
        else:
            y = video_rect.bottom() - rect_h - max(12, int(video_rect.height() * 0.055))

        rect = usable.__class__(
            usable.left(), int(y), usable.width(), rect_h
        )

        if v.get("background"):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 165))
            p.drawRoundedRect(rect.adjusted(-12, -8, 12, 8), 9, 9)

        outline_w = max(2, font_px // 12)
        flags = Qt.AlignCenter | Qt.TextWordWrap

        if v.get("shadow"):
            p.setPen(QPen(QColor(0, 0, 0, 220), outline_w + 2))
            p.drawText(rect.translated(3, 3), flags, self.text)

        if v.get("outline"):
            p.setPen(QPen(QColor("black"), outline_w))
            p.drawText(rect, flags, self.text)

        p.setPen(QPen(QColor(v.get("color", "#ffffff")), 1))
        p.drawText(rect, flags, self.text)


class StylePanel(QGroupBox):
    """Compact, user-friendly subtitle appearance controls."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Subtitle Appearance", parent)
        self.color = "#ffffff"

        self.font = QComboBox()
        self.font.addItems([
            "Arial", "Verdana", "Tahoma", "Georgia",
            "Trebuchet MS", "Times New Roman", "Courier New"
        ])

        self.size = QSpinBox()
        self.size.setRange(12, 96)
        self.size.setValue(32)
        self.size.setSuffix(" px")

        self.color_button = QPushButton("White")
        self.color_button.clicked.connect(self.choose_color)

        self.position = QComboBox()
        self.position.addItems(["Bottom", "Center", "Top"])

        self.bold = QCheckBox("Bold")
        self.bold.setChecked(True)
        self.italic = QCheckBox("Italic")
        self.outline = QCheckBox("Outline")
        self.outline.setChecked(True)
        self.shadow = QCheckBox("Shadow")
        self.shadow.setChecked(True)
        self.background = QCheckBox("Background box")

        self.fade = QSpinBox()
        self.fade.setRange(0, 2000)
        self.fade.setValue(0)
        self.fade.setSingleStep(100)
        self.fade.setSuffix(" ms")

        form = QFormLayout(self)
        form.addRow("Font:", self.font)
        form.addRow("Size:", self.size)
        form.addRow("Color:", self.color_button)
        form.addRow("Position:", self.position)
        form.addRow("", self.bold)
        form.addRow("", self.italic)
        form.addRow("", self.outline)
        form.addRow("", self.shadow)
        form.addRow("", self.background)
        form.addRow("Fade in/out:", self.fade)

        self.font.currentTextChanged.connect(lambda _: self.changed.emit())
        self.size.valueChanged.connect(lambda _: self.changed.emit())
        self.position.currentTextChanged.connect(lambda _: self.changed.emit())
        self.fade.valueChanged.connect(lambda _: self.changed.emit())
        for box in (
            self.bold, self.italic, self.outline,
            self.shadow, self.background
        ):
            box.toggled.connect(lambda _: self.changed.emit())

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Subtitle Color")
        if color.isValid():
            self.color = color.name()
            self.color_button.setText(color.name().upper())
            self.changed.emit()

    def values(self):
        return {
            "font": self.font.currentText(),
            "size": self.size.value(),
            "color": self.color,
            "bold": self.bold.isChecked(),
            "italic": self.italic.isChecked(),
            "outline": self.outline.isChecked(),
            "shadow": self.shadow.isChecked(),
            "background": self.background.isChecked(),
            "position": self.position.currentText(),
            "fade": self.fade.value(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {VERSION}")
        self.resize(1450, 900)
        self.video_path = ""
        self.srt_path = ""
        self.output_path = ""
        self.entries = []
        self.duration = 0
        self.render_process = None
        self.ffmpeg = self.find_ffmpeg()
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.9)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.preview = VideoPreview()
        self.player.setVideoOutput(self.preview.sink)
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(self.on_duration)
        self.player.errorOccurred.connect(self.media_error)
        self.build_ui()
        self.refresh_style()

    def find_ffmpeg(self):
        candidates = [
            shutil.which("ffmpeg"),
            str(Path(__file__).with_name("ffmpeg.exe")),
            str(Path(__file__).with_name("bin") / "ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
        ]
        return next((x for x in candidates if x and Path(x).exists()), None)

    def build_ui(self):
        root = QWidget()
        main = QVBoxLayout(root)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("JASS SUBTITLE STUDIO")
        title.setObjectName("title")
        sub = QLabel(f"{VERSION}  •  Video + subtitles made simple")
        sub.setObjectName("muted")
        head.addWidget(title)
        head.addWidget(sub)
        head.addStretch()
        self.ffmpeg_label = QLabel("● FFmpeg ready" if self.ffmpeg else "● FFmpeg not found")
        self.ffmpeg_label.setObjectName("ffmpeg")
        setup = QPushButton("FFmpeg…")
        setup.clicked.connect(self.choose_ffmpeg)
        head.addWidget(self.ffmpeg_label)
        head.addWidget(setup)
        main.addLayout(head)

        steps = QHBoxLayout()
        for label, slot in [
            ("1  Choose Video", self.choose_video),
            ("2  Load SRT", self.choose_srt),
            ("TXT → SRT", self.choose_txt),
            ("Edit Subtitles", self.edit_selected),
            ("Validate", self.validate_dialog),
        ]:
            b = QPushButton(label); b.clicked.connect(slot); steps.addWidget(b)

        self.quick_render = QPushButton("🔥  RENDER / BURN SUBTITLES")
        self.quick_render.setMinimumHeight(36)
        self.quick_render.clicked.connect(self.create_video)
        self.quick_render.setToolTip("Create a new video with the subtitles permanently burned in.")
        steps.addWidget(self.quick_render)

        main.addLayout(steps)

        split = QSplitter(Qt.Horizontal)
        preview_box = QGroupBox("LIVE PREVIEW")
        pv = QVBoxLayout(preview_box)
        pv.addWidget(self.preview, 1)

        controls = QHBoxLayout()
        self.play = QPushButton("▶ Play")
        self.play.clicked.connect(self.play_pause)
        self.back = QPushButton("−5s"); self.back.clicked.connect(lambda: self.seek_by(-5000))
        self.forward = QPushButton("+5s"); self.forward.clicked.connect(lambda: self.seek_by(5000))
        self.time = QLabel("00:00:00 / 00:00:00")
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.player.setPosition)
        controls.addWidget(self.play); controls.addWidget(self.back); controls.addWidget(self.forward)
        controls.addWidget(self.time); controls.addWidget(self.slider, 1)
        pv.addLayout(controls)
        split.addWidget(preview_box)

        right = QTabWidget()
        style_tab = QWidget(); sl = QVBoxLayout(style_tab)
        self.style = StylePanel(); self.style.changed.connect(self.refresh_style)
        sl.addWidget(self.style)
        help_label = QLabel("Changes are visible immediately in the video preview and are used when the video is rendered.")
        help_label.setWordWrap(True); help_label.setObjectName("muted")
        sl.addWidget(help_label); sl.addStretch()
        right.addTab(style_tab, "Style")

        convert_tab = QWidget(); cl = QVBoxLayout(convert_tab)
        box = QGroupBox("TXT → SRT")
        form = QFormLayout(box)
        self.seconds = QDoubleSpinBox(); self.seconds.setRange(.25, 120); self.seconds.setValue(3.0); self.seconds.setSuffix(" sec")
        self.chars = QSpinBox(); self.chars.setRange(0, 200); self.chars.setValue(42); self.chars.setSpecialValueText("No limit")
        self.sentences = QCheckBox("Split sentences automatically")
        form.addRow("Time per line", self.seconds); form.addRow("Max characters", self.chars); form.addRow("", self.sentences)
        cl.addWidget(box)
        save_srt = QPushButton("Save Current SRT")
        save_srt.clicked.connect(self.save_srt)
        cl.addWidget(save_srt); cl.addStretch()
        right.addTab(convert_tab, "TXT / SRT")

        export_tab = QWidget(); el = QVBoxLayout(export_tab)
        out = QGroupBox("Create Final Video")
        ef = QFormLayout(out)
        self.output = QLineEdit(); self.output.setPlaceholderText("Choose output MP4…")
        ob = QPushButton("Browse"); ob.clicked.connect(self.choose_output)
        row = QHBoxLayout(); row.addWidget(self.output); row.addWidget(ob)
        ef.addRow("Output", row)
        self.copy_srt = QCheckBox("Also save SRT next to video"); self.copy_srt.setChecked(True)
        ef.addRow("", self.copy_srt)
        self.render = QPushButton("🔥  CREATE VIDEO")
        self.render.setMinimumHeight(55); self.render.clicked.connect(self.create_video)
        ef.addRow("", self.render)
        render_help = QLabel("Creates a NEW video with subtitles permanently burned in. Your original video is never changed.")
        render_help.setWordWrap(True); render_help.setObjectName("muted")
        ef.addRow("", render_help)
        self.progress = QProgressBar(); self.progress.setValue(0)
        ef.addRow("", self.progress)
        self.cancel = QPushButton("Cancel rendering"); self.cancel.setEnabled(False); self.cancel.clicked.connect(self.cancel_render)
        ef.addRow("", self.cancel)
        el.addWidget(out)
        el.addStretch()
        right.addTab(export_tab, "🔥 Render Video")

        split.addWidget(right)
        split.setSizes([970, 400])
        main.addWidget(split, 1)

        editor_box = QGroupBox("SUBTITLE LIST")
        ev = QVBoxLayout(editor_box)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Start", "End", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self.table_changed)
        self.table.cellDoubleClicked.connect(self.jump_to_row)
        ev.addWidget(self.table)
        erow = QHBoxLayout()
        for text, slot in [
            ("＋ Add", self.add_subtitle), ("− Delete", self.delete_subtitle),
            ("Shift −1s", lambda: self.shift_all(-1000)), ("Shift +1s", lambda: self.shift_all(1000)),
            ("Save SRT", self.save_srt), ("Export Subtitle Images", self.export_images),
        ]:
            b = QPushButton(text); b.clicked.connect(slot); erow.addWidget(b)
        erow.addStretch()
        ev.addLayout(erow)
        main.addWidget(editor_box, 1)

        self.status = QLabel("Ready. Choose a video, then load an SRT or TXT.")
        self.status.setObjectName("status")
        main.addWidget(self.status)
        self.setCentralWidget(root)

    def refresh_style(self):
        v = self.style.values()
        self.preview.set_style(v)
        self.update_overlay()

    def choose_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg.exe", "", "FFmpeg (ffmpeg.exe);;All Files (*)")
        if path:
            self.ffmpeg = path
            self.ffmpeg_label.setText("● FFmpeg ready")
            self.status.setText("FFmpeg configured.")

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Video", "", "Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All Files (*)")
        if not path: return
        self.video_path = path
        self.player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self.status.setText(f"Loaded video: {Path(path).name}")
        if not self.output_path:
            p = Path(path); self.output_path = str(p.with_name(p.stem + "_subtitled.mp4")); self.output.setText(self.output_path)

    def choose_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load SRT", "", "SubRip (*.srt);;All Files (*)")
        if not path: return
        try:
            self.entries = parse_srt(Path(path).read_text(encoding="utf-8-sig"))
            if not self.entries: raise ValueError("No valid subtitles found.")
            self.srt_path = path
            self.fill_table()
            self.status.setText(f"Loaded {len(self.entries)} subtitles.")
            self.update_overlay()
        except Exception as e:
            QMessageBox.critical(self, "SRT error", str(e))

    def choose_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load TXT", "", "Text (*.txt);;All Files (*)")
        if not path: return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            self.entries = txt_to_srt(text, self.seconds.value(), self.chars.value(), self.sentences.isChecked())
            self.srt_path = ""
            self.fill_table()
            self.status.setText(f"Created {len(self.entries)} subtitles from TXT.")
            self.update_overlay()
        except Exception as e:
            QMessageBox.critical(self, "TXT error", str(e))

    def fill_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for i, s in enumerate(self.entries):
            self.table.insertRow(i)
            vals = [str(i+1), fmt_time(s.start), fmt_time(s.end), s.text]
            for c, value in enumerate(vals):
                item = QTableWidgetItem(value)
                if c == 0: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, c, item)
        self.table.blockSignals(False)

    def table_changed(self, item):
        r = item.row()
        if r >= len(self.entries): return
        try:
            if item.column() == 1: self.entries[r].start = parse_time(item.text())
            elif item.column() == 2: self.entries[r].end = parse_time(item.text())
            elif item.column() == 3: self.entries[r].text = item.text()
            self.update_overlay()
        except Exception:
            self.status.setText("Invalid time. Use HH:MM:SS,mmm.")

    def jump_to_row(self, row, col):
        if row < len(self.entries):
            self.player.setPosition(self.entries[row].start)
            self.table.selectRow(row)

    def edit_selected(self):
        row = self.table.currentRow()
        if row >= 0: self.jump_to_row(row, 0)

    def add_subtitle(self):
        start = self.player.position()
        end = min(self.duration or start + 3000, start + 3000)
        self.entries.append(Subtitle(len(self.entries)+1, start, end, "New subtitle"))
        self.fill_table(); self.table.selectRow(len(self.entries)-1); self.status.setText("Subtitle added.")

    def delete_subtitle(self):
        rows = sorted({x.row() for x in self.table.selectedItems()}, reverse=True)
        if not rows: return
        for r in rows:
            if 0 <= r < len(self.entries): self.entries.pop(r)
        for i, s in enumerate(self.entries, 1): s.index = i
        self.fill_table(); self.status.setText("Subtitle deleted.")

    def shift_all(self, delta):
        for s in self.entries:
            s.start = max(0, s.start + delta); s.end = max(s.start + 100, s.end + delta)
        self.fill_table(); self.status.setText(f"All subtitles shifted {delta/1000:+g}s.")

    def save_srt(self):
        if not self.entries:
            QMessageBox.information(self, "No subtitles", "Load or create subtitles first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save SRT", self.srt_path or "", "SubRip (*.srt)")
        if not path: return
        Path(path).write_text(write_srt(self.entries), encoding="utf-8")
        self.srt_path = path
        self.status.setText(f"Saved: {Path(path).name}")

    def export_images(self):
        if not self.entries:
            QMessageBox.information(self, "No subtitles", "Load or create subtitles first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose folder for subtitle images")
        if not folder:
            return

        v = self.style.values()
        out_dir = Path(folder) / "subtitle_images"
        out_dir.mkdir(parents=True, exist_ok=True)

        width, height = 1920, 1080
        font = QFont(v["font"], v["size"])
        font.setBold(v["bold"])
        font.setItalic(v["italic"])
        font.setPixelSize(max(12, v["size"]))
        painter_dummy = QImage(width, height, QImage.Format_ARGB32)
        painter = QPainter(painter_dummy)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for i, item in enumerate(self.entries, 1):
            image = QImage(width, height, QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            p = QPainter(image)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.setFont(font)

            margin = 100
            rect_h = 260
            if v["position"] == "Top":
                y = 80
            elif v["position"] == "Center":
                y = (height - rect_h) // 2
            else:
                y = height - rect_h - 80
            rect = image.rect().adjusted(margin, y, -margin, -(height-y-rect_h))

            if v["background"]:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 170))
                p.drawRoundedRect(rect.adjusted(-24, -16, 24, 16), 14, 14)

            ow = max(1, v["size"] // 12)
            if v["shadow"]:
                p.setPen(QPen(QColor(0, 0, 0, 210), ow + 2))
                p.drawText(rect.translated(5, 5), Qt.AlignCenter | Qt.TextWordWrap, item.text)
            if v["outline"]:
                p.setPen(QPen(QColor("black"), ow))
                p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, item.text)
            p.setPen(QPen(QColor(v["color"]), 1))
            p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, item.text)
            p.end()

            filename = out_dir / f"{i:04d}_{item.start//1000:06d}.png"
            image.save(str(filename), "PNG")

        painter.end()
        self.status.setText(f"✓ Exported {len(self.entries)} subtitle images to {out_dir}")
        QMessageBox.information(
            self, "Subtitle images created",
            f"Created {len(self.entries)} PNG images.\n\n{out_dir}"
        )

    def validate_dialog(self):
        issues = validate(self.entries)
        if issues:
            QMessageBox.warning(self, "Subtitle validation", "\n".join(issues[:40]) + (f"\n\n…and {len(issues)-40} more." if len(issues)>40 else ""))
        else:
            QMessageBox.information(self, "Subtitle validation", "✓ No subtitle issues found.")

    def on_duration(self, value):
        self.duration = value; self.slider.setRange(0, max(0, value)); self.on_position(self.player.position())

    def on_position(self, value):
        self.time.setText(f"{short_time(value)} / {short_time(self.duration)}")
        if not self.slider.isSliderDown(): self.slider.setValue(value)
        self.update_overlay()
        if self.entries:
            row = next((i for i,s in enumerate(self.entries) if s.start <= value <= s.end), -1)
            if row >= 0 and self.table.currentRow() != row:
                self.table.blockSignals(True); self.table.selectRow(row); self.table.blockSignals(False)

    def update_overlay(self):
        pos = self.player.position()
        text = next((s.text for s in self.entries if s.start <= pos <= s.end), "")
        self.preview.set_text(text)

    def seek_by(self, delta):
        self.player.setPosition(max(0, min(self.duration, self.player.position()+delta)))

    def play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause(); self.play.setText("▶ Play")
        else:
            self.player.play(); self.play.setText("⏸ Pause")

    def media_error(self, error, message):
        if message: self.status.setText("Playback error: " + message)

    def choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Choose Output", self.output_path or "", "MP4 Video (*.mp4);;MKV Video (*.mkv)")
        if path: self.output_path = path; self.output.setText(path)

    def ass_time(self, ms):
        ms = max(0, int(ms)); cs=(ms%1000)//10; total=ms//1000
        s=total%60; total//=60; m=total%60; h=total//60
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def ass_escape(self, text):
        return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")

    def make_ass(self):
        import tempfile
        fd, name = tempfile.mkstemp(suffix=".ass", prefix="jass_"); os.close(fd)
        v=self.style.values()
        align={"Bottom":2,"Center":5,"Top":8}[v["position"]]
        rgb=v["color"].lstrip("#"); primary=f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"
        bold=-1 if v["bold"] else 0; italic=-1 if v["italic"] else 0
        outline=max(0, v["size"]//12) if v["outline"] else 0
        shadow=2 if v["shadow"] else 0
        border=3 if v["background"] else 1
        header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Jass,{v["font"]},{v["size"]},{primary},&H00000000,&H00000000,&H99000000,{bold},{italic},0,0,100,100,0,0,{border},{outline},{shadow},{align},60,60,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines=[header]
        for s in self.entries:
            fade = self.style.values()["fade"]
            effect = f"\\fad({fade},{fade})" if fade else ""
            lines.append(f"Dialogue: 0,{self.ass_time(s.start)},{self.ass_time(s.end)},Jass,,0,0,0,,{{{effect}}}{self.ass_escape(s.text)}")
        Path(name).write_text("\n".join(lines)+"\n", encoding="utf-8")
        return name

    def create_video(self):
        if not self.video_path:
            QMessageBox.information(self,"Choose video","Choose a video first."); return
        if not self.entries:
            QMessageBox.information(self,"Add subtitles","Load an SRT or TXT file first."); return
        if not self.ffmpeg:
            QMessageBox.warning(self,"FFmpeg required","Choose ffmpeg.exe with the FFmpeg… button, or install FFmpeg and add it to PATH."); return
        out=self.output_path or str(Path(self.video_path).with_name(Path(self.video_path).stem+"_subtitled.mp4"))
        if Path(out).resolve()==Path(self.video_path).resolve():
            QMessageBox.warning(self,"Output","Choose a different output file."); return
        ass=None
        try:
            ass=self.make_ass()
            # Normalize Windows path for FFmpeg's ASS filter.
            fp=str(Path(ass).resolve()).replace("\\","/").replace(":","\\:")
            vf=f"ass='{fp}'"
            cmd=[self.ffmpeg,"-y","-i",self.video_path,"-vf",vf,
                 "-c:v","libx264","-preset","medium","-crf","20",
                 "-c:a","aac","-b:a","192k","-movflags","+faststart",
                 "-progress","pipe:1","-nostats","-loglevel","error",out]
            self.render.setEnabled(False); self.quick_render.setEnabled(False); self.cancel.setEnabled(True); self.progress.setValue(0)
            self.status.setText("Rendering video…")
            self.render_process=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                  text=True, encoding="utf-8", errors="replace", bufsize=1)
            self._render_ass=ass; self._render_out=out
            QTimer.singleShot(100, self.poll_render)
        except Exception as e:
            if ass: Path(ass).unlink(missing_ok=True)
            QMessageBox.critical(self,"Render error",str(e))

    def poll_render(self):
        p=self.render_process
        if not p: return
        # Read available progress lines without blocking the GUI.
        line=None
        try:
            if p.stdout and p.poll() is None:
                import selectors
                sel=selectors.DefaultSelector(); sel.register(p.stdout, selectors.EVENT_READ)
                ready=sel.select(timeout=0)
                if ready: line=p.stdout.readline()
                sel.close()
        except Exception:
            pass
        if line and line.startswith("out_time_ms="):
            try:
                ms=int(line.split("=",1)[1])//1000
                if self.duration: self.progress.setValue(max(0,min(99,int(ms*100/self.duration))))
            except ValueError: pass
        if p.poll() is None:
            QTimer.singleShot(100, self.poll_render); return
        self.render.setEnabled(True); self.quick_render.setEnabled(True); self.cancel.setEnabled(False)
        ass=self._render_ass; out=self._render_out
        if ass: Path(ass).unlink(missing_ok=True)
        if p.returncode==0 and Path(out).exists():
            self.progress.setValue(100)
            if self.copy_srt.isChecked():
                Path(out).with_suffix(".srt").write_text(write_srt(self.entries), encoding="utf-8")
            self.status.setText(f"✓ Created: {Path(out).name}")
            QMessageBox.information(self,"Finished",f"Subtitled video created:\n\n{out}")
        else:
            self.progress.setValue(0)
            self.status.setText("Rendering failed. See the video/output settings and FFmpeg installation.")
            QMessageBox.critical(self,"FFmpeg error","FFmpeg could not create the video. Make sure your FFmpeg build has the ASS/subtitles filter.")

    def cancel_render(self):
        if self.render_process and self.render_process.poll() is None:
            self.render_process.terminate()
            self.status.setText("Rendering cancelled.")
            self.render.setEnabled(True); self.quick_render.setEnabled(True); self.cancel.setEnabled(False)


def main():
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet("""
        QMainWindow { background: #f4f5f7; }
        QGroupBox { font-weight: 600; border: 1px solid #d7dbe0; border-radius: 8px; margin-top: 8px; padding-top: 12px; background: white; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QPushButton { padding: 7px 12px; border: 1px solid #c7ccd2; border-radius: 6px; background: #fff; }
        QPushButton:hover { background: #eef4ff; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 6px; border: 1px solid #c7ccd2; border-radius: 5px; background: white; }
        QTableWidget { background: white; border: 1px solid #d7dbe0; }
        #title { font-size: 22px; font-weight: 800; }
        #muted { color: #68717c; }
        #ffmpeg { color: #287a43; font-weight: 600; }
        #status { padding: 7px; color: #374151; background: white; border: 1px solid #d7dbe0; border-radius: 5px; }
    """)
    w=MainWindow(); w.show()
    sys.exit(app.exec())


if __name__=="__main__":
    main()
