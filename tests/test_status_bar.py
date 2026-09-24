

def test_setting_the_same_colour_again_after_a_theme_switch_still_paints_it(qtbot) -> None:
    # Two themes share #007acc: switching dark -> light set the same sheet again, a no-op that left the bar unpainted.
    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtWidgets import QApplication, QWidget

    from in_reach_ide.status_bar import StatusBar

    host = QWidget()
    qtbot.addWidget(host)
    bar = StatusBar(host, host, edge_resize=False)
    bar.resize(200, 22)
    bar.set_color("#007acc")
    old = QApplication.palette()
    try:
        light = QPalette(old)
        light.setColor(QPalette.ColorRole.Window, QColor("#f0f0f0"))
        QApplication.setPalette(light)
        bar.set_color("#007acc")
        image = bar.grab().toImage()
        assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#007acc"
    finally:
        QApplication.setPalette(old)
