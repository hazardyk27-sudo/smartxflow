import os
import sys
import sqlite3
import json
from typing import List, Tuple, Optional, Dict
import re
from datetime import datetime

from PyQt6.QtCore import Qt, QSize, QTimer, QProcess, QThread, QObject, pyqtSignal, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QPainter, QColor, QFont, QFontMetrics, QIcon, QPixmap, QBrush
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QToolButton, QTableView, QLabel, QMessageBox, QHeaderView, QStyledItemDelegate, QStyle,
    QDialog, QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QDialogButtonBox, QProgressBar, QButtonGroup,
    QSizePolicy, QLineEdit, QDateEdit
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from scraper.moneyway import scrape_all, DATASETS, EXTRACTOR_MAP
def _get_default_cookie():
    """Get default cookie from embedded config or scrape_moneyway."""
    try:
        import embedded_config
        if embedded_config.EMBEDDED_COOKIE:
            return embedded_config.EMBEDDED_COOKIE
    except (ImportError, AttributeError):
        pass
    
    try:
        from scrape_moneyway import COOKIE_STRING
        return COOKIE_STRING
    except Exception:
        pass
    
    return None

DEFAULT_COOKIE = _get_default_cookie()
from core.settings import SettingsManager, Settings
from ui.settings_dialog import SettingsDialog

def _user_data_dir():
    name = "SmartXFlow"
    try:
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        elif sys.platform.startswith("win"):
            base = os.getenv("APPDATA") or os.path.expanduser("~")
        else:
            base = os.path.expanduser("~/.local/share")
        path = os.path.join(base, name)
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        p = os.path.join(os.path.dirname(__file__), name)
        try:
            os.makedirs(p, exist_ok=True)
        except Exception:
            pass
        return p

DB_PATH = os.path.join(_user_data_dir(), "moneyway.db")
from core.storage import get_storage
_STORAGE = get_storage(DB_PATH)

def _ensure_db_schema(db_path: str):
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            import re as _re
            def _sanitize(name: str) -> str:
                t = _re.sub(r"[^0-9A-Za-z_]+", "_", name.replace("-", "_"))
                if not _re.match(r"^[A-Za-z]", t):
                    t = "t_" + t
                return t
            for key, _ in EXTRACTOR_MAP.items():
                t = _sanitize(key)
                headers = EXTRACTOR_MAP[key][1]
                cols_def = ", ".join([f'"{h}" TEXT' for h in headers])
                cur.execute(f'CREATE TABLE IF NOT EXISTS "{t}" ({cols_def})')
                hist_headers = list(headers) + ["ScrapedAt"]
                hist_cols = ", ".join([f'"{h}" TEXT' for h in hist_headers])
                cur.execute(f'CREATE TABLE IF NOT EXISTS "{t}_hist" ({hist_cols})')
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

_ensure_db_schema(DB_PATH)

BUTTONS: List[Tuple[str, str]] = [
    ("Moneyway 1-X-2", "moneyway_1x2"),
    ("Moneyway 2.5", "moneyway_ou25"),
    ("Moneyway BTTS", "moneyway_btts"),
    ("ODDS 1-X-2", "dropping_1x2"),
    ("ODDS 2.5", "dropping_ou25"),
    ("ODDS BTTS", "dropping_btts"),
]


class TwoLineCellDelegate(QStyledItemDelegate):
    """Custom delegate to render cells with two lines: top (odds) and bottom (%/£) with dynamic color."""
    def paint(self, painter: QPainter, option, index):
        painter.save()
        # Default background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(60, 60, 60))
        else:
            painter.fillRect(option.rect, QColor(30, 30, 30))

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        parts = str(text).split("\n", 1)
        top_text = parts[0].strip() if parts else ""
        bottom_text = parts[1].strip() if len(parts) > 1 else ""

        # Colors
        top_color = QColor(224, 224, 224)  # light gray
        bottom_color = QColor(192, 192, 192)
        # Parse percent from bottom
        pct_value = None
        import re
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", bottom_text)
        if m:
            try:
                pct_value = float(m.group(1))
            except ValueError:
                pct_value = None
        if pct_value is not None:
            if pct_value >= 90:
                bottom_color = QColor(217, 83, 79)  # red
            elif pct_value >= 80:
                bottom_color = QColor(240, 173, 78)  # amber
            elif pct_value >= 50:
                bottom_color = QColor(240, 173, 78)  # amber (50–80 aralığı)

        # Fonts
        top_font = QFont()
        top_font.setPointSize(10)
        top_font.setBold(True)
        bottom_font = QFont()
        bottom_font.setPointSize(9)

        # Layout: center both lines
        rect = option.rect
        fm_top = QFontMetrics(top_font)
        fm_bottom = QFontMetrics(bottom_font)
        total_h = fm_top.height() + fm_bottom.height()
        y = rect.y() + (rect.height() - total_h) // 2

        # Draw top
        painter.setFont(top_font)
        painter.setPen(top_color)
        top_w = fm_top.horizontalAdvance(top_text)
        x_top = rect.x() + (rect.width() - top_w) // 2
        painter.drawText(x_top, y + fm_top.ascent(), top_text)

        # Draw bottom
        painter.setFont(bottom_font)
        painter.setPen(bottom_color)
        bottom_w = fm_bottom.horizontalAdvance(bottom_text)
        x_bottom = rect.x() + (rect.width() - bottom_w) // 2
        painter.drawText(x_bottom, y + fm_top.height() + fm_bottom.ascent(), bottom_text)
        painter.restore()

    def sizeHint(self, option, index):
        # Provide taller cell height for two lines
        top_font = QFont()
        top_font.setPointSize(10)
        bottom_font = QFont()
        bottom_font.setPointSize(9)
        fm_top = QFontMetrics(top_font)
        fm_bottom = QFontMetrics(bottom_font)
        return QSize(option.rect.width(), fm_top.height() + fm_bottom.height() + 8)


class DroppingTwoLineDelegate(QStyledItemDelegate):
    """Delegate for dropping tables: shows two lines (start and current) with a colored separator and an arrow
    positioned according to change direction."""
    def paint(self, painter: QPainter, option, index):
        painter.save()
        # Background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(60, 60, 60))
        else:
            painter.fillRect(option.rect, QColor(30, 30, 30))

        raw = index.data(Qt.ItemDataRole.DisplayRole) or ""
        parts = [p.strip() for p in str(raw).split("\n") if p.strip()]
        start_text = parts[0] if parts else ""
        cur_text = parts[1] if len(parts) > 1 else (parts[0] if parts else "")

        # Determine change direction
        arrow_char = "→"
        sep_color = QColor(200, 160, 0)  # amber (no change or parse fail)
        try:
            s = float(str(start_text))
            c = float(str(cur_text))
            if c > s:
                arrow_char = "↑"  # up
                sep_color = QColor(0, 200, 0)  # green
            elif c < s:
                arrow_char = "↓"  # down
                sep_color = QColor(220, 70, 60)  # red
        except Exception:
            pass
        self.detail_windows = []

        # Fonts
        font_top = QFont(); font_top.setPointSize(9)
        font_bottom = QFont(); font_bottom.setPointSize(10); font_bottom.setBold(True)
        fm_top = QFontMetrics(font_top)
        fm_bottom = QFontMetrics(font_bottom)

        rect = option.rect
        total_h = fm_top.height() + fm_bottom.height() + 6  # space for separator
        y = rect.y() + (rect.height() - total_h) // 2

        # Draw top line (start)
        painter.setFont(font_top)
        painter.setPen(QColor(200, 200, 210))
        top_w = fm_top.horizontalAdvance(start_text)
        x_top = rect.x() + (rect.width() - top_w) // 2
        painter.drawText(x_top, y + fm_top.ascent(), start_text)

        # Separator
        sep_y = y + fm_top.height() + 2
        margin = 10
        painter.fillRect(rect.x() + margin, sep_y, rect.width() - margin * 2, 3, sep_color)

        # Arrow: always next to the bottom (current) value
        painter.setFont(QFont())
        painter.setPen(sep_color)
        fm_arrow = QFontMetrics(QFont())
        arrow_x = rect.right() - margin - fm_arrow.horizontalAdvance("↑")
        painter.drawText(arrow_x, sep_y + 3 + fm_bottom.ascent(), arrow_char)

        # Draw bottom line (current)
        painter.setFont(font_bottom)
        painter.setPen(QColor(230, 230, 230))
        bottom_w = fm_bottom.horizontalAdvance(cur_text)
        x_bottom = rect.x() + (rect.width() - bottom_w) // 2
        painter.drawText(x_bottom, sep_y + 3 + fm_bottom.ascent(), cur_text)

        painter.restore()

    def sizeHint(self, option, index):
        font_top = QFont(); font_top.setPointSize(9)
        font_bottom = QFont(); font_bottom.setPointSize(10); font_bottom.setBold(True)
        fm_top = QFontMetrics(font_top)
        fm_bottom = QFontMetrics(font_bottom)
        return QSize(option.rect.width(), fm_top.height() + fm_bottom.height() + 16)


