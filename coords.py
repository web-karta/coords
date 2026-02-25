from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
import os
from .coords_dialog import CoordsDialog

class CoordsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = self.tr("&Coords")

    def tr(self, msg):
        return QCoreApplication.translate("coords", msg)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.action = QAction(QIcon(icon_path), self.tr("Coords"), self.iface.mainWindow())
        self.action.setToolTip(self.tr("Coords"))
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(self.menu, self.action)
            self.iface.removeToolBarIcon(self.action)
        self.action = None
        self.dlg = None

    def open_dialog(self):
        if self.dlg is None:
            self.dlg = CoordsDialog(self.iface)
        # Dialog updates itself on layer change; keep this call safe across versions
        try:
            self.dlg._on_layer_changed(self.dlg.current_layer())
        except Exception:
            pass
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
