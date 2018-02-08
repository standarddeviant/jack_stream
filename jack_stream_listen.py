#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Attempt at writing jack_stream client/audio-player

author: Dave Crist
last edited: February 2018
"""

import os, sys, json, time, logging
from os.path import join, expanduser

try: # python 3 std imports
    import configparser
except:
    try: # python 2 std imports
        import ConfigParser as configparser
    except:
        raise ImportError("unable to import standard package configparser or ConfigParser")

try:
    from PyQt5 import QtCore, QtGui, QtNetwork
    from PyQt5.QtWidgets import *
    #    QMainWindow, QDialog, QLineEdit, QFormLayout, QApplication
    from PyQt5.QtCore import pyqtSlot as PyQtSlot, pyqtSignal as PyQtSignal
    # from PyQt5.QtCore import QObject, pyqtSlot
    # from PyQt5.QtCore import pyqtSignal as QtSignal
except:
    try:
        from PyQt4 import QtCore,QtGui,QtNetwork
        from PyQt4.QtGui import *
        #    QMainWindow, QDialog, QLineEdit, QFormLayout, QApplication
        from PyQt4.QtCore import pyqtSlot as PyQtSlot, pyqtSignal as PyQtSignal
    except:
        pass # fixme, try to use PySide and THEN print helpful error message...


from jack_stream_common import msgify_pkt, JACK_STREAM_VERSION


class JackStreamListen(QMainWindow):
    checkInQueueSignal = PyQtSignal()
    def __init__(self):
        super(JackStreamListen, self).__init__()
        self.ip = '127.0.0.1'
        self.port = '23'
        self.state = 'disconnected'
        self.channels = 1
        # self.tsfmt = '%y%m%d-%H%M%S:'
        # self.textFgColor = 'rgb(0,0,0)'
        # self.textBgColor = 'rgb(255,255,255)'
        # self.fontstr = 'Helvetica'

        logging.debug('DBG: state = '+self.state)

        # self.insFile = "";self.insDir=""
        # self.insSleepAmount = 0;

        self.qsock = QtNetwork.QTcpSocket(self)
        self.qsock.readyRead.connect(self.onReadyRead)
        
        self.prevpkt = bytearray() # note a QByteArray b/c reusing msgify_pkt
        self.audiodata = bytearray()
        
        #FIXME self.tcpSocket.error.connect(self.displayError)

        # self.font = QtGui.QFont()
        self.loadSettings()
        self.initUI()
        
    def initUI(self):
        # self.destroyed is inherited from QMainWindow
        self.destroyed.connect(self.exitApplication)

        # self.textBox = QTextEdit();self.textBox.setReadOnly(1);
        # self.textBox.setStyleSheet('QTextEdit{color: '+self.textFgColor+'; background: '+self.textBgColor+';}');
        # self.inputLine = QLineEdit(self)
        # self.textBox.setFont(self.font)
        # self.inputLine.setFont(self.font)
        # self.inputLine.setStyleSheet('QLineEdit{background: gray;}');
        # self.inputLine.setReadOnly(1)
        # self.inputLine.returnPressed.connect(self.sendInputToTcp);

        self.statusLabel = QLabel('STATUS: Disconnected')
        self.statusLabel.setStyleSheet('QLabel {color: white; background: red}')


        self.chanButtons = []
        
        # self.setLayout ( grid )

        # self.setCentralWidget(self.textBox)

        self.connectAction = QAction('Connect', self);self.connectAction.setShortcut('Ctrl+X')
        self.connectAction.triggered.connect(self.invokeConnectDialog);
        self.disconnectAction = QAction('Disonnect', self);self.disconnectAction.setShortcut('Ctrl+D')
        self.disconnectAction.triggered.connect(self.disconnect);self.disconnectAction.setEnabled(0)
        # self.insertAction = QAction('Insert File', self);self.insertAction.setShortcut('Ctrl+I')
        # self.insertAction.triggered.connect(self.insertFile);self.insertAction.setEnabled(0)
        self.exitAction = QAction('Exit', self);self.exitAction.setShortcut('Ctrl+Q')
        self.exitAction.triggered.connect(self.exitApplication)
        self.optionsAction = QAction('Options', self);self.optionsAction.setShortcut('Ctrl+O')
        self.optionsAction.triggered.connect(self.invokeOptionsDialog)

        #menubar = self.menuBar()
        #fileMenu = menubar.addMenu('&File')
        #fileMenu.addAction(exitAction)
        mainbar = QToolBar('Main');mainbar.setParent(self)
        self.addToolBar(QtCore.Qt.TopToolBarArea,mainbar)
        mainbar.setMovable(0)
        mainbar.addAction(self.connectAction)
        mainbar.addAction(self.disconnectAction)
        # mainbar.addAction(self.insertAction)
        mainbar.addAction(self.optionsAction)

        #adding to window so the key shortcut works, but it's not displayed in the menu
        self.addAction(self.exitAction)

        inputbar = QToolBar('Input');inputbar.setParent(self)
        self.addToolBar(QtCore.Qt.BottomToolBarArea,inputbar)
        inputbar.setMovable(0)
        inputbar.addWidget(self.statusLabel)

        self.setGeometry(300, 300, 350, 250)
        self.setWindowTitle('jack_stream_listen v'+JACK_STREAM_VERSION)    
        self.show()

    def invokeConnectDialog(self):
        if( self.state == 'disconnected' ):
            connectDialog = ConnectDialog(self)
            connectDialog.show();

    def invokeOptionsDialog(self):
        optionsDialog = OptionsDialog(self)
        optionsDialog.show();

    # def insertFile(self):
    #     if( self.state == 'connected' ):
    #         fileName = QtGui.QFileDialog.getOpenFileName(self,'Open File', self.insDir, "All Files (*.*)")
    #         self.insFile = fileName[0];
    #         self.insDir = os.path.dirname(self.insFile)
    #         runnable = InsertFileRunnable(self)
    #         QtCore.QThreadPool.globalInstance().start(runnable)

    def sockHandleConnect(self,ip,port):
        self.ip=ip ; self.port=port
        self.qsock.connectToHost(ip,int(port))
        self.state = 'connected'
        # self.inputLine.setStyleSheet('QLineEdit{color: '+self.textFgColor+'; background: '+self.textBgColor+';}')
        # self.inputLine.setReadOnly(0)
        # self.inputLine.setFocus()
        self.connectAction.setEnabled(0)
        self.disconnectAction.setEnabled(1)

        self.statusLabel.setText('STATUS: Connected')
        self.statusLabel.setStyleSheet('QLabel {color: white; background: green}')

        # self.insertAction.setEnabled(1)
        #self.spawnSocketThreads()

        logging.debug('state = '+self.state+': '+self.ip+':'+self.port)

    def disconnect(self):
        if( self.state == 'connected' ):
            self.state = 'disconnected'
            self.qsock.disconnectFromHost()
            # self.inputLine.setStyleSheet("QLineEdit{background: gray;}");
            # self.inputLine.setReadOnly(1)
            # self.textBox.setFocus()
            self.connectAction.setEnabled(1)
            self.disconnectAction.setEnabled(0)

            self.statusLabel.setText('STATUS: Disconnected')
            self.statusLabel.setStyleSheet('QLabel {color: white; background: red}')

            # self.insertAction.setEnabled(0)
            logging.debug('state = '+self.state+'\n')

    @PyQtSlot()
    def sendInputToTcp(self):
        if( self.state == 'connected' ):
            outstr = self.inputLine.text()+'\r\n'
            dbg = self.qsock.write(QtCore.QByteArray(outstr))
            self.inputLine.clear()

    def exitApplication(self):
        if( self.state == 'connected' ):
            self.qsock.disconnectFromHost()
            self.state = 'disconnected'
        self.saveSettings()
        self.close()

    def saveSettings(self):
        cfgParser = configparser.RawConfigParser()
        cfgParser.add_section('Generic')
        cfgParser.set('Generic','ip', self.ip)
        cfgParser.set('Generic','port', self.port)
        # cfgParser.set('Generic','tsfmt',self.tsfmt)
        # cfgParser.set('Generic','font',self.fontstr)
        # cfgParser.set('Generic','textfg',self.textFgColor)
        # cfgParser.set('Generic','textbg',self.textBgColor)

        with open(join(expanduser('~'), 'jack_stream_listen.cfg'), 'w') as cfgfile:
            cfgParser.write(cfgfile)

    def loadSettings(self):
        cfgParser = configparser.RawConfigParser()
        cfgParser.read(join(expanduser('~'), 'jack_stream_listen.cfg'))
        if( cfgParser.has_section('Generic') ):
            self.ip = cfgParser.get('Generic','ip')
            self.port = cfgParser.get('Generic','port')
            # self.tsfmt = cfgParser.get('Generic','tsfmt')
            # self.fontstr = cfgParser.get('Generic','font')
            # self.font = QtGui.QFont()
            # self.font.fromString(self.fontstr)
            # self.textFgColor = cfgParser.get('Generic','textfg')
            # self.textBgColor = cfgParser.get('Generic','textbg')

        # if( cfgParser.has_section('InsertFile') ):
        #     self.insFile = cfgParser.get('InsertFile','insFile')
        #     self.insDir = cfgParser.get('InsertFile','insDir')
        #     self.insSleepAmount = cfgParser.get('InsertFile','insSleepAmount')

    @PyQtSlot()
    def onReadyRead(self):
        # tstr = time.strftime(self.tsfmt)
        curpkt = bytearray(self.qsock.readAll())
        logging.debug('DBG: Rcvd: '+curpkt.decode())
        msgtype, msg = msgify_pkt(self.prevpkt, curpkt)

        if msgtype == 'META' and len(msg) > 0:
            jsd = json.loads(msg)
            self.updateChannelStats(jsd)

    #Redefining QtGui.MainWindow method in order to cleanly destroy socket 
    #connection when the user clicks the 'X' button at the top of the window
    def closeEvent(self, event):
        self.exitApplication()
        event.accept()
#END Qnet class


class ConnectDialog(QDialog):
    def __init__(self, parent):
        super(ConnectDialog, self).__init__(parent)
        self.parent = parent
        # Create widgets
        self.ip = QLineEdit(parent.ip)
        self.port = QLineEdit(parent.port)
        self.button = QPushButton("Connect")
        self.button.clicked.connect(self.tcpConnect)
        # Create layout and add widgets
        self.layout = QFormLayout()
        self.layout.addRow("Host",self.ip)
        self.layout.addRow("Port",self.port)
        self.layout.addRow(self.button)
        # Set dialog layout
        self.setLayout(self.layout)
        self.setWindowTitle('Connection Dialog')    

    # connects socket
    def tcpConnect(self):
        self.parent.sockHandleConnect( self.ip.text() , self.port.text() )
        self.accept()
#END class ConnectDialog(QtGui.QDialog)

class OptionsDialog(QDialog):
    def __init__(self, parent):
        super(OptionsDialog, self).__init__(parent)
        self.parent = parent

        # Create widgets
        # self.fontButton = QPushButton('Set Font')
        # self.fontButton.clicked.connect(self.setFont)

        # self.textFgButton = QPushButton('Set Text Foreground Color')
        # self.textFgButton.clicked.connect(self.setFg)

        self.textBgButton = QPushButton('Set Text Background Color')
        self.textBgButton.clicked.connect(self.setBg)

        self.saveButton = QPushButton('Save and Close')
        self.saveButton.clicked.connect(self.saveSettings)
        
        # Create layout and add widgets
        self.layout = QFormLayout()
        # self.layout.addRow('Insert Sleep Amount (Sec)',self.insSleepAmount);
        # self.layout.addRow('Time (%y%m%d-%H%M%S:)',self.tsfmt);
        
        # self.layout.addRow(self.fontButton)
        # self.layout.addRow(self.textFgButton)
        self.layout.addRow(self.textBgButton)
        self.layout.addRow(self.saveButton)

        # Set dialog layout
        self.setLayout(self.layout)
        self.setWindowTitle('Connection Dialog')    

    # def setFont(self):
    #     (font,ok) = QFontDialog.getFont(self.parent.inputLine.font())
    #     if( ok ):
    #         self.parent.fontstr = font.toString()
    #         self.parent.inputLine.setFont(font)
    #         self.parent.textBox.setFont(font)

    # def setFg(self):
    #     c = QColorDialog.getColor()
    #     self.parent.textFgColor = 'rgb('+str(c.red())+','+str(c.green())+','+str(c.blue())+')'
    #     self.parent.textBox.setStyleSheet('QTextEdit{color: '+self.parent.textFgColor+'; background: '+self.parent.textBgColor+';}');
    #     if( 'connected' == self.parent.state ):
    #         self.parent.inputLine.setStyleSheet('QLineEdit{color: '+self.parent.textFgColor+'; background: '+self.parent.textBgColor+';}');

    def setBg(self):
        c = QColorDialog.getColor()
        # self.parent.textBgColor = 'rgb('+str(c.red())+','+str(c.green())+','+str(c.blue())+')'
        # self.parent.textBox.setStyleSheet('QTextEdit{color: '+self.parent.textFgColor+'; background: '+self.parent.textBgColor+';}');
        # if( 'connected' == self.parent.state ):
        #     self.parent.inputLine.setStyleSheet('QLineEdit{color: '+self.parent.textFgColor+'; background: '+self.parent.textBgColor+';}');

    def saveSettings(self):
        # self.parent.insSleepAmount = float(self.insSleepAmount.text())
        # self.parent.tsfmt = self.tsfmt.text()
        # self.parent.font = self.font
        self.parent.saveSettings()
        self.accept()
#END class OptionsDialog(QtGui.QDialog)

# class HotKeyDialog(QDialog):
#     def __init__(self, parent):
#         super(HotKeyDialog, self).__init__(parent)
#         self.parent = parent

#         # Create widgets
#         self.ip = QLineEdit(parent.ip)
#         self.port = QLineEdit(parent.port)
#         self.button = QPushButton("Connect")
#         self.button.clicked.connect(self.tcpConnect)

#         # Create layout and add widgets
#         self.layout = QtGui.QFormLayout()
#         self.layout.addRow("Host",self.ip);
#         self.layout.addRow("Port",self.port);
#         self.layout.addRow(self.button)

#         # Set dialog layout
#         self.setLayout(self.layout)
#         self.setWindowTitle('Connection Dialog')    

#     # connects socket
#     def tcpConnect(self):
#         self.parent.sockHandleConnect( self.ip.text() , self.port.text() )
#         self.accept()
# #END class ConnectDialog(QDialog)


# class HistoricalLineEdit(QLineEdit):
#     def __init__(self, parent):
#         super(HistoricalLineEdit, self).__init__(parent)
#         self.cmds = [];#FIXME - set maximum size to list
#         self.returnPressed.connect(self.storeCmdOnReturnPress)
#         # -1 represents 'currently edited text' and 
#         #  0 represents most recent item
#         #  1 represents second most recent item, etc.
#         self.idx = -1; 
#     def keyPressEvent(self,event):
#         if(event.key() == QtCore.Qt.Key_Up):
#             #print 'DBG: QtCore.Qt.Key_Up , idx='+str(self.idx)
#             # move towards past, towards higher numbers
#             # -1 --> 0 ok if len is 1 or greater
#             #  0 --> 1 ok if len is 2 or greater,etc.
#             if( self.idx <= len(self.cmds) - 2 ):
#                 self.idx += 1
#                 self.setText(self.cmds[self.idx])
#         if(event.key() == QtCore.Qt.Key_Down):
#             #print 'DBG: QtCore.Qt.Key_Down , idx='+str(self.idx)
#             # move towards present, towards lower numbers
#             # -1 --> 0 ok if len is 1 or greater
#             #  0 --> 1 ok if len is 2 or greater,etc.
#             if( self.idx >= 0 ):
#                 self.idx -= 1
#                 if( self.idx >= 0 ):
#                     self.setText(self.cmds[self.idx])
#                 else:
#                     self.setText('')
#         if(event.key() == QtCore.Qt.Key_Escape):
#             self.idx = -1
#             self.setText('')
#         else:
#             #default handler for event
#             QLineEdit.keyPressEvent(self,event)

#     @PyQtSlot()
#     def storeCmdOnReturnPress(self):
#         if( len(self.cmds) ):
#             if( self.text() != self.cmds[0] ):
#                 self.cmds.insert(0,self.text())
#                 self.idx = -1
#         else:
#             self.cmds.insert(0,self.text())
#         #print "DBG: self.cmds: "+str(self.cmds)
# #END class HistoricalLineEdit(QtGui.QLineEdit)
        

# Using a QRunnable
# http://doc.qt.nokia.com/latest/qthreadpool.html
# Note that a QRunnable isn't a subclass of QObject and therefore does
# not provide signals and slots.
# class InsertFileRunnable(QtCore.QRunnable):
#     def __init__(self, parent):
#         super(InsertFileRunnable, self).__init__(parent)
#         self.insFile = parent.insFile
#         self.qsock = parent.qsock
#         self.parent = parent
#     def run(self):
#         f = open(self.insFile,'r')
#         for line in f:
#             sline = line.rstrip();
#             if( sline ):
#                 self.qsock.write(QtCore.QByteArray(line.rstrip()+'\r\n'))
#                 time.sleep(self.parent.insSleepAmount)
#         f.close()
#END class InsertFileRunnable(QtCore.QRunnable)

def main():
    app = QApplication(sys.argv)
    jack_stream_listen = JackStreamListen()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