class DroppingLineDelegate(QStyledItemDelegate):
    """Delegate for ODDS 1-X-2 cells: draws a colored horizontal bar and up/down arrow next to the current odds."""
    def paint(self, painter: QPainter, option, index):
        painter.save()
        # Background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(60, 60, 60))
        else:
            painter.fillRect(option.rect, QColor(30, 30, 30))

        raw = (index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        # Expect like: "1.96 ↑" or "3.55 ↓" or "3.2 →"
        val_str = raw
        arrow = ""
        if raw.endswith("↑") or raw.endswith("↓") or raw.endswith("→"):
            arrow = raw[-1]
            val_str = raw[:-1].strip()
        # Determine color
        color_up = QColor(0, 200, 0)      # green
        color_down = QColor(220, 70, 60)  # red
        color_eq = QColor(200, 160, 0)    # amber
        bar_color = color_eq
        if arrow == "↑":
            bar_color = color_up
        elif arrow == "↓":
            bar_color = color_down

        rect = option.rect
        margin = 10
        bar_h = 4
        bar_y = rect.y() + rect.height() // 2
        painter.fillRect(rect.x() + margin, bar_y, rect.width() - margin * 2, bar_h, bar_color)

        # Draw odds text (bold white) left side
        font_val = QFont()
        font_val.setPointSize(10)
        font_val.setBold(True)
        painter.setFont(font_val)
        painter.setPen(QColor(230, 230, 230))
        fm = QFontMetrics(font_val)
        painter.drawText(rect.x() + margin, bar_y - 6 + fm.ascent(), val_str)

        # Draw arrow at right side in bar color
        font_arrow = QFont()
        font_arrow.setPointSize(11)
        font_arrow.setBold(True)
        painter.setFont(font_arrow)
        painter.setPen(bar_color)
        painter.drawText(rect.right() - margin - fm.horizontalAdvance("↑"), bar_y - 6 + fm.ascent(), arrow)

        painter.restore()

    def sizeHint(self, option, index):
        font_val = QFont()
        font_val.setPointSize(10)
        fm = QFontMetrics(font_val)
        return QSize(option.rect.width(), max(28, fm.height() + 12))


def fetch_table(table_name: str) -> Tuple[List[str], List[Tuple[str, ...]]]:
    res = _STORAGE.fetch_table_values(table_name)
    return res.headers, res.rows


def to_display(headers: List[str], rows: List[Tuple[str, ...]], table_name: str) -> Tuple[List[str], List[List[str]]]:
    idx = {h: i for i, h in enumerate(headers)}
    # Güvenli hücre erişimi: kolon yoksa boş string döner
    def cell(r: Tuple[str, ...], col: str) -> str:
        i = idx.get(col)
        return "" if i is None else r[i]
    out_rows: List[List[str]] = []
    if table_name == "moneyway_1x2":
        out_headers = ["League", "Date", "Match", "1 %/£", "X %/£", "2 %/£", "Volume", "Info"]
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            # Combine odds + pct/amt as two-line text
            c1 = f"{cell(r,'Odds1')}\n{(str(cell(r,'Pct1')) + ' ' + str(cell(r,'Amt1'))).strip()}"
            cx = f"{cell(r,'OddsX')}\n{(str(cell(r,'PctX')) + ' ' + str(cell(r,'AmtX'))).strip()}"
            c2 = f"{cell(r,'Odds2')}\n{(str(cell(r,'Pct2')) + ' ' + str(cell(r,'Amt2'))).strip()}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                c1, cx, c2,
                cell(r,'Volume'),
                "Click for detailed information",
            ])
    elif table_name == "moneyway_ou25":
        out_headers = ["League", "Date", "Match", "2.5 OVER %/£", "LINE", "2.5 UNDER %/£", "Volume", "Info"]
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            over_c = f"{cell(r,'Over')}\n{(str(cell(r,'PctOver')) + ' ' + str(cell(r,'AmtOver'))).strip()}"
            under_c = f"{cell(r,'Under')}\n{(str(cell(r,'PctUnder')) + ' ' + str(cell(r,'AmtUnder'))).strip()}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                over_c,
                cell(r,'Line'),
                under_c,
                cell(r,'Volume'),
                "Click for detailed information",
            ])
    elif table_name == "moneyway_btts":
        out_headers = ["League", "Date", "Match", "BTTS YES %/£", "BTTS NO %/£", "Volume", "Info"]
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            yes_c = f"{cell(r,'Yes')}\n{(str(cell(r,'PctYes')) + ' ' + str(cell(r,'AmtYes'))).strip()}"
            no_c = f"{cell(r,'No')}\n{(str(cell(r,'PctNo')) + ' ' + str(cell(r,'AmtNo'))).strip()}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                yes_c,
                no_c,
                cell(r,'Volume'),
                "Click for detailed information",
            ])
    elif table_name == "dropping_1x2":
        out_headers = ["League", "Date", "Match", "1", "X", "2", "Volume", "Info"]
        def arrow(cur, start):
            try:
                c = float(cur)
                s = float(start)
                if c > s:
                    return "↑"
                elif c < s:
                    return "↓"
                else:
                    return "→"
            except Exception:
                return "→"
        def split2(txt: str) -> Tuple[str, str]:
            if not txt:
                return "", ""
            parts = [p for p in str(txt).splitlines() if p.strip()]
            if len(parts) >= 2:
                return parts[0].strip(), parts[-1].strip()
            else:
                p = parts[0].strip() if parts else ""
                return p, p
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            if 'Odds1_cur' in idx:
                c1 = cell(r,'Odds1_cur')
                s1 = cell(r,'Odds1_start')
                cx = cell(r,'OddsX_cur')
                sx = cell(r,'OddsX_start')
                c2 = cell(r,'Odds2_cur')
                s2 = cell(r,'Odds2_start')
            else:
                s1, c1 = split2(cell(r,'1'))
                sx, cx = split2(cell(r,'X'))
                s2, c2 = split2(cell(r,'2'))
            # Show as two lines: start on top, current below
            t1 = f"{s1}\n{c1}"
            tx = f"{sx}\n{cx}"
            t2 = f"{s2}\n{c2}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                t1, tx, t2,
                cell(r,'Volume'),
                "Click for detailed information",
            ])

    elif table_name == "dropping_ou25":
        out_headers = ["League", "Date", "Match", "2.5 OVER", "ASTAR", "2.5 UNDER", "Volume", "Info"]
        def split2(txt: str) -> Tuple[str, str]:
            if not txt:
                return "", ""
            parts = [p for p in str(txt).splitlines() if p.strip()]
            if len(parts) >= 2:
                return parts[0].strip(), parts[-1].strip()
            else:
                p = parts[0].strip() if parts else ""
                return p, p
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            sOver, cOver = split2(cell(r,'Over'))
            sUnder, cUnder = split2(cell(r,'Under'))
            tOver = f"{sOver}\n{cOver}"
            tUnder = f"{sUnder}\n{cUnder}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                tOver,
                cell(r,'Astar'),
                tUnder,
                cell(r,'Volume'),
                "Click for detailed information",
            ])
    elif table_name == "dropping_btts":
        out_headers = ["League", "Date", "Match", "BTTS YES", "BTTS NO", "Volume", "Info"]
        def split2(txt: str) -> Tuple[str, str]:
            if not txt:
                return "", ""
            parts = [p for p in str(txt).splitlines() if p.strip()]
            if len(parts) >= 2:
                return parts[0].strip(), parts[-1].strip()
            else:
                p = parts[0].strip() if parts else ""
                return p, p
        for r in rows:
            match = f"{cell(r,'Home')} - {cell(r,'Away')}"
            sYes, cYes = split2(cell(r,'Yes'))
            sNo, cNo = split2(cell(r,'No'))
            tYes = f"{sYes}\n{cYes}"
            tNo = f"{sNo}\n{cNo}"
            out_rows.append([
                cell(r,'League'),
                cell(r,'Date'),
                match,
                tYes,
                tNo,
                cell(r,'Volume'),
                "Click for detailed information",
            ])
    else:
        # Varsayılan: ham tablo
        out_headers = headers
        out_rows = [list(map(str, r)) for r in rows]
    return out_headers, out_rows


