# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.8.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QHeaderView, QLabel, QMainWindow,
    QMenuBar, QPushButton, QSizePolicy, QStatusBar,
    QTableWidget, QTableWidgetItem, QTextEdit, QWidget)

class Ui_FinanceTrackerHomeWindow(object):
    def setupUi(self, FinanceTrackerHomeWindow):
        if not FinanceTrackerHomeWindow.objectName():
            FinanceTrackerHomeWindow.setObjectName(u"FinanceTrackerHomeWindow")
        FinanceTrackerHomeWindow.resize(1274, 900)
        self.centralwidget = QWidget(FinanceTrackerHomeWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.accountNameEdit = QTextEdit(self.centralwidget)
        self.accountNameEdit.setObjectName(u"accountNameEdit")
        self.accountNameEdit.setGeometry(QRect(250, 70, 171, 41))
        self.NameLabel = QLabel(self.centralwidget)
        self.NameLabel.setObjectName(u"NameLabel")
        self.NameLabel.setGeometry(QRect(280, 30, 131, 41))
        self.addSource = QPushButton(self.centralwidget)
        self.addSource.setObjectName(u"addSource")
        self.addSource.setGeometry(QRect(270, 220, 131, 41))
        self.textEdit = QTextEdit(self.centralwidget)
        self.textEdit.setObjectName(u"textEdit")
        self.textEdit.setGeometry(QRect(130, 170, 171, 41))
        self.sourceLabel = QLabel(self.centralwidget)
        self.sourceLabel.setObjectName(u"sourceLabel")
        self.sourceLabel.setGeometry(QRect(270, 130, 131, 31))
        self.sourceTable = QTableWidget(self.centralwidget)
        if (self.sourceTable.columnCount() < 4):
            self.sourceTable.setColumnCount(4)
        self.sourceTable.setObjectName(u"sourceTable")
        self.sourceTable.setGeometry(QRect(60, 280, 471, 431))
        self.sourceTable.setRowCount(0)
        self.sourceTable.setColumnCount(4)
        self.sourceTable.horizontalHeader().setVisible(True)
        self.valueAmountEdit = QTextEdit(self.centralwidget)
        self.valueAmountEdit.setObjectName(u"valueAmountEdit")
        self.valueAmountEdit.setGeometry(QRect(380, 170, 171, 41))
        self.deleteRowButton = QPushButton(self.centralwidget)
        self.deleteRowButton.setObjectName(u"deleteRowButton")
        self.deleteRowButton.setGeometry(QRect(550, 330, 121, 51))
        self.resetButton = QPushButton(self.centralwidget)
        self.resetButton.setObjectName(u"resetButton")
        self.resetButton.setGeometry(QRect(520, 230, 101, 41))
        FinanceTrackerHomeWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(FinanceTrackerHomeWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1274, 33))
        FinanceTrackerHomeWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(FinanceTrackerHomeWindow)
        self.statusbar.setObjectName(u"statusbar")
        FinanceTrackerHomeWindow.setStatusBar(self.statusbar)

        self.retranslateUi(FinanceTrackerHomeWindow)

        QMetaObject.connectSlotsByName(FinanceTrackerHomeWindow)
    # setupUi

    def retranslateUi(self, FinanceTrackerHomeWindow):
        FinanceTrackerHomeWindow.setWindowTitle(QCoreApplication.translate("FinanceTrackerHomeWindow", u"MainWindow", None))
        self.NameLabel.setText(QCoreApplication.translate("FinanceTrackerHomeWindow", u"Enter Account Name", None))
        self.addSource.setText(QCoreApplication.translate("FinanceTrackerHomeWindow", u"Add Source", None))
        self.sourceLabel.setText(QCoreApplication.translate("FinanceTrackerHomeWindow", u"Enter Sources", None))
        self.deleteRowButton.setText(QCoreApplication.translate("FinanceTrackerHomeWindow", u"Delete Selected Row", None))
        self.resetButton.setText(QCoreApplication.translate("FinanceTrackerHomeWindow", u"Reset", None))
    # retranslateUi

