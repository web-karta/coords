
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QStyledItemDelegate,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QTabWidget, QWidget
)
from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsPointXY, QgsGeometry, QgsFeature, edit

try:
    from qgis.core import QgsMapLayerProxyModel
    _POINT_FILTER = QgsMapLayerProxyModel.PointLayer
except Exception:
    _POINT_FILTER = None


def _float_or_none(s: str):
    if s is None:
        return None
    t = str(s).strip().replace(",", ".")
    if t == "":
        return None
    try:
        return float(t)
    except Exception:
        return None



class _ReadOnlyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Block editor creation entirely
        return None

class CoordsDialog(QDialog):
    """
    Dialog for moving selected points by typed coordinates and creating new points.
    Works in layer CRS. If CRS is geographic -> columns are φ (latitude), λ (longitude) (fi then lambda).
    If CRS is projected -> columns are E/N.
    """
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setWindowTitle("Coords")
        self.resize(1050, 600)  # wider default window  # wider default window

        root = QVBoxLayout(self)

        # Layer picker
        row = QHBoxLayout()
        self.lang = "en"
        self.btnLang = QPushButton("EN")
        self.btnLang.setFixedWidth(46)
        row.addWidget(self.btnLang)
        self.lblLayer = QLabel("Point layer:")
        row.addWidget(self.lblLayer)

        self.layerCombo = QgsMapLayerComboBox()
        if _POINT_FILTER is not None:
            self.layerCombo.setFilters(_POINT_FILTER)
        row.addWidget(self.layerCombo, 1)
        root.addLayout(row)

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # --- Move tab ---
        self.tabMove = QWidget()
        mv = QVBoxLayout(self.tabMove)

        self.btnLoad = QPushButton("Load selection")
        mv.addWidget(self.btnLoad)

        self.btnSelectAll = QPushButton("Select All")
        mv.addWidget(self.btnSelectAll)


        self.move_table = QTableWidget()
        self._readonly_delegate = _ReadOnlyDelegate(self.move_table)
        self.move_table.setMinimumWidth(800)
        self.move_table.setColumnCount(5)
        mv.addWidget(self.move_table, 1)

        self.btnApply = QPushButton("Apply move")
        mv.addWidget(self.btnApply)

        self.tabs.addTab(self.tabMove, "Move selected points")

        # --- Create tab ---
        self.tabCreate = QWidget()
        cr = QVBoxLayout(self.tabCreate)

        self.new_table = QTableWidget()
        self.new_table.setMinimumWidth(800)
        self.new_table.setColumnCount(3)  # X, Y, Status
        cr.addWidget(self.new_table, 1)

        btns = QHBoxLayout()
        self.btnAddRow = QPushButton("Add row")
        self.btnCreate = QPushButton("Create points and edit attributes")
        btns.addWidget(self.btnAddRow)
        btns.addWidget(self.btnCreate)
        cr.addLayout(btns)

        self.tabs.addTab(self.tabCreate, "Create new points")

        # Signals
        self.layerCombo.layerChanged.connect(self._on_layer_changed)
        self.btnLang.clicked.connect(self._retranslate_crs_label)
        self.btnLang.clicked.connect(self._force_update_label_from_combo)
        self.btnLang.clicked.connect(self._retranslate_crs_label)
        self.btnLang.clicked.connect(self.toggle_language)
        self.btnLang.clicked.connect(self._retranslate_crs_label)
        self.btnLang.clicked.connect(self._force_update_label_from_combo)
        self.btnLang.clicked.connect(self._retranslate_crs_label)
        self.btnLang.clicked.connect(self._refresh_current_layer_label)
        self.btnLoad.clicked.connect(self.load_selection)
        self.btnSelectAll.clicked.connect(self.select_all_features)
        self.btnApply.clicked.connect(self.apply_move)
        self.btnAddRow.clicked.connect(self.add_new_row)
        self.btnCreate.clicked.connect(self.create_points)

        # Initialize headers
        self._on_layer_changed(self.current_layer())
        self._apply_ui_texts()

    def current_layer(self):
        return self.layerCombo.currentLayer()

    def _t(self, en: str, hr: str) -> str:
        return en if self.lang == 'en' else hr

    def toggle_language(self):
        self.lang = 'hr' if self.lang == 'en' else 'en'
        self.btnLang.setText('HR' if self.lang == 'hr' else 'EN')
        # refresh all UI text
        self._apply_ui_texts()

    def _apply_ui_texts(self):
        # labels / buttons / tabs
        self.setWindowTitle(self._t('Coords', 'Coords'))
        self.lblLayer.setText(self._t('Point layer:', 'Točkasti sloj:'))
        self.btnLoad.setText(self._t('Load selection', 'Učitaj odabir'))
        self.btnSelectAll.setText(self._t('Select All', 'Odaberi sve'))
        self.btnApply.setText(self._t('Apply move', 'Primijeni pomak'))
        self.btnAddRow.setText(self._t('Add row', 'Dodaj red'))
        self.btnCreate.setText(self._t('Create points and edit attributes', 'Izradi točke i uredi atribute'))
        self.tabs.setTabText(0, self._t('Move selected points', 'Pomak odabranih točaka'))
        self.tabs.setTabText(1, self._t('Create new points', 'Izrada novih točaka'))
        # headers depend on CRS
        self._update_headers_only()

    def _update_headers_only(self):
        # Update table headers without clearing existing rows
        is_geo = self._is_geo()
        if is_geo:
            self.move_table.setHorizontalHeaderLabels([
                self._t('FID', 'FID'),
                ( 'φ (geodetic latitude)' if self.lang=='en' else 'φ (geodetska širina)' ),
                ( 'λ (geodetic longitude)' if self.lang=='en' else 'λ (geodetska dužina)' ),
                self._t('New φ', 'Novi φ'),
                self._t('New λ', 'Novi λ')
            ])
            self.new_table.setHorizontalHeaderLabels([
                ( 'φ (geodetic latitude)' if self.lang=='en' else 'φ (geodetska širina)' ),
                ( 'λ (geodetic longitude)' if self.lang=='en' else 'λ (geodetska dužina)' ),
                self._t('Status', 'Stanje')
            ])
        else:
            self.move_table.setHorizontalHeaderLabels([
                self._t('FID', 'FID'),
                self._t('E (Y)', 'E (Y)'),
                self._t('N (X)', 'N (X)'),
                self._t('New E (Y)', 'Novi E (Y)'),
                self._t('New N (X)', 'Novi N (X)')
            ])
            self.new_table.setHorizontalHeaderLabels([
                self._t('E (Y)', 'E (Y)'),
                self._t('N (X)', 'N (X)'),
                self._t('Status', 'Stanje')
            ])
        self._apply_column_widths()
        # enforce non-editable old coordinate columns
        self.move_table.setItemDelegateForColumn(1, self._readonly_delegate)
        self.move_table.setItemDelegateForColumn(2, self._readonly_delegate)


    def _apply_column_widths(self):
        # Make coordinate columns wider (both tables)
        try:
            for c in range(self.move_table.columnCount()):
                if c == 0:
                    self.move_table.setColumnWidth(c, 80)
                else:
                    self.move_table.setColumnWidth(c, 200)
            for c in range(self.new_table.columnCount()):
                if c in (0, 1):
                    self.new_table.setColumnWidth(c, 240)
                else:
                    self.new_table.setColumnWidth(c, 200)
        except Exception:
            pass

    # Backwards-compat: older plugin shells may call this
    def refresh_layers(self):
        try:
            self._on_layer_changed(self.current_layer())
            self._apply_ui_texts()
        except Exception:
            pass


    def _is_geo(self):
        lyr = self.current_layer()
        return bool(lyr and lyr.crs() and lyr.crs().isGeographic())

    def _on_layer_changed(self, lyr):
        self._current_layer = lyr
        self._update_crs_label(lyr)
        # Auto toggle editing when layer chosen
        try:
            if lyr and not lyr.isEditable():
                lyr.startEditing()
        except Exception:
            pass
        is_geo = self._is_geo()
        if is_geo:
            self.move_table.setHorizontalHeaderLabels([
                self._t('FID', 'FID'),
                ( 'φ (geodetic latitude)' if self.lang=='en' else 'φ (geodetska širina)' ),
                ( 'λ (geodetic longitude)' if self.lang=='en' else 'λ (geodetska dužina)' ),
                self._t('New φ', 'Novi φ'),
                self._t('New λ', 'Novi λ')
            ])
            self.new_table.setHorizontalHeaderLabels([
                ( 'φ (geodetic latitude)' if self.lang=='en' else 'φ (geodetska širina)' ),
                ( 'λ (geodetic longitude)' if self.lang=='en' else 'λ (geodetska dužina)' ),
                self._t('Status', 'Stanje')
            ])
        else:
            self.move_table.setHorizontalHeaderLabels([
                self._t('FID', 'FID'),
                self._t('E (Y)', 'E (Y)'),
                self._t('N (X)', 'N (X)'),
                self._t('New E (Y)', 'Novi E (Y)'),
                self._t('New N (X)', 'Novi N (X)')
            ])
            self.new_table.setHorizontalHeaderLabels([
                self._t('E (Y)', 'E (Y)'),
                self._t('N (X)', 'N (X)'),
                self._t('Status', 'Stanje')
            ])

        # reset tables
        self.move_table.setRowCount(0)
        self.new_table.setRowCount(0)
        self._apply_column_widths()
        # enforce non-editable old coordinate columns
        self.move_table.setItemDelegateForColumn(1, self._readonly_delegate)
        self.move_table.setItemDelegateForColumn(2, self._readonly_delegate)


    def load_selection(self):
        lyr = self.current_layer()
        if lyr is None:
            QMessageBox.warning(self, "Coords", "Select a point layer.")
            return
        if lyr.geometryType() != 0:  # point
            QMessageBox.warning(self, "Coords", "Layer is not a point layer.")
            return

        feats = lyr.selectedFeatures()
        if not feats:
            QMessageBox.information(self, "Coords", "No selected features.")
            return

        is_geo = self._is_geo()
        self.move_table.setRowCount(len(feats))
        self.move_table.resizeColumnsToContents()
        self._apply_column_widths()
        # enforce non-editable old coordinate columns
        self.move_table.setItemDelegateForColumn(1, self._readonly_delegate)
        self.move_table.setItemDelegateForColumn(2, self._readonly_delegate)

        for r, f in enumerate(feats):
            pt = f.geometry().asPoint()
            self.move_table.setItem(r, 0, QTableWidgetItem(str(f.id())))

            if is_geo:
                # show φ then λ
                self.move_table.setItem(r, 1, QTableWidgetItem(str(pt.y())))
                self.move_table.setItem(r, 2, QTableWidgetItem(str(pt.x())))
            else:
                self.move_table.setItem(r, 1, QTableWidgetItem(str(pt.x())))
                self.move_table.setItem(r, 2, QTableWidgetItem(str(pt.y())))

            self.move_table.setItem(r, 3, QTableWidgetItem(""))
            self.move_table.setItem(r, 4, QTableWidgetItem(""))

    def apply_move(self):
        lyr = self.current_layer()
        if lyr is None:
            QMessageBox.warning(self, "Coords", self._t("Select a point layer.", "Odaberi točkasti sloj."))
            return

        # Ensure layer is editable
        if not lyr.isEditable():
            try:
                ok = lyr.startEditing()
            except Exception:
                ok = False
            if not ok:
                msg_en = (
                    "Layer cannot be put into edit mode.\n"
                    "Possible reasons: read-only source, no write permissions, or provider limitations.\n\n"
                    "Tip: Save layer to a writable format (e.g., GeoPackage) and try again."
                )
                msg_hr = (
                    "Sloj se ne može staviti u način uređivanja.\n"
                    "Mogući razlozi: izvor je samo za čitanje, nema prava pisanja ili ograničenja providera.\n\n"
                    "Savjet: spremi sloj u format s pravom pisanja (npr. GeoPackage) i pokušaj ponovno."
                )
                QMessageBox.warning(self, "Coords", msg_en if self.lang == "en" else msg_hr)
                return

        is_geo = self._is_geo()

        moved = 0
        skipped = 0
        errors = 0

        for r in range(self.move_table.rowCount()):
            fid_item = self.move_table.item(r, 0)
            a_item = self.move_table.item(r, 3)  # New φ or New E (Y)
            b_item = self.move_table.item(r, 4)  # New λ or New N (X)

            if not fid_item:
                continue

            a = _float_or_none(a_item.text() if a_item else "")
            b = _float_or_none(b_item.text() if b_item else "")

            # If both empty -> skip
            if a is None and b is None:
                skipped += 1
                continue

            try:
                fid = int(fid_item.text())
                f = lyr.getFeature(fid)
                if not f.isValid():
                    errors += 1
                    continue

                pt = f.geometry().asPoint()
                old_x, old_y = pt.x(), pt.y()

                if is_geo:
                    # a=lat (φ), b=lon (λ)
                    new_lat = a if a is not None else old_y
                    new_lon = b if b is not None else old_x
                    x, y = new_lon, new_lat
                else:
                    # a=E (Y), b=N (X)
                    x = a if a is not None else old_x
                    y = b if b is not None else old_y

                ok = lyr.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                if ok:
                    moved += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

        lyr.triggerRepaint()

        msg_en = f"Done.\nMoved: {moved}\nSkipped (unchanged/missing): {skipped}\nErrors: {errors}\n\nRemember: Save Edits (or Rollback) in QGIS."
        msg_hr = f"Gotovo.\nPomaknuto: {moved}\nPreskočeno (nepromijenjeno/nedostaje): {skipped}\nGrešaka: {errors}\n\nNe zaboravi: Spremi izmjene (ili Poništi)."
        QMessageBox.information(self, "Coords", msg_en if self.lang == "en" else msg_hr)

    def add_new_row(self):
        r = self.new_table.rowCount()
        self.new_table.insertRow(r)
        self.new_table.setItem(r, 0, QTableWidgetItem(""))
        self.new_table.setItem(r, 1, QTableWidgetItem(""))
        st = QTableWidgetItem("—")
        st.setFlags(st.flags() & ~Qt.ItemIsEditable)
        self.new_table.setItem(r, 2, st)

    
    def select_all_features(self):
        lyr = self.current_layer()
        if not lyr:
            return
        try:
            lyr.selectAll()
        except Exception:
            pass
        self.load_selection()

    def create_points(self):
        lyr = self.current_layer()
        if lyr is None:
            QMessageBox.warning(self, "Coords", "Select a point layer.")
            return

        # Ensure layer is editable (avoid edit() assertion)
        if not lyr.isEditable():
            try:
                ok = lyr.startEditing()
            except Exception:
                ok = False
            if not ok:
                QMessageBox.warning(
                    self, "Coords",
                    """Layer cannot be put into edit mode.
Possible reasons: read-only source, no write permissions, or provider limitations.

Tip: Save layer to a writable format (e.g., GeoPackage) and try again."""
                )
                return

        is_geo = self._is_geo()
        created = 0
        skipped = 0
        errors = 0

        for r in range(self.new_table.rowCount()):
            a = _float_or_none(self.new_table.item(r, 0).text() if self.new_table.item(r, 0) else "")
            b = _float_or_none(self.new_table.item(r, 1).text() if self.new_table.item(r, 1) else "")
            if a is None or b is None:
                if self.new_table.item(r, 2):
                    self.new_table.item(r, 2).setText(
   		                self._t("Skipped (missing)", "Preskočeno (nedostaje)")
                    )
                skipped += 1
                continue

            try:
                if is_geo:
                    x, y = b, a  # lon, lat
                else:
                    x, y = a, b  # E, N

                nf = QgsFeature(lyr.fields())
                nf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                ok, out_feats = lyr.dataProvider().addFeatures([nf])
                if ok and out_feats:
                    created += 1
                    added = out_feats[0]
                    if self.new_table.item(r, 2):
                        self.new_table.item(r, 2).setText(
                            self._t("Created ✓", "Stvoreno ✓")
                        )                    
                    try:
                        lyr.selectByIds([added.id()])
                        self.iface.openFeatureForm(lyr, added, True)
                    except Exception:
                        pass
                else:
                    errors += 1
                    if self.new_table.item(r, 2):
                        self.new_table.item(r, 2).setText("Error")
            except Exception:
                errors += 1
                if self.new_table.item(r, 2):
                    self.new_table.item(r, 2).setText("Error")

        lyr.triggerRepaint()
        msg = self._t(
            f"Created: {created}, Skipped: {skipped}, Errors: {errors}.",
            f"Izrađeno: {created}, Preskočeno: {skipped}, Grešaka: {errors}."
        )        
        QMessageBox.information(self, "Coords", msg)

    def _redo_last(self):
        try:
            if hasattr(self.iface, "actionRedo"):
                self.iface.actionRedo().trigger()
        except Exception:
            pass

    def _update_crs_label(self, lyr):
        try:
            if not lyr:
                return
            crs = lyr.crs()
            if not crs or not crs.isValid():
                return
            auth = crs.authid()
            desc = crs.description()
            if getattr(self, "btnLang", None) and self.btnLang.text() == "EN":
                sys = "Geodetic system" if crs.isGeographic() else "Projected system"
                prefix = "Point layer"
            else:
                sys = "Geodetski sustav" if crs.isGeographic() else "Ravninski sustav"
                prefix = "Sloj točaka"
            if hasattr(self, "lblLayer"):
                self.lblLayer.setText(f"{prefix}: {lyr.name()} ({desc}, {auth}, {sys})")
        except Exception:
            pass



    def _refresh_current_layer_label(self):
        try:
            lyr = None
            if hasattr(self, "cmbPointLayer"):
                lyr = self.cmbPointLayer.currentLayer() if hasattr(self.cmbPointLayer, "currentLayer") else None
            if lyr:
                self._current_layer = lyr
                self._update_crs_label(lyr)
        except Exception:
            pass



    def _force_update_label_from_combo(self):
        try:
            lyr = None
            if hasattr(self, "cmbPointLayer"):
                if hasattr(self.cmbPointLayer, "currentLayer"):
                    lyr = self.cmbPointLayer.currentLayer()
                elif hasattr(self.cmbPointLayer, "currentIndex"):
                    idx = self.cmbPointLayer.currentIndex()
                    lyr = self.cmbPointLayer.itemData(idx)
            if lyr:
                self._current_layer = lyr
                self._update_crs_label(lyr)
        except Exception:
            pass



    def _retranslate_crs_label(self):
        try:
            if hasattr(self, "_current_layer") and self._current_layer:
                self._update_crs_label(self._current_layer)
        except Exception:
            pass