# --- Date/Volume filtreleme ve doğru sıralama için proxy model ---
class FilterSortProxyModel(QSortFilterProxyModel):
    DATE_COL = 1
    VOLUME_COL = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        self.date_from = None  # datetime or None
        self.date_to = None    # datetime or None
        self.volume_min = None # float or None
        self.volume_max = None # float or None

    def set_date_filter_strings(self, s_from: str, s_to: str):
        self.date_from = self._parse_date(s_from.strip()) if s_from and s_from.strip() else None
        self.date_to = self._parse_date(s_to.strip()) if s_to and s_to.strip() else None
        try:
            print(f"[ApplyDateFilter] from='{s_from}' -> {self.date_from}, to='{s_to}' -> {self.date_to}")
        except Exception:
            pass
        self.invalidateFilter()

    def set_volume_filter_strings(self, s_min: str, s_max: str):
        self.volume_min = self._parse_amount(s_min.strip()) if s_min and s_min.strip() else None
        self.volume_max = self._parse_amount(s_max.strip()) if s_max and s_max.strip() else None
        self.invalidateFilter()

    def lessThan(self, left, right):
        col = left.column()
        lm = left.model()
        rm = right.model()
        lv = lm.data(left)
        rv = rm.data(right)
        if col == self.DATE_COL:
            ld = self._parse_date(str(lv))
            rd = self._parse_date(str(rv))
            if ld and rd:
                return ld < rd
            return str(lv) < str(rv)
        if col == self.VOLUME_COL:
            la = self._parse_amount(str(lv))
            ra = self._parse_amount(str(rv))
            if la is not None and ra is not None:
                return la < ra
            return str(lv) < str(rv)
        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row, source_parent):
        sm = self.sourceModel()
        if sm is None:
            return True
        idx_date = sm.index(source_row, self.DATE_COL, source_parent)
        date_str = sm.data(idx_date)
        d = self._parse_date(str(date_str) if date_str is not None else '')
        has_date_filter = bool(self.date_from or self.date_to)
        date_ok = True
        if has_date_filter:
            if d is None:
                date_ok = False
            else:
                if self.date_from and d < self.date_from:
                    date_ok = False
                if self.date_to and d > self.date_to:
                    date_ok = False
        idx_vol = sm.index(source_row, self.VOLUME_COL, source_parent)
        vol_str = sm.data(idx_vol)
        v = self._parse_amount(str(vol_str) if vol_str is not None else '')
        has_vol_filter = (self.volume_min is not None) or (self.volume_max is not None)
        volume_ok = True
        if has_vol_filter:
            if v is None:
                volume_ok = False
            else:
                if self.volume_min is not None and v < self.volume_min:
                    volume_ok = False
                if self.volume_max is not None and v > self.volume_max:
                    volume_ok = False
        if not has_date_filter and not has_vol_filter:
            return True
        accept = (has_date_filter and date_ok) or (has_vol_filter and volume_ok)
        try:
            if self._dbg_rows_printed < 50:
                print(f"[FilterRow] row={source_row} date='{date_str}' -> {d}, vol='{vol_str}' -> {v}, has_date={has_date_filter}, date_ok={date_ok}, has_vol={has_vol_filter}, volume_ok={volume_ok}, accept={accept}")
                self._dbg_rows_printed += 1
        except Exception:
            pass
        return (has_date_filter and date_ok) or (has_vol_filter and volume_ok)

    # Yardımcı parse fonksiyonları
    def _parse_date(self, s: str):
        if not s:
            return None
        from datetime import datetime
        s_norm = s.strip()
        fmts = [
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
            '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M', '%d.%m.%Y',
        ]
        for fmt in fmts:
            try:
                return datetime.strptime(s_norm, fmt)
            except Exception:
                continue
        try:
            val = datetime.fromisoformat(s_norm)
            try:
                print(f"[DateParse iso] '{s_norm}' -> {val}")
            except Exception:
                pass
            return val
        except Exception:
            pass
        try:
            import re
            m = re.match(r'^(\d{1,2})\.(\w{3})\s+(\d{1,2}:\d{2}(?::\d{2})?)$', s_norm)
            if m:
                day = int(m.group(1))
                mon = m.group(2).lower()
                time_part = m.group(3)
                mon_map = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                    'oca': 1, 'şub': 2, 'sub': 2, 'mar': 3, 'nis': 4, 'may': 5, 'haz': 6,
                    'tem': 7, 'ağu': 8, 'agu': 8, 'eyl': 9, 'eki': 10, 'kas': 11, 'ara': 12,
                }
                if mon in mon_map:
                    month = mon_map[mon]
                    try:
                        hh, mm, ss = (time_part+':00').split(':')[0:3] if time_part.count(':') == 1 else time_part.split(':')
                        hh = int(hh); mm = int(mm); ss = int(ss)
                        today = datetime.today()
                        dt_val = datetime(today.year, month, day, hh, mm, ss)
                        try:
                            print(f"[DateParse mon] '{s_norm}' -> {dt_val}")
                        except Exception:
                            pass
                        return dt_val
                    except Exception:
                        pass
        except Exception:
            pass
        import re
        m = re.match(r'^(\d{4}-\d{2}-\d{2})', s_norm)
        if m:
            try:
                val = datetime.strptime(m.group(1), '%Y-%m-%d')
                try:
                    print(f"[DateParse ymd] '{s_norm}' -> {val}")
                except Exception:
                    pass
                return val
            except Exception:
                pass
        try:
            print(f"[DateParse fail] '{s_norm}' -> None")
        except Exception:
            pass
        return None

    def _parse_amount(self, s: str):
        if not s:
            return None
        txt = s.strip()
        import re
        suf = None
        if txt.lower().endswith('k'):
            suf = 'k'
            txt = txt[:-1]
        elif txt.lower().endswith('m'):
            suf = 'm'
            txt = txt[:-1]
        txt = re.sub(r'[^0-9.,]', '', txt)
        if not txt:
            return None
        if ',' in txt and '.' in txt:
            if txt.rfind(',') > txt.rfind('.'):
                txt = txt.replace('.', '').replace(',', '.')
            else:
                txt = txt.replace(',', '')
        else:
            txt = txt.replace(',', '')
        try:
            val = float(txt)
        except Exception:
            return None
        if suf == 'k':
            val *= 1_000
        elif suf == 'm':
            val *= 1_000_000
        return val

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartXFlow")
        self.resize(1200, 700)
        
        # Ana widget
        cw = QWidget(self)
        self.setCentralWidget(cw)
        self.vbox = QVBoxLayout(cw)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setSpacing(8)
        
        # Üst başlık barı (sol: ayarlar, yanında marka)
        header_bar = QHBoxLayout()
        self.settings_btn = QToolButton(self)
        self.settings_btn.setText("")
        self.settings_btn.setToolTip("Ayarlar")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        try:
            self.settings_btn.setIcon(self._make_gear_icon(22))
            self.settings_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        except Exception:
            pass
        header_bar.addWidget(self.settings_btn)
        
        self.brand = QLabel("SmartXFlow")
        self.brand.setObjectName("Brand")
        header_bar.addWidget(self.brand)
        header_bar.addStretch(1)
        self.start_scrape_btn = QPushButton("Periyodik Veri Çekmeyi Başlat")
        self.start_scrape_btn.clicked.connect(self.start_periodic_scraping)
        header_bar.addWidget(self.start_scrape_btn)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        header_bar.addWidget(self.progress)
        self.countdown_label = QLabel("")
        header_bar.addWidget(self.countdown_label)
        self.vbox.addLayout(header_bar)
        
        # Üst buton paneli
        self.btn_bar = QHBoxLayout()
        self.btns: List[QPushButton] = []
        for label, table in BUTTONS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda checked, t=table, btn_label=label: self.load_table(t, btn_label))
            self.btn_bar.addWidget(b)
            self.btns.append(b)
        self.vbox.addLayout(self.btn_bar)
        
        # --- Filtre barı: Date ve Volume için ---
        self.filter_bar = QHBoxLayout()
        self.filter_bar.setSpacing(6)
        self.filter_bar.addWidget(QLabel("Tarih >="))
        self.date_from_edit = QDateEdit(self)
        self.date_from_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_from_edit.setCalendarPopup(True)
        self._date_from_active = False
        self.date_from_edit.dateChanged.connect(lambda _: self._on_date_changed('from'))
        self.filter_bar.addWidget(self.date_from_edit)
        self.date_from_clear_btn = QToolButton(self)
        self.date_from_clear_btn.setText("×")
        self.date_from_clear_btn.clicked.connect(lambda: self._clear_single_date('from'))
        self.filter_bar.addWidget(self.date_from_clear_btn)
        self.filter_bar.addWidget(QLabel("Tarih <="))
        self.date_to_edit = QDateEdit(self)
        self.date_to_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_to_edit.setCalendarPopup(True)
        self._date_to_active = False
        self.date_to_edit.dateChanged.connect(lambda _: self._on_date_changed('to'))
        self.filter_bar.addWidget(self.date_to_edit)
        self.date_to_clear_btn = QToolButton(self)
        self.date_to_clear_btn.setText("×")
        self.date_to_clear_btn.clicked.connect(lambda: self._clear_single_date('to'))
        self.filter_bar.addWidget(self.date_to_clear_btn)
        self.filter_bar.addWidget(QLabel("Hacim >="))
        self.volume_min_edit = QLineEdit(self)
        self.volume_min_edit.setPlaceholderText("Örn: 1000, 1.5k, 2m")
        self.volume_min_edit.textChanged.connect(self._on_filter_changed)
        self.filter_bar.addWidget(self.volume_min_edit)
        self.filter_bar.addWidget(QLabel("Hacim <="))
        self.volume_max_edit = QLineEdit(self)
        self.volume_max_edit.setPlaceholderText("Örn: 5000, 2k, 3m")
        self.volume_max_edit.textChanged.connect(self._on_filter_changed)
        self.filter_bar.addWidget(self.volume_max_edit)
        self.apply_filters_btn = QPushButton("Filtreleri Uygula", self)
        self.apply_filters_btn.clicked.connect(self._on_filter_changed)
        self.filter_bar.addWidget(self.apply_filters_btn)
        self.clear_filters_btn = QPushButton("Filtreleri Temizle", self)
        self.clear_filters_btn.clicked.connect(self._clear_filters)
        self.filter_bar.addWidget(self.clear_filters_btn)
        self.vbox.addLayout(self.filter_bar)
        
        # Tablo görünümü
        self.table = QTableView(self)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        # Sayfayı kaplaması için genişlet
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header = self.table.horizontalHeader()
        # Kolonları pencereye göre esnet
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(50)
        # Satır yüksekliğini artır
        try:
            self.table.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        # Vbox içinde genişlik/yükseklik payı ver
        self.vbox.addWidget(self.table, 1)
        # Çift tıklama ile maç detayına aç
        self.table.doubleClicked.connect(self.on_row_double_clicked)
        
        # Proxy model
        self.proxy = FilterSortProxyModel(self)
        
        # Alt durum etiketi
        self.status_label = QLabel("")
        self.vbox.addWidget(self.status_label)
        
        # Zamanlayıcı ve process state
        self.scrape_timer = None
        self.scrape_process = None
        self.scrape_value = 1
        self.scrape_unit_index = 0  # 0: Dakika, 1: Saat
        self.scrape_thread = None
        self.scrape_worker = None
        self.cookie_string = DEFAULT_COOKIE
        try:
            mgr = SettingsManager(os.path.join(_user_data_dir(), "settings.json"))
            s = load_settings = mgr.load
            st = s()
            self.scrape_value = st.scrape_value
            self.scrape_unit_index = st.scrape_unit_index
            if st.cookie_string:
                self.cookie_string = st.cookie_string
            self._settings_mgr = mgr
            self.status_label.setText(f"Periyot yüklendi: {self.scrape_value} {'Dakika' if self.scrape_unit_index==0 else 'Saat'}")
        except Exception:
            pass
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setSingleShot(False)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start()
        
        self.apply_dark_theme()
        # Varsayılan: ilk buton
        if self.btns:
            self.btns[0].setChecked(True)
            self.load_table(BUTTONS[0][1], BUTTONS[0][0])

    def open_settings_dialog(self):
        dlg = SettingsDialog(self.scrape_value, self.scrape_unit_index, self.cookie_string, parent=self)
        if dlg.exec():
            v, u, c = dlg.get_values()
            self.scrape_value = int(v)
            self.scrape_unit_index = int(u)
            self.cookie_string = c
            interval_ms = self.scrape_value * (60 * 1000 if self.scrape_unit_index == 0 else 60 * 60 * 1000)
            self._start_scrape_timer(interval_ms)
            self.status_label.setText(f"Periyot ayarlandı: {self.scrape_value} {'Dakika' if self.scrape_unit_index==0 else 'Saat'}")
            try:
                st = Settings(scrape_value=self.scrape_value, scrape_unit_index=self.scrape_unit_index, cookie_string=self.cookie_string)
                self._settings_mgr.save(st)
            except Exception:
                pass

    def _start_scrape_timer(self, interval_ms: int):
        if self.scrape_timer is None:
            self.scrape_timer = QTimer(self)
            self.scrape_timer.setSingleShot(False)
            self.scrape_timer.timeout.connect(self._run_scraper)
        self.scrape_timer.start(interval_ms)
        print(f"Scrape zamanlayıcı başlatıldı: {interval_ms} ms")
        # İlk çalıştırmayı hemen tetikle
        print("İlk scrape tetikleniyor...")
        self._run_scraper()

    def start_periodic_scraping(self):
        interval_ms = self.scrape_value * (60 * 1000 if self.scrape_unit_index == 0 else 60 * 60 * 1000)
        self._start_scrape_timer(interval_ms)
        self.status_label.setText(
            f"Periyodik çekim başlatıldı: her {self.scrape_value} "
            f"{'dakika' if self.scrape_unit_index == 0 else 'saat'}."
        )
        if hasattr(self, "_settings_mgr"):
            try:
                st = Settings(
                    scrape_value=self.scrape_value,
                    scrape_unit_index=self.scrape_unit_index,
                    cookie_string=self.cookie_string,
                )
                self._settings_mgr.save(st)
            except Exception:
                pass


    def _make_gear_icon(self, size: int) -> QIcon:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QColor(220,220,220))
            f = QFont()
            f.setPointSize(int(size*0.8))
            f.setBold(True)
            p.setFont(f)
            fm = QFontMetrics(f)
            text = "⚙"
            w = fm.horizontalAdvance(text)
            h = fm.height()
            x = (size - w)//2
            y = (size + h)//2 - fm.descent()
            p.drawText(x, y, text)
        finally:
            p.end()
        return QIcon(pm)

    def _run_scraper(self):
        if getattr(self, 'scrape_thread', None) and self.scrape_thread.isRunning():
            self.status_label.setText("Önceki çekim devam ediyor, yeni tetikleme atlandı.")
            return
        self.status_label.setText("Scrape başlatılıyor...")
        try:
            self.progress.setMaximum(len(DATASETS))
            self.progress.setValue(0)
            self.progress.setVisible(True)
            self.start_scrape_btn.setEnabled(False)
        except Exception:
            pass
        self.scrape_thread = QThread(self)
        self.scrape_worker = ScrapeWorker(_user_data_dir(), True, self.cookie_string)
        self.scrape_worker.moveToThread(self.scrape_thread)
        def on_progress(msg, i, n):
            self.progress.setMaximum(n)
            self.progress.setValue(i)
            self.status_label.setText(msg)
        def on_finished(code):
            self.status_label.setText(f"Scrape tamamlandı (kod={code}).")
            try:
                self.progress.setVisible(False)
                self.start_scrape_btn.setEnabled(True)
            except Exception:
                pass
            try:
                orig_name = getattr(self, 'current_table_name', None)
                orig_label = None
                if orig_name:
                    for L, T in BUTTONS:
                        if T == orig_name:
                            orig_label = L
                            break
                for L, T in BUTTONS:
                    self.load_table(T, L)
                if orig_name and orig_label:
                    self.load_table(orig_name, orig_label)
                for w in getattr(self, 'detail_windows', []):
                    try:
                        w._redraw()
                    except Exception:
                        pass
            except Exception:
                pass
            self.scrape_thread.quit()
        def on_error(msg):
            try:
                self.progress.setVisible(False)
                self.start_scrape_btn.setEnabled(True)
            except Exception:
                pass
            QMessageBox.critical(self, "Scrape Hatası", str(msg))
        self.scrape_thread.started.connect(self.scrape_worker.run)
        self.scrape_worker.progress.connect(on_progress)
        self.scrape_worker.finished.connect(on_finished)
        self.scrape_worker.error.connect(on_error)
        self.scrape_thread.start()

    def _update_countdown(self):
        try:
            if getattr(self, 'scrape_thread', None) and self.scrape_thread.isRunning():
                self.countdown_label.setText("Çekim devam ediyor")
                return
            if self.scrape_timer and self.scrape_timer.isActive():
                ms = self.scrape_timer.remainingTime()
                s = max(0, int(ms/1000))
                m = s // 60
                sec = s % 60
                self.countdown_label.setText(f"Sonraki çekime: {m:02d}:{sec:02d}")
            else:
                self.countdown_label.setText("Periyot kapalı")
        except Exception:
            pass

    def apply_dark_theme(self):
        self.setStyleSheet(
            """
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QLabel#Brand { font-size: 28px; font-weight: 800; color: #e0e0e0; padding: 4px 0 2px 4px; }
            QPushButton { background: #2b2b2b; border: 1px solid #444; padding: 8px 12px; border-radius: 6px; }
            QPushButton:hover { background: #333; }
            QPushButton:checked { background: #444; border: 1px solid #777; }
            QTableView { gridline-color: #444; alternate-background-color: #2b2b2b; background-color: #1e1e1e; }
            QHeaderView::section { background: #2b2b2b; color: #e0e0e0; padding: 6px; border: 1px solid #444; }
            """
        )

    def _apply_delegates(self, table_name: str, model: QStandardItemModel):
        delegate = TwoLineCellDelegate(self.table)
        drop_delegate = DroppingTwoLineDelegate(self.table)
        if table_name == "moneyway_1x2":
            self.table.setItemDelegateForColumn(3, delegate)
            self.table.setItemDelegateForColumn(4, delegate)
            self.table.setItemDelegateForColumn(5, delegate)
        elif table_name == "dropping_1x2":
            self.table.setItemDelegateForColumn(3, drop_delegate)
            self.table.setItemDelegateForColumn(4, drop_delegate)
            self.table.setItemDelegateForColumn(5, drop_delegate)
        elif table_name == "moneyway_ou25":
            self.table.setItemDelegateForColumn(3, delegate)
            self.table.setItemDelegateForColumn(5, delegate)
        elif table_name == "dropping_ou25":
            # Over/Under iki satırlı; ASTAR tek satır basit metin, bu yüzden ortadaki sütunda özel delegate yok
            self.table.setItemDelegateForColumn(3, drop_delegate)
            # sütun-4 (ASTAR) için delegate kaldırılıyor
            self.table.setItemDelegateForColumn(5, drop_delegate)
        elif table_name == "moneyway_btts":
            self.table.setItemDelegateForColumn(3, delegate)
            self.table.setItemDelegateForColumn(4, delegate)
        elif table_name == "dropping_btts":
            self.table.setItemDelegateForColumn(3, drop_delegate)
            self.table.setItemDelegateForColumn(4, drop_delegate)
        # Date sütunu altı çizili
        from PyQt6.QtGui import QBrush
        for row in range(model.rowCount()):
            it = model.item(row, 1)
            if it:
                f = it.font()
                f.setUnderline(True)
                it.setFont(f)
                it.setForeground(QBrush(QColor(180, 180, 200)))

    def load_table(self, table_name: str, label: str):
        # Toggle check state
        for b in self.btns:
            b.setChecked(b.text() == label)
        # Seçili tablo adını sakla (detay penceresi için gerekli)
        self.current_table_name = table_name
        try:
            headers, rows = fetch_table(table_name)
            dheaders, drows = to_display(headers, rows, table_name)
            model = QStandardItemModel()
            model.setColumnCount(len(dheaders))
            model.setHorizontalHeaderLabels(dheaders)
            for row in drows:
                items = []
                for col_index, val in enumerate(row):
                    it = QStandardItem(str(val))
                    it.setEditable(False)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    items.append(it)
                model.appendRow(items)
            # Proxy model üzerinden tabloya bağla
            if not hasattr(self, 'proxy') or self.proxy is None:
                self.proxy = FilterSortProxyModel(self)
            self.proxy.setSourceModel(model)
            self.table.setModel(self.proxy)
            # Model yüklendikten sonra kolonlar pencereye göre esnesin
            try:
                hdr = self.table.horizontalHeader()
                hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                hdr.setStretchLastSection(True)
                hdr.setMinimumSectionSize(50)
            except Exception:
                pass
            # Mevcut filtre değerlerini uygula
            try:
                self._on_filter_changed()
            except Exception:
                pass
            self._apply_delegates(table_name, model)
            # Stretch modunda içerik boyutuna göre yeniden boyutlandırma gereksiz
            self.status_label.setText(f"Loaded: {label} (rows: {len(drows)})")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Tablo yüklenemedi: {label}\n\n{e}")

    def _on_filter_changed(self):
        try:
            if hasattr(self, 'proxy') and self.proxy:
                src = self.proxy.sourceModel()
                vol_col = FilterSortProxyModel.VOLUME_COL
                date_col = FilterSortProxyModel.DATE_COL
                if src is not None:
                    headers = [src.headerData(i, Qt.Orientation.Horizontal) for i in range(src.columnCount())]
                    try:
                        if headers:
                            if 'Volume' in headers:
                                vol_col = headers.index('Volume')
                            if 'Date' in headers:
                                date_col = headers.index('Date')
                    except Exception:
                        pass
                # Proxy kolonlarını güncelle
                self.proxy.DATE_COL = date_col
                self.proxy.VOLUME_COL = vol_col
                # Değerleri uygula
                from_str = self.date_from_edit.date().toString('yyyy-MM-dd') if getattr(self, '_date_from_active', False) else ''
                to_str = self.date_to_edit.date().toString('yyyy-MM-dd') if getattr(self, '_date_to_active', False) else ''
                try:
                    print(f"[UI] apply filters from='{from_str}', to='{to_str}', vol_min='{self.volume_min_edit.text()}', vol_max='{self.volume_max_edit.text()}', date_col={date_col}, vol_col={vol_col}")
                except Exception:
                    pass
                self.proxy.set_date_filter_strings(from_str, to_str)
                self.proxy.set_volume_filter_strings(self.volume_min_edit.text(), self.volume_max_edit.text())
                try:
                    total_rows = src.rowCount() if src is not None else 0
                    shown_rows = self.proxy.rowCount()
                    self.status_label.setText(f"Filtre uygulandı: {shown_rows}/{total_rows} satır gösteriliyor")
                except Exception:
                    pass
        except Exception:
            pass

    def _on_date_changed(self, which: str):
        try:
            if which == 'from':
                self._date_from_active = True
                try:
                    print(f"[UI] date_changed from='{self.date_from_edit.date().toString('yyyy-MM-dd')}' active=True")
                except Exception:
                    pass
            else:
                self._date_to_active = True
                try:
                    print(f"[UI] date_changed to='{self.date_to_edit.date().toString('yyyy-MM-dd')}' active=True")
                except Exception:
                    pass
            self._on_filter_changed()
        except Exception:
            pass

    def _clear_filters(self):
        try:
            self.date_from_edit.blockSignals(True)
            self.date_to_edit.blockSignals(True)
            self.volume_min_edit.blockSignals(True)
            self.volume_max_edit.blockSignals(True)
            self._date_from_active = False
            self._date_to_active = False
            self.volume_min_edit.clear()
            self.volume_max_edit.clear()
        finally:
            try:
                self.date_from_edit.blockSignals(False)
                self.date_to_edit.blockSignals(False)
                self.volume_min_edit.blockSignals(False)
                self.volume_max_edit.blockSignals(False)
            except Exception:
                pass
        self._on_filter_changed()

    def _clear_single_date(self, which: str):
        try:
            if which == 'from':
                self._date_from_active = False
            else:
                self._date_to_active = False
            self._on_filter_changed()
        except Exception:
            pass

    def on_row_double_clicked(self, index):
        if not self.current_table_name:
            return
        # Proxy indexini kaynak modele çevir (proxy aktif olabilir)
        if hasattr(self, 'proxy') and self.table.model() is self.proxy:
            src_index = self.proxy.mapToSource(index)
            model = self.proxy.sourceModel()
            row = src_index.row()
        else:
            model = self.table.model()
            row = index.row()
        # Kolonlar: 0 League, 1 Date, 2 Match
        league_text = model.item(row, 0).text() if model.item(row, 0) else ""
        date_text = model.item(row, 1).text() if model.item(row, 1) else ""
        match_text = model.item(row, 2).text() if model.item(row, 2) else ""
        if " - " not in match_text:
            return
        home, away = [p.strip() for p in match_text.split(" - ", 1)]
        dlg = MatchDetailWindow(DB_PATH, self.current_table_name, home, away, date_text, league_text, parent=self)
        try:
            self.detail_windows.append(dlg)
            dlg.finished.connect(lambda _: self._remove_detail_window(dlg))
        except Exception:
            pass
        dlg.exec()

    def _remove_detail_window(self, w):
        try:
            self.detail_windows = [x for x in self.detail_windows if x is not w]
        except Exception:
            self.detail_windows = []


