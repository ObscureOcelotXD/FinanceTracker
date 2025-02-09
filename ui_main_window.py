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
        FinanceTrackerHomeWindow.resize(800, 600)
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
        if (self.sourceTable.columnCount() < 3):
            self.sourceTable.setColumnCount(3)
        self.sourceTable.setObjectName(u"sourceTable")
        self.sourceTable.setGeometry(QRect(180, 280, 321, 192))
        self.sourceTable.setRowCount(0)
        self.sourceTable.setColumnCount(3)
        self.sourceTable.horizontalHeader().setVisible(True)
        self.valueAmountEdit = QTextEdit(self.centralwidget)
        self.valueAmountEdit.setObjectName(u"valueAmountEdit")
        self.valueAmountEdit.setGeometry(QRect(380, 170, 171, 41))
        FinanceTrackerHomeWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(FinanceTrackerHomeWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 33))
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
    # retranslateUi

