def classFactory(iface):
    from .coords import CoordsPlugin
    return CoordsPlugin(iface)