def _compute_axis_bounds(series_values: dict) -> Tuple[float, float]:
    """Determine a comfortable y-axis range for the current odds series."""
    collected: List[float] = []
    for values in series_values.values():
        for val in values:
            if isinstance(val, (int, float)):
                collected.append(float(val))
    if not collected:
        return 0.0, 5.0
    min_v = min(collected)
    max_v = max(collected)
    if max_v == min_v:
        padding = max(0.2, min_v * 0.1 if min_v else 0.2)
    else:
        padding = max(0.2, (max_v - min_v) * 0.1)
    lower = max(0.0, min_v - padding)
    upper = max_v + padding
    return lower, upper

class MatchDetailWindow(QDialog):
    def __init__(self, db_path: str, table_name: str, home: str, away: str, date: str, league: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{home} - {away}")
        self.resize(1350, 820)
        self.setMinimumSize(1180, 760)
        main = QHBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)
        self._table_name = table_name
        self._db_path = db_path
        self._storage = get_storage(db_path)
        self._home = home
        self._away = away
        self._league = league

        # Sol panel: başlık ve 1-X-2 istatistikleri
        left_container = QWidget(self)
        left_container.setObjectName("DetailLeftPanel")
        left_container.setMinimumWidth(320)
        left_container.setMaximumWidth(430)
        left_container.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding))
        left = QVBoxLayout(left_container)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        title = QLabel(f"{home} - {away}")
        title.setStyleSheet("font-size:26px; font-weight:800; color:#e0e0e0;")
        left.addWidget(title)
        meta = QLabel(f"{league}\n{date}")
        meta.setStyleSheet("font-size:13px; color:#c0c0c8;")
        left.addWidget(meta)
        refresh_btn = QPushButton("Yenile")
        left.addWidget(refresh_btn)

        # Moneyway 1X2: sadece yüzde ve hacim
        stats = QTableWidget(2, 3)
        stats.setObjectName("Moneyway1x2StatsTable")
        stats.setStyleSheet(
            """
#Moneyway1x2StatsTable::item {
    padding: 10px 6px;
    border: none;
}
#Moneyway1x2StatsTable::item:hover {
    background-color: rgba(255, 255, 255, 0.08);
}
"""
        )
        stats.setHorizontalHeaderLabels(["1", "X", "2"])
        stats.setVerticalHeaderLabels(["%", "Volume"])
        stats.verticalHeader().setVisible(True)
        try:
            stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats.setVisible(table_name == 'moneyway_1x2')
        left.addWidget(stats)

        # Odds 1X2: Open, Current, Change %, Volume
        stats_drop_1x2 = QTableWidget(4, 3)
        stats_drop_1x2.setHorizontalHeaderLabels(["1", "X", "2"])
        stats_drop_1x2.setVerticalHeaderLabels(["Open", "Current", "Change %", "Volume"])
        stats_drop_1x2.verticalHeader().setVisible(True)
        try:
            stats_drop_1x2.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats_drop_1x2.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats_drop_1x2.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats_drop_1x2.setVisible(table_name == 'dropping_1x2')
        left.addWidget(stats_drop_1x2)

        # Moneyway 2.5: sadece yüzde ve hacim (Under/Over)
        stats_mw_ou25 = QTableWidget(2, 2)
        stats_mw_ou25.setHorizontalHeaderLabels(["Under", "Over"])
        stats_mw_ou25.setVerticalHeaderLabels(["%", "Volume"])
        stats_mw_ou25.verticalHeader().setVisible(True)
        try:
            stats_mw_ou25.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats_mw_ou25.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats_mw_ou25.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats_mw_ou25.setVisible(table_name == 'moneyway_ou25')
        left.addWidget(stats_mw_ou25)

        # Odds 2.5: sadece Open, Current, Change % (Under/Over)
        stats_drop_ou25 = QTableWidget(3, 2)
        stats_drop_ou25.setHorizontalHeaderLabels(["Under", "Over"])
        stats_drop_ou25.setVerticalHeaderLabels(["Open", "Current", "Change %"])
        stats_drop_ou25.verticalHeader().setVisible(True)
        try:
            stats_drop_ou25.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats_drop_ou25.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats_drop_ou25.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats_drop_ou25.setVisible(table_name == 'dropping_ou25')
        left.addWidget(stats_drop_ou25)

        stats_mw_btts = QTableWidget(4, 2)
        stats_mw_btts.setHorizontalHeaderLabels(["Yes", "No"])
        stats_mw_btts.setVerticalHeaderLabels(["Odds", "%", "£", "Volume"])
        stats_mw_btts.verticalHeader().setVisible(True)
        try:
            stats_mw_btts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats_mw_btts.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats_mw_btts.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats_mw_btts.setVisible(table_name == 'moneyway_btts')
        left.addWidget(stats_mw_btts)

        stats_drop_btts = QTableWidget(3, 2)
        stats_drop_btts.setHorizontalHeaderLabels(["Yes", "No"])
        stats_drop_btts.setVerticalHeaderLabels(["Open", "Cur", "Volume"])
        stats_drop_btts.verticalHeader().setVisible(True)
        try:
            stats_drop_btts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            stats_drop_btts.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            stats_drop_btts.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        stats_drop_btts.setVisible(table_name == 'dropping_btts')
        left.addWidget(stats_drop_btts)

        # Nokta detay tablosu: başlangıçta gizli, tıklanınca seçilen tarihin 1/X/2 oranlarını gösterir
        point_tbl = QTableWidget(1, 3)
        point_tbl.setObjectName("PointDetailTable")
        point_tbl.setStyleSheet(
            """
#PointDetailTable::item {
    padding: 10px 6px;
}
#PointDetailTable::item:hover {
    background-color: rgba(255, 255, 255, 0.08);
}
"""
        )
        point_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        try:
            point_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            point_tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            point_tbl.verticalHeader().setDefaultSectionSize(38)
        except Exception:
            pass
        point_tbl.setVisible(False)
        left.addWidget(point_tbl)
        self.point_tbl = point_tbl

        # Sağ panel: grafik
        right_container = QWidget(self)
        right_container.setObjectName("DetailRightPanel")
        right_container.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        right = QVBoxLayout(right_container)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        datasets_widget = QWidget(self)
        datasets_widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
        dataset_bar = QGridLayout(datasets_widget)
        dataset_bar.setContentsMargins(0, 0, 0, 0)
        dataset_bar.setHorizontalSpacing(6)
        dataset_bar.setVerticalSpacing(6)
        self._dataset_buttons = {}
        self._dataset_button_group = QButtonGroup(self)
        self._dataset_button_group.setExclusive(True)
        columns = 3
        for idx, (btn_label, dataset_name) in enumerate(BUTTONS):
            btn = QPushButton(btn_label)
            btn.setCheckable(True)
            btn.setChecked(dataset_name == table_name)
            btn.setMinimumHeight(32)
            self._dataset_button_group.addButton(btn)
            dataset_bar.addWidget(btn, idx // columns, idx % columns)
            btn.clicked.connect(lambda _, ds=dataset_name: self._handle_dataset_selection(ds))
            self._dataset_buttons[dataset_name] = btn
        for col in range(columns):
            dataset_bar.setColumnStretch(col, 1)
        right.addWidget(datasets_widget, 0)
        fig = Figure(facecolor="#1e1e1e")
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        ax = fig.add_subplot(111)
        fig.subplots_adjust(bottom=0.22, top=0.95, left=0.08, right=0.98)
        ax.set_facecolor("#1e1e1e")
        ax.spines['bottom'].set_color('#aaaaaa')
        ax.spines['top'].set_color('#aaaaaa')
        ax.spines['right'].set_color('#aaaaaa')
        ax.spines['left'].set_color('#aaaaaa')
        ax.tick_params(colors='#cccccc')
        ax.set_ylabel("Odds", color="#cccccc")
        ax.set_xlabel("Date", color="#cccccc")
        right.addWidget(canvas, 1)
        self._ax = ax
        self._canvas = canvas
        self._stats_tbl = stats
        self._stats_tbl_drop_1x2 = stats_drop_1x2
        self._stats_tbl_mw_ou25 = stats_mw_ou25
        self._stats_tbl_drop_ou25 = stats_drop_ou25
        self._stats_tbl_mw_btts = stats_mw_btts
        self._stats_tbl_drop_btts = stats_drop_btts

        # Layoutu birleştir
        main.addWidget(left_container, 0)
        main.addWidget(right_container, 1)
        main.setStretch(0, 0)
        main.setStretch(1, 1)

        self._labels = []
        self._series_keys = []
        self._values_by_series = {}
        self._point_rows = []
        self._highlight_artists = []
        self._vline = None
        self._redraw()

         # Pick handler: noktaya tıklanınca sol alttaki tabloyu seçilen tarihin oranlarıyla doldur
        refresh_btn.clicked.connect(self._redraw)
        def on_pick(event):
            try:
                inds = event.ind
                if not inds:
                    return
                artist = getattr(event, "artist", None)
                if artist is None:
                    return
                label_idx = None
                if hasattr(artist, "get_xdata"):
                    xdata = artist.get_xdata()
                    idx_in_line = int(inds[0])
                    if idx_in_line < 0 or idx_in_line >= len(xdata):
                        return
                    label_idx = int(round(float(xdata[idx_in_line])))
                elif hasattr(artist, "get_offsets"):
                    offs = artist.get_offsets()
                    idx_in_coll = int(inds[0])
                    if idx_in_coll < 0 or idx_in_coll >= len(offs):
                        return
                    label_idx = int(round(float(offs[idx_in_coll][0])))
                else:
                    return
                if label_idx < 0 or label_idx >= len(self._labels):
                    return
                try:
                    self._set_selection_index(label_idx)
                except Exception:
                    pass
            except Exception:
                pass
        canvas.mpl_connect('pick_event', on_pick)

        self._dragging = False
        def on_press(event):
            try:
                if getattr(event, "inaxes", None) is not self._ax:
                    return
                x = getattr(event, "xdata", None)
                if x is None:
                    return
                self._dragging = True
                idx = int(round(float(x)))
                self._set_selection_index(idx)
            except Exception:
                pass
        def on_move(event):
            try:
                if not self._dragging:
                    return
                if getattr(event, "inaxes", None) is not self._ax:
                    return
                x = getattr(event, "xdata", None)
                if x is None:
                    return
                idx = int(round(float(x)))
                self._set_selection_index(idx)
            except Exception:
                pass
        def on_release(event):
            try:
                self._dragging = False
            except Exception:
                pass
        canvas.mpl_connect('button_press_event', on_press)
        canvas.mpl_connect('motion_notify_event', on_move)
        canvas.mpl_connect('button_release_event', on_release)

    def _handle_dataset_selection(self, dataset_name: str):
        if dataset_name not in getattr(self, "_dataset_buttons", {}):
            return
        self._table_name = dataset_name
        self._sync_dataset_button_states()
        self._redraw()

    def _sync_dataset_button_states(self):
        for name, btn in getattr(self, "_dataset_buttons", {}).items():
            prev_state = btn.blockSignals(True)
            btn.setChecked(name == self._table_name)
            btn.blockSignals(prev_state)


    def _split_last_num(self, s: str):
        try:
            parts = str(s).splitlines()
            for p in reversed(parts):
                p = p.strip()
                if p:
                    return p
            return ""
        except Exception:
            return ""

    def _split_first_num(self, s: str):
        try:
            parts = str(s).splitlines()
            for p in parts:
                p = p.strip()
                if p:
                    return p
            return ""
        except Exception:
            return ""

    def _to_float(self, x):
        try:
            return float(str(x).replace(',', '.'))
        except Exception:
            return None

    def _to_amount(self, x):
        try:
            s = str(x)
            s = s.replace('£', '').replace('₺', '')
            s = s.replace(' ', '')
            s = s.replace(',', '')
            return float(s) if s else None
        except Exception:
            return None

    def _to_percent(self, x):
        try:
            s = str(x)
            s = s.replace('%', '')
            s = s.replace(' ', '')
            s = s.replace(',', '.')
            return float(s) if s else None
        except Exception:
            return None

    def _fmt_pct_change(self, old_val, new_val):
        try:
            if old_val is None or new_val is None:
                return ""
            if float(old_val) == 0.0:
                return ""
            diff = (float(new_val) - float(old_val)) / float(old_val) * 100.0
            if diff > 0:
                return f"+{diff:.1f}%"
            elif diff < 0:
                return f"-{abs(diff):.1f}%"
            else:
                return f"{0:.1f}%"
        except Exception:
            return ""

    def _format_signed_value(self, value: Optional[float], precision: int = 2) -> str:
        if value is None:
            return ""
        try:
            num = float(value)
        except Exception:
            return ""
        fmt = f"{abs(num):.{precision}f}"
        if num > 0:
            return f"+{fmt}"
        if num < 0:
            return f"-{fmt}"
        return f"{0:.{precision}f}"

    def _parse_scraped_datetime(self, scraped_at_value):
        if not scraped_at_value:
            return None
        try:
            return datetime.fromisoformat(str(scraped_at_value))
        except Exception:
            return None

    def _format_hist_label(self, row: Optional[dict]) -> str:
        if not row:
            return ""
        dt = self._parse_scraped_datetime(row.get('ScrapedAt'))
        if dt:
            return dt.strftime('%d/%m/%Y %H:%M')
        date_text = str(row.get('Date', '')).strip()
        return date_text

    def _make_day_key(self, row: dict):
        dt = self._parse_scraped_datetime(row.get('ScrapedAt'))
        if dt:
            return dt.strftime('%Y-%m-%d')
        txt = str(row.get('Date', '')).strip()
        if txt:
            return txt.split()[0]
        return str(id(row))

    def _collapse_hist_rows(self, rows: List[dict]) -> List[dict]:
        try:
            return list(rows or [])
        except Exception:
            return []

    def _make_table_item(self, value, colorize=False, bold=False):
        text = "" if value is None else str(value)
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        if colorize and text:
            # Percent change için renk mantığı: artış=yeşil, azalış=kırmızı, nötr=grİ
            cleaned = str(text).strip()
            num = None
            try:
                num = self._to_float(cleaned.replace('%', '').replace('+', '').replace('−', '-'))
            except Exception:
                num = None
            if num is None and cleaned.endswith('%'):
                try:
                    num = self._to_float(cleaned[:-1].replace('+', '').replace('−', '-'))
                except Exception:
                    num = None
            if num is not None:
                if num > 0:
                    item.setForeground(QColor("#32d764"))
                elif num < 0:
                    item.setForeground(QColor("#ff5b5b"))
                else:
                    item.setForeground(QColor("#9fa3aa"))
        return item

    def _apply_gray_column(self, tbl, col: int, skip_first_row: bool = False):
        try:
            if tbl is None or col is None or col < 0:
                return
            rows = tbl.rowCount()
            start_row = 1 if skip_first_row else 0
            brush = QBrush(QColor(80, 80, 80))
            for r in range(start_row, rows):
                it = tbl.item(r, col)
                if it is None:
                    it = QTableWidgetItem("")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(r, col, it)
                it.setBackground(brush)
        except Exception:
            pass

    def _highlight_percent_row(self, tbl, row_index: int, palette: Optional[Dict[int, str]] = None):
        try:
            if tbl is None or row_index < 0 or row_index >= tbl.rowCount():
                return
            cols = tbl.columnCount()
            parsed: List[Tuple[int, float]] = []
            for c in range(cols):
                item = tbl.item(row_index, c)
                if item is None:
                    continue
                pct = self._to_percent(item.text())
                if pct is not None:
                    parsed.append((c, pct))
            if not parsed:
                return
            max_col = max(parsed, key=lambda pair: pair[1])[0]
            palette = palette or {}
            muted_bg = QBrush(QColor(43, 43, 48))
            muted_fg = QColor("#9fa3aa")
            default_accent = palette.get('default', "#4CAF50")
            for c in range(cols):
                item = tbl.item(row_index, c)
                if item is None:
                    item = QTableWidgetItem("")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row_index, c, item)
                font = item.font()
                if c == max_col:
                    accent_color = QColor(palette.get(c, default_accent))
                    item.setBackground(QBrush(accent_color))
                    # Vurgulanan hücrede siyah yerine beyaz metin kullan
                    item.setForeground(QColor("#ffffff"))
                    font.setBold(True)
                else:
                    item.setBackground(muted_bg)
                    item.setForeground(muted_fg)
                    font.setBold(False)
                item.setFont(font)
        except Exception:
            pass

    def _populate_point_table(self, row_data: Optional[dict], label_text: str):
        tbl = self.point_tbl
        tbl.clear()
        if row_data is None:
            tbl.setRowCount(1)
            tbl.setColumnCount(1)
            tbl.setHorizontalHeaderLabels(["Bilgi"])
            tbl.setVerticalHeaderLabels([""])
            tbl.setItem(0, 0, self._make_table_item("Seçilen tarih için veri yok"))
            tbl.setVisible(True)
            return

        dataset = self._table_name
        date_text = (label_text or str(row_data.get('Date', '')).strip() or str(row_data.get('ScrapedAt', '')).strip())
        date_text = str(date_text).strip()
        col_labels: List[str] = []
        rows: List[Tuple[str, List[str], List[bool]]] = []

        if dataset == 'moneyway_1x2':
            col_labels = [self._home, 'X', self._away]
            # Sadece yüzdeler ve hacim
            rows.append(("Percent %", [row_data.get('Pct1',''), row_data.get('PctX',''), row_data.get('Pct2','')], [False, False, False]))
            volume = row_data.get('Volume','')
            rows.append(("Volume", [volume, volume, volume], [False, False, False]))
        elif dataset == 'dropping_1x2':
            col_labels = [self._home, 'X', self._away]
            rows.append(("Open", [
                self._split_first_num(row_data.get('1','')),
                self._split_first_num(row_data.get('X','')),
                self._split_first_num(row_data.get('2',''))
            ], [False, False, False]))
            rows.append(("Current", [
                self._split_last_num(row_data.get('1','')),
                self._split_last_num(row_data.get('X','')),
                self._split_last_num(row_data.get('2',''))
            ], [False, False, False]))
            # Change %: Open -> Current değişimi
            try:
                o1 = self._to_float(self._split_first_num(row_data.get('1','')))
                ox = self._to_float(self._split_first_num(row_data.get('X','')))
                o2 = self._to_float(self._split_first_num(row_data.get('2','')))
                c1 = self._to_float(self._split_last_num(row_data.get('1','')))
                cx = self._to_float(self._split_last_num(row_data.get('X','')))
                c2 = self._to_float(self._split_last_num(row_data.get('2','')))
                rows.append(("Change %", [
                    self._fmt_pct_change(o1, c1),
                    self._fmt_pct_change(ox, cx),
                    self._fmt_pct_change(o2, c2)
                ], [True, True, True]))
            except Exception:
                pass
            volume = row_data.get('Volume','')
            if volume:
                rows.append(("Volume", [volume, volume, volume], [False, False, False]))
        elif dataset == 'moneyway_ou25':
            # Sadece yüzde dağılımı ve hacim (Under/Over)
            col_labels = ["Under", "Over"]
            rows.append(("Percent %", [row_data.get('PctUnder',''), row_data.get('PctOver','')], [False, False]))
            volume = row_data.get('Volume','')
            if volume:
                rows.append(("Volume", [volume, volume], [False, False]))
        elif dataset == 'dropping_ou25':
            # Open, Current, Change % (Under/Over)
            col_labels = ["Under", "Over"]
            o_u = self._split_first_num(row_data.get('Under',''))
            o_o = self._split_first_num(row_data.get('Over',''))
            c_u = self._split_last_num(row_data.get('Under',''))
            c_o = self._split_last_num(row_data.get('Over',''))
            rows.append(("Open", [o_u, o_o], [False, False]))
            rows.append(("Current", [c_u, c_o], [False, False]))
            ou = self._to_float(o_u)
            oo = self._to_float(o_o)
            cu = self._to_float(c_u)
            co = self._to_float(c_o)
            rows.append(("Change %", [self._fmt_pct_change(ou, cu), self._fmt_pct_change(oo, co)], [True, True]))
        elif dataset == 'moneyway_btts':
            col_labels = ["Yes", "No"]
            rows.append(("Odds", [row_data.get('Yes',''), row_data.get('No','')], [False, False]))
            rows.append(("Percent %", [row_data.get('PctYes',''), row_data.get('PctNo','')], [True, True]))
            rows.append(("Amount ₺", [row_data.get('AmtYes',''), row_data.get('AmtNo','')], [False, False]))
            try:
                tr = self._query_row(self._db_path, 'moneyway_btts', self._home, self._away)
                if tr:
                    chY = self._fmt_pct_change(self._to_amount(row_data.get('AmtYes')), self._to_amount(tr.get('AmtYes')))
                    chN = self._fmt_pct_change(self._to_amount(row_data.get('AmtNo')), self._to_amount(tr.get('AmtNo')))
                    rows.append(("Change %", [chY, chN], [True, True]))
            except Exception:
                pass
            volume = row_data.get('Volume','')
            rows.append(("Volume", [volume, volume], [False, False]))
        elif dataset == 'dropping_btts':
            col_labels = ["Yes", "No"]
            rows.append(("Open", [
                self._split_first_num(row_data.get('Yes','')),
                self._split_first_num(row_data.get('No',''))
            ], [False, False]))
            rows.append(("Current", [
                self._split_last_num(row_data.get('Yes','')),
                self._split_last_num(row_data.get('No',''))
            ], [False, False]))
            try:
                tr = self._query_row(self._db_path, 'dropping_btts', self._home, self._away)
                if tr:
                    y_old = self._to_float(self._split_last_num(row_data.get('Yes','')))
                    n_old = self._to_float(self._split_last_num(row_data.get('No','')))
                    y_new = self._to_float(self._split_last_num(tr.get('Yes','')))
                    n_new = self._to_float(self._split_last_num(tr.get('No','')))
                    rows.append(("Change %", [
                        self._fmt_pct_change(y_old, y_new),
                        self._fmt_pct_change(n_old, n_new)
                    ], [True, True]))
            except Exception:
                pass
            volume = row_data.get('Volume','')
            rows.append(("Volume", [volume, volume], [False, False]))
        else:
            col_labels = self._series_keys or []
            idx = self._labels.index(label_text) if label_text in self._labels else -1
            current_values = []
            for key in self._series_keys:
                arr = self._values_by_series.get(key, [])
                current_values.append("" if idx < 0 or idx >= len(arr) else arr[idx])
            rows.append(("Values", current_values, [False] * len(current_values)))

        if not col_labels:
            col_labels = ["Değer"]

        col_count = len(col_labels)
        row_headers = []
        date_header_label = "Tarih"
        date_row_value = date_text
        if dataset == 'dropping_ou25' and date_text:
            date_header_label = ""
            date_row_value = f"Tarih ve Saat: {date_text}"
        if date_text:
            row_headers.append(date_header_label)
        row_headers.extend([header for header, _, _ in rows])

        tbl.setColumnCount(col_count)
        tbl.setHorizontalHeaderLabels(col_labels)
        tbl.setRowCount(len(row_headers))
        tbl.setVerticalHeaderLabels(row_headers)

        percent_rows: List[int] = []
        row_idx = 0
        if date_text:
            tbl.setSpan(0, 0, 1, col_count)
            tbl.setItem(0, 0, self._make_table_item(date_row_value or date_text, bold=True))
            for c in range(1, col_count):
                tbl.setItem(0, c, self._make_table_item(""))
            row_idx = 1

        for header, values, color_mask in rows:
            current_row = row_idx
            padded = list(values) + [""] * (col_count - len(values))
            mask = (color_mask or []) + [False] * (col_count - len(color_mask or []))
            for c in range(col_count):
                tbl.setItem(row_idx, c, self._make_table_item(padded[c], colorize=mask[c]))
            if dataset == 'moneyway_1x2' and header and header.strip().lower() == "percent %":
                percent_rows.append(current_row)
            row_idx += 1

        try:
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        tbl.setVisible(True)

        if dataset == 'moneyway_1x2' and percent_rows:
            palette = {0: "#4CAF50", 1: "#FFB300", 2: "#E53935", 'default': "#4CAF50"}
            for r in percent_rows:
                self._highlight_percent_row(tbl, r, palette=palette)

        # En yüksek oran sütununu griye boya
        try:
            highlight_col = None
            if dataset == 'moneyway_1x2':
                vals = [self._to_float(row_data.get('Odds1')), self._to_float(row_data.get('OddsX')), self._to_float(row_data.get('Odds2'))]
                idxs = [i for i, v in enumerate(vals) if v is not None]
                if idxs:
                    mx = max(idxs, key=lambda i: vals[i])
                    highlight_col = mx
            elif dataset == 'dropping_1x2':
                v1 = self._to_float(self._split_last_num(row_data.get('1','')))
                vx = self._to_float(self._split_last_num(row_data.get('X','')))
                v2 = self._to_float(self._split_last_num(row_data.get('2','')))
                vals = [v1, vx, v2]
                idxs = [i for i, v in enumerate(vals) if v is not None]
                if idxs:
                    mx = max(idxs, key=lambda i: vals[i])
                    highlight_col = mx
            elif dataset == 'moneyway_ou25':
                over_v = self._to_float(row_data.get('Over'))
                under_v = self._to_float(row_data.get('Under'))
                if over_v is not None and under_v is not None:
                    highlight_col = 0 if over_v >= under_v else 2
            elif dataset == 'dropping_ou25':
                over_v = self._to_float(self._split_last_num(row_data.get('Over','')))
                under_v = self._to_float(self._split_last_num(row_data.get('Under','')))
                if over_v is not None and under_v is not None:
                    highlight_col = 0 if over_v >= under_v else 1
            elif dataset == 'moneyway_btts':
                y = self._to_float(row_data.get('Yes'))
                n = self._to_float(row_data.get('No'))
                if y is not None and n is not None:
                    highlight_col = 0 if y >= n else 1
            elif dataset == 'dropping_btts':
                y = self._to_float(self._split_last_num(row_data.get('Yes','')))
                n = self._to_float(self._split_last_num(row_data.get('No','')))
                if y is not None and n is not None:
                    highlight_col = 0 if y >= n else 1
            if highlight_col is not None:
                self._apply_gray_column(tbl, highlight_col, skip_first_row=bool(date_text))
        except Exception:
            pass

    def _redraw(self):
        try:
            self.point_tbl.clear()
            self.point_tbl.setRowCount(0)
            self.point_tbl.setColumnCount(0)
        except Exception:
            pass
        self.point_tbl.setVisible(False)
        try:
            for a in getattr(self, "_highlight_artists", []) or []:
                try:
                    a.remove()
                except Exception:
                    pass
            self._highlight_artists = []
            if getattr(self, "_vline", None) is not None:
                try:
                    self._vline.remove()
                except Exception:
                    pass
                self._vline = None
        except Exception:
            pass
        mw = self._query_row(self._db_path, 'moneyway_1x2', self._home, self._away)
        hist_table = f"{self._table_name}_hist"
        hist_rows = self._query_history(self._db_path, hist_table, self._home, self._away)
        hist_rows = self._collapse_hist_rows(hist_rows)
        labels = []
        series = {}
        point_rows = []
        if self._table_name == 'moneyway_1x2':
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    p1 = self._to_percent(rr.get('Pct1'))
                    px = self._to_percent(rr.get('PctX'))
                    p2 = self._to_percent(rr.get('Pct2'))
                    series.setdefault('1', []).append(p1 if isinstance(p1, float) else None)
                    series.setdefault('X', []).append(px if isinstance(px, float) else None)
                    series.setdefault('2', []).append(p2 if isinstance(p2, float) else None)
            elif mw:
                lbl = self._format_hist_label(mw)
                labels = [lbl] if lbl else []
                if labels:
                    point_rows.append(mw)
                series['1'] = [ self._to_percent(mw.get('Pct1')) ] if labels else []
                series['X'] = [ self._to_percent(mw.get('PctX')) ] if labels else []
                series['2'] = [ self._to_percent(mw.get('Pct2')) ] if labels else []
        elif self._table_name == 'dropping_1x2':
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    series.setdefault('1', []).append(self._to_float(self._split_last_num(rr.get('1',''))))
                    series.setdefault('X', []).append(self._to_float(self._split_last_num(rr.get('X',''))))
                    series.setdefault('2', []).append(self._to_float(self._split_last_num(rr.get('2',''))))
            else:
                row = self._query_row(self._db_path, 'dropping_1x2', self._home, self._away)
                if row:
                    lbl = self._format_hist_label(row)
                    labels = [lbl] if lbl else []
                    if labels:
                        point_rows.append(row)
                    series['1'] = [ self._to_float(self._split_last_num(row.get('1',''))) ] if labels else []
                    series['X'] = [ self._to_float(self._split_last_num(row.get('X',''))) ] if labels else []
                    series['2'] = [ self._to_float(self._split_last_num(row.get('2',''))) ] if labels else []
        elif self._table_name == 'moneyway_ou25':
            # Moneyway OU25 grafiği yüzdelik dağılımları göstermeli
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    series.setdefault('Under', []).append(self._to_percent(rr.get('PctUnder')))
                    series.setdefault('Over', []).append(self._to_percent(rr.get('PctOver')))
            else:
                row = self._query_row(self._db_path, 'moneyway_ou25', self._home, self._away)
                if row:
                    lbl = self._format_hist_label(row)
                    labels = [lbl] if lbl else []
                    if labels:
                        point_rows.append(row)
                    series['Under'] = [ self._to_percent(row.get('PctUnder')) ] if labels else []
                    series['Over'] = [ self._to_percent(row.get('PctOver')) ] if labels else []
        elif self._table_name == 'dropping_ou25':
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    series.setdefault('Under', []).append(self._to_float(self._split_last_num(rr.get('Under',''))))
                    series.setdefault('Over', []).append(self._to_float(self._split_last_num(rr.get('Over',''))))
            else:
                row = self._query_row(self._db_path, 'dropping_ou25', self._home, self._away)
                if row:
                    lbl = self._format_hist_label(row)
                    labels = [lbl] if lbl else []
                    if labels:
                        point_rows.append(row)
                    series['Under'] = [ self._to_float(self._split_last_num(row.get('Under',''))) ] if labels else []
                    series['Over'] = [ self._to_float(self._split_last_num(row.get('Over',''))) ] if labels else []
        elif self._table_name == 'moneyway_btts':
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    series.setdefault('Yes', []).append(self._to_amount(rr.get('AmtYes')))
                    series.setdefault('No', []).append(self._to_amount(rr.get('AmtNo')))
            else:
                row = self._query_row(self._db_path, 'moneyway_btts', self._home, self._away)
                if row:
                    lbl = self._format_hist_label(row)
                    labels = [lbl] if lbl else []
                    if labels:
                        point_rows.append(row)
                    series['Yes'] = [ self._to_amount(row.get('AmtYes')) ] if labels else []
                    series['No'] = [ self._to_amount(row.get('AmtNo')) ] if labels else []
        elif self._table_name == 'dropping_btts':
            if hist_rows:
                for rr in hist_rows:
                    labels.append(self._format_hist_label(rr))
                    point_rows.append(rr)
                    series.setdefault('Yes', []).append(self._to_float(self._split_last_num(rr.get('Yes',''))))
                    series.setdefault('No', []).append(self._to_float(self._split_last_num(rr.get('No',''))))
            else:
                row = self._query_row(self._db_path, 'dropping_btts', self._home, self._away)
                if row:
                    lbl = self._format_hist_label(row)
                    labels = [lbl] if lbl else []
                    if labels:
                        point_rows.append(row)
                    series['Yes'] = [ self._to_float(self._split_last_num(row.get('Yes',''))) ] if labels else []
                    series['No'] = [ self._to_float(self._split_last_num(row.get('No',''))) ] if labels else []

        ax = self._ax
        canvas = self._canvas
        ax.clear()
        ax.set_facecolor("#1e1e1e")
        ax.spines['bottom'].set_color('#aaaaaa')
        ax.spines['top'].set_color('#aaaaaa')
        ax.spines['right'].set_color('#aaaaaa')
        ax.spines['left'].set_color('#aaaaaa')
        ax.tick_params(colors='#cccccc')
        # Y eksen başlığı: Moneyway 1x2 ve OU25 için yüzde, diğerleri için odds
        ylab = "Percent %" if self._table_name in ('moneyway_1x2', 'moneyway_ou25') else ("Money" if self._table_name.startswith('moneyway') else "Odds")
        ax.set_ylabel(ylab, color="#cccccc")
        ax.set_xlabel("Date", color="#cccccc")
        xs = list(range(len(labels)))
        color_map = {'1': '#2aa1ff', 'X': '#ffd000', '2': '#ff4a4a', 'Under': '#2aa1ff', 'Over': '#ff4a4a', 'Yes': '#2aa1ff', 'No': '#ff4a4a'}
        y_lower, y_upper = _compute_axis_bounds(series)
        ax.set_ylim(y_lower, y_upper)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        plotted_any = False
        for key, values in series.items():
            cleaned_points = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
            if not cleaned_points:
                continue
            plot_x = [i for i, _ in cleaned_points]
            plot_y = [float(v) for _, v in cleaned_points]
            if self._table_name in ('moneyway_ou25','dropping_ou25'):
                label_text = '2.5 Alt' if key == 'Under' else '2.5 Üst'
            elif self._table_name in ('moneyway_btts','dropping_btts'):
                label_text = 'Yes' if key == 'Yes' else 'No'
            else:
                label_text = self._home if key == '1' else ('X' if key == 'X' else self._away)
            line, = ax.plot(
                plot_x,
                plot_y,
                color=color_map.get(key, '#ffffff'),
                linewidth=2,
                label=label_text,
            )
            plotted_any = True
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=45, ha='right', color="#cccccc")
        if plotted_any:
            legend = ax.legend(facecolor="#ffffff", edgecolor="#cccccc")
            if legend:
                for text in legend.get_texts():
                    text.set_color("#1e1e1e")
        canvas.draw()
        self._labels = labels
        self._series_keys = list(series.keys())
        self._values_by_series = series
        self._point_rows = point_rows

        try:
            for t in [
                self._stats_tbl,
                self._stats_tbl_drop_1x2,
                self._stats_tbl_mw_ou25,
                self._stats_tbl_drop_ou25,
                self._stats_tbl_mw_btts,
                self._stats_tbl_drop_btts,
            ]:
                t.setVisible(False)
        except Exception:
            pass

        if self._table_name == 'moneyway_1x2' and mw:
            def _set(r, row, col_name):
                val = r.get(col_name, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._stats_tbl.setItem(row, 0 if col_name.endswith('1') else 1 if col_name.endswith('X') else 2, item)
            self._stats_tbl.setVisible(True)
            # Sadece yüzde ve hacim
            _set(mw, 0, 'Pct1')
            _set(mw, 0, 'PctX')
            _set(mw, 0, 'Pct2')
            vol_item = QTableWidgetItem(str(mw.get('Volume', '')))
            vol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stats_tbl.setItem(1, 1, vol_item)
            try:
                self._highlight_percent_row(
                    self._stats_tbl,
                    0,
                    palette={0: "#4CAF50", 1: "#FFB300", 2: "#E53935", 'default': "#4CAF50"},
                )
            except Exception:
                pass

        if self._table_name == 'dropping_1x2':
            r = self._query_row(self._db_path, 'dropping_1x2', self._home, self._away)
            tbl = self._stats_tbl_drop_1x2
            tbl.setVisible(True)
            try:
                def _set(row, col, val):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
                if r:
                    o1 = self._split_first_num(r.get('1',''))
                    ox = self._split_first_num(r.get('X',''))
                    o2 = self._split_first_num(r.get('2',''))
                    c1 = self._split_last_num(r.get('1',''))
                    cx = self._split_last_num(r.get('X',''))
                    c2 = self._split_last_num(r.get('2',''))
                    _set(0,0,o1); _set(0,1,ox); _set(0,2,o2)
                    _set(1,0,c1); _set(1,1,cx); _set(1,2,c2)
                    # Change % satırı
                    def pct_change(open_str, cur_str):
                        try:
                            o = self._to_float(open_str)
                            c = self._to_float(cur_str)
                            if o is None or c is None:
                                return ""
                            if o == 0:
                                return "0%" if c == 0 else ""
                            ch = ((c - o) / o) * 100.0
                            sign = "+" if ch > 0 else ("" if ch == 0 else "-")
                            return f"{sign}{abs(ch):.2f}%"
                        except Exception:
                            return ""
                    _set(2,0,pct_change(o1, c1)); _set(2,1,pct_change(ox, cx)); _set(2,2,pct_change(o2, c2))
                    # Change % renk mantığı uygula (yeşil/kırmızı/nötr gri)
                    try:
                        for col in range(3):
                            it = tbl.item(2, col)
                            if it is None:
                                continue
                            s = str(it.text()).replace('%', '').replace('+', '').replace('−', '-')
                            num = self._to_float(s)
                            if num is None:
                                continue
                            if num > 0:
                                it.setForeground(QColor("#32d764"))
                            elif num < 0:
                                it.setForeground(QColor("#ff5b5b"))
                            else:
                                it.setForeground(QColor("#9fa3aa"))
                    except Exception:
                        pass
                    _set(3,1,r.get('Volume',''))
            except Exception:
                pass

        if self._table_name == 'moneyway_ou25':
            r = self._query_row(self._db_path, 'moneyway_ou25', self._home, self._away)
            tbl = self._stats_tbl_mw_ou25
            tbl.setVisible(True)
            try:
                def _set(row, col, val):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
                if r:
                    # Sadece yüzde ve hacim (Under/Over)
                    _set(0,0,r.get('PctUnder',''))
                    _set(0,1,r.get('PctOver',''))
                    vol = r.get('Volume','')
                    _set(1,0,vol)
                    _set(1,1,vol)
            except Exception:
                pass

        if self._table_name == 'dropping_ou25':
            r = self._query_row(self._db_path, 'dropping_ou25', self._home, self._away)
            tbl = self._stats_tbl_drop_ou25
            tbl.setVisible(True)
            try:
                def _set(row, col, val):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
                if r:
                    o_u = self._split_first_num(r.get('Under',''))
                    o_o = self._split_first_num(r.get('Over',''))
                    c_u = self._split_last_num(r.get('Under',''))
                    c_o = self._split_last_num(r.get('Over',''))
                    _set(0,0,o_u)
                    _set(0,1,o_o)
                    _set(1,0,c_u)
                    _set(1,1,c_o)
                    def pct_change(open_str, cur_str):
                        try:
                            o = self._to_float(open_str)
                            c = self._to_float(cur_str)
                            if o is None or c is None:
                                return ""
                            if o == 0:
                                return "0%" if c == 0 else ""
                            ch = ((c - o) / o) * 100.0
                            sign = "+" if ch > 0 else ("" if ch == 0 else "-")
                            return f"{sign}{abs(ch):.2f}%"
                        except Exception:
                            return ""
                    _set(2,0,pct_change(o_u, c_u))
                    _set(2,1,pct_change(o_o, c_o))
                    # Change % renk mantığı uygula (yeşil/kırmızı/nötr gri)
                    try:
                        for col in range(2):
                            it = tbl.item(2, col)
                            if it is None:
                                continue
                            s = str(it.text()).replace('%', '').replace('+', '').replace('−', '-')
                            num = self._to_float(s)
                            if num is None:
                                continue
                            if num > 0:
                                it.setForeground(QColor("#32d764"))
                            elif num < 0:
                                it.setForeground(QColor("#ff5b5b"))
                            else:
                                it.setForeground(QColor("#9fa3aa"))
                    except Exception:
                        pass
            except Exception:
                pass

        if self._table_name == 'moneyway_btts':
            r = self._query_row(self._db_path, 'moneyway_btts', self._home, self._away)
            tbl = self._stats_tbl_mw_btts
            tbl.setVisible(True)
            try:
                def _set(row, col, val):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
                if r:
                    _set(0,0,r.get('Yes',''))
                    _set(0,1,r.get('No',''))
                    _set(1,0,r.get('PctYes',''))
                    _set(1,1,r.get('PctNo',''))
                    _set(2,0,r.get('AmtYes',''))
                    _set(2,1,r.get('AmtNo',''))
                    _set(3,0,r.get('Volume',''))
                    _set(3,1,r.get('Volume',''))
            except Exception:
                pass

        if self._table_name == 'dropping_btts':
            r = self._query_row(self._db_path, 'dropping_btts', self._home, self._away)
            tbl = self._stats_tbl_drop_btts
            tbl.setVisible(True)
            try:
                def _set(row, col, val):
                    it = QTableWidgetItem(str(val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
                if r:
                    _set(0,0,self._split_first_num(r.get('Yes','')))
                    _set(0,1,self._split_first_num(r.get('No','')))
                    _set(1,0,self._split_last_num(r.get('Yes','')))
                    _set(1,1,self._split_last_num(r.get('No','')))
                    _set(2,0,r.get('Volume',''))
                    _set(2,1,r.get('Volume',''))
            except Exception:
                pass

    def _lookup_hist_row_by_label(self, date_label: str):
        if not date_label:
            return None
        hist_table = f"{self._table_name}_hist"
        try:
            return self._storage.lookup_hist_row_by_label(hist_table, self._home, self._away, date_label)
        except Exception:
            return None

    def _set_selection_index(self, label_idx: int):
        try:
            if label_idx is None:
                return
            if label_idx < 0 or label_idx >= len(self._labels):
                return
            label_text = self._labels[label_idx]
            row_data = self._point_rows[label_idx] if label_idx < len(self._point_rows) else None
            if not row_data and label_text:
                row_data = self._lookup_hist_row_by_label(label_text)
            self._populate_point_table(row_data, label_text)
            try:
                if getattr(self, "_vline", None) is not None:
                    try:
                        self._vline.remove()
                    except Exception:
                        pass
                    self._vline = None
                self._vline = self._ax.axvline(label_idx, color='#00e5ff', linestyle='--', linewidth=1.4, zorder=5)
                self._canvas.draw_idle()
            except Exception:
                pass
        except Exception:
            pass

    def _query_history(self, db_path: str, hist_table: str, home: str, away: str):
        try:
            return self._storage.query_history(hist_table, home, away)
        except Exception:
            return []

    def _query_row(self, db_path: str, table_name: str, home: str, away: str):
        try:
            return self._storage.query_row(table_name, home, away)
        except Exception:
            return None

class ScrapeWorker(QObject):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)
    def __init__(self, output_dir: str, verbose: bool, cookie_string: Optional[str]):
        super().__init__()
        self.output_dir = output_dir
        self.verbose = verbose
        self.cookie_string = cookie_string
    def run(self):
        try:
            scrape_all(self.output_dir, self.verbose, self.cookie_string, lambda m,i,n: self.progress.emit(m,i,n))
            self.finished.emit(0)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(1)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()