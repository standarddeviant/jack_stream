#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Attempt at writing jack_stream client/audio-player

author: Dave Crist
last edited: February 2018
"""

import os, sys, json, time, logging
from os.path import join, expanduser
from operator import add

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
    from PyQt5.QtCore import QByteArray, QIODevice
    from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudioFormat, QAudioOutput
    # from PyQt5.QtCore import QObject, pyqtSlot
    # from PyQt5.QtCore import pyqtSignal as QtSignal
except:
    logging.error('Unable to import PyQt5')
    sys.exit()


from jack_stream_common import msgify_pkt, JACK_STREAM_VERSION

class ChannelWidgetType:
    def __init__(self, button, rms, clips):
        self.button = button
        self.rms    = rms
        self.clips  = clips

class JackStreamListen(QMainWindow):
    checkInQueueSignal = PyQtSignal()
    def __init__(self):
        super(JackStreamListen, self).__init__()
        self.ip = '127.0.0.1'
        self.port = '23'
        self.state = 'disconnected'
        self.channel_select = -1
        self.channel_count = -1
        # self.tsfmt = '%y%m%d-%H%M%S:'
        # self.textFgColor = 'rgb(0,0,0)'
        # self.textBgColor = 'rgb(255,255,255)'
        # self.fontstr = 'Helvetica'

        logging.debug('DBG: state = '+self.state)

        # self.insFile = "";self.insDir=""
        # self.insSleepAmount = 0;

        self.qsock = QtNetwork.QTcpSocket(self)
        self.qsock.readyRead.connect(self.onReadyRead)
        
        # create None/empty variables to be created/updated later
        self.prevpkt = bytearray() # note a QByteArray b/c reusing msgify_pkt
        self.audiodata = bytearray()
        self.clips = []
        self.rms = []
        self.audiofmt = QAudioFormat()
        self.audioout = QAudioOutput()
        self.iodevice = self.createIoDevice()

        #FIXME self.tcpSocket.error.connect(self.displayError)

        # self.font = QtGui.QFont()
        self.loadSettings()
        self.initUI()
        
    def initUI(self):
        # self.destroyed is inherited from QMainWindow
        self.destroyed.connect(self.exitApplication)

        # make colored status label at the bottom
        self.statusLabel = QLabel('STATUS: Disconnected')
        self.statusLabel.setStyleSheet('QLabel {color: white; background: red}')

        # create layout/widgets for channels stats to be updated later
        self.setCentralWidget(QLabel('Waiting for connection and channels metadata'))

        self.connectAction = QAction('Connect', self);self.connectAction.setShortcut('Ctrl+X')
        self.connectAction.triggered.connect(self.invokeConnectDialog);
        self.disconnectAction = QAction('Disonnect', self);self.disconnectAction.setShortcut('Ctrl+D')
        self.disconnectAction.triggered.connect(self.disconnect);self.disconnectAction.setEnabled(0)
        self.exitAction = QAction('Exit', self);self.exitAction.setShortcut('Ctrl+Q')
        self.exitAction.triggered.connect(self.exitApplication)
        self.optionsAction = QAction('Options', self);self.optionsAction.setShortcut('Ctrl+O')
        self.optionsAction.triggered.connect(self.invokeOptionsDialog)

        # Create main toolbar
        mainbar = QToolBar('Main');mainbar.setParent(self)
        self.addToolBar(QtCore.Qt.TopToolBarArea,mainbar)
        mainbar.setMovable(0)
        mainbar.addAction(self.connectAction)
        mainbar.addAction(self.disconnectAction)
        mainbar.addAction(self.optionsAction)

        #adding to window so the key shortcut works, but it's not displayed in the menu
        self.addAction(self.exitAction)

        inputbar=QToolBar('Input'); inputbar.setParent(self)
        self.addToolBar(QtCore.Qt.BottomToolBarArea,inputbar)
        inputbar.setMovable(0)
        inputbar.addWidget(self.statusLabel)

        # create empty list to be used/referenced after we've connected to the host
        self.channelsWidgets = [] 

        self.setGeometry(300, 300, 350, 250)
        self.setWindowTitle('jack_stream_listen v'+JACK_STREAM_VERSION)    
        self.show()

    def createIoDevice(self):
        pass

    def invokeConnectDialog(self):
        if( self.state == 'disconnected' ):
            connectDialog = ConnectDialog(self)
            connectDialog.show()

    def invokeOptionsDialog(self):
        optionsDialog = OptionsDialog(self)
        optionsDialog.show()

    def sockHandleConnect(self,ip,port):
        self.ip=ip ; self.port=port
        self.qsock.connectToHost(ip,int(port))
        self.state = 'connected'
        logging.debug('state = '+self.state+': '+self.ip+':'+self.port)

        self.connectAction.setEnabled(0)
        self.disconnectAction.setEnabled(1)
        self.statusLabel.setText('STATUS: Connected, waiting for Initialization')
        self.statusLabel.setStyleSheet('QLabel {color: black; background: yellow}')

    def disconnect(self):
        if( self.state == 'connected' ):
            self.qsock.disconnectFromHost()
            self.state = 'disconnected'
            logging.debug('state = '+self.state+'\n')

            self.connectAction.setEnabled(1)
            self.disconnectAction.setEnabled(0)
            self.statusLabel.setText('STATUS: Disconnected')
            self.statusLabel.setStyleSheet('QLabel {color: white; background: red}')

            self.channel_count = -1
            # self.channel_select = -1


    @PyQtSlot(int)
    def sendMetaToServer(self, cidx):
        metastr = json.dumps(dict(channel_select=cidx))
        if( self.state == 'connected' ):
            print('cidx = {}'.format(cidx))
            dbg = self.qsock.write(QByteArray(bytearray(metastr.encode())))

    def exitApplication(self):
        if( self.state == 'connected' ):
            self.qsock.disconnectFromHost()
            self.state = 'disconnected'
        self.saveSettings()
        self.close()

    def saveSettings(self):
        cfgParser = configparser.RawConfigParser()
        cfgParser.add_section('Generic')
        cfgParser.set('Generic', 'ip', self.ip)
        cfgParser.set('Generic', 'port', self.port)
        cfgParser.set('Generic', 'channel_select', self.channel_select)
        
        with open(join(expanduser('~'), 'jack_stream_listen.cfg'), 'w') as cfgfile:
            cfgParser.write(cfgfile)

    def loadSettings(self):
        cfgParser = configparser.RawConfigParser()
        cfgParser.read(join(expanduser('~'), 'jack_stream_listen.cfg'))
        if( cfgParser.has_section('Generic') ):
            self.ip = cfgParser.get('Generic','ip')
            self.port = cfgParser.get('Generic','port')

    @PyQtSlot()
    def onReadyRead(self):
        # tstr = time.strftime(self.tsfmt)
        curpkt = bytearray(self.qsock.readAll())
        msgtype, msg = msgify_pkt(self.prevpkt, curpkt)

        if msgtype == 'META' and len(msg) > 0:
            self.updateMetadata(msg)

    def createChannelsWidgets(self):
        self.channelsContainer = QWidget()
        self.channelsLayout = QGridLayout()
        self.channelsContainer.setLayout( self.channelsLayout )

        self.channelsWidgets = [
            ChannelWidgetType(
                QPushButton(str(idx), self),
                QLabel(self),
                QLabel(self)
            )
            for idx in range(self.channel_count)
        ]

        self.channelsButtonGroup = QButtonGroup(self)
        for cidx,cw in enumerate(self.channelsWidgets):
            self.channelsButtonGroup.addButton(cw.button, cidx)
            self.channelsLayout.addWidget(cw.button, 0, cidx)
            self.channelsLayout.addWidget(cw.rms,    1, cidx)
            self.channelsLayout.addWidget(cw.clips,  2, cidx)

            self.channelsButtonGroup.buttonClicked[int].connect(self.sendMetaToServer)


        self.setCentralWidget(self.channelsContainer)
    # end createChannelsWidgets

    def updateMetadata(self, msg):
        if self.channel_count < 0:
            try:
                self.channel_count = msg['format']['channel_count']
                self.createChannelsWidgets()
                self.statusLabel.setText('STATUS: Connected AND Initialized')
                self.statusLabel.setStyleSheet('QLabel {color: black; background: green}')

            except Exception as e:
                print(str(e))
                logging.warning('Unable to set channel count from META msg')
                logging.warning(json.dumps(msg, indent=4))
            
            self.rms = [0.0, ] * self.channel_count
            self.clips = [0, ] * self.channel_count
            self.createChannelsWidgets()


        if 'rms' in msg and 'clips' in msg:
            assert len(msg['rms']) == len(msg['clips']) == self.channel_count
            self.rms = msg['rms']
            self.clips = list(map(add, self.clips, msg['clips']))
            
            for cidx,cw in enumerate(self.channelsWidgets):
                cw.rms.setText('{:3f}'.format(msg['rms'][cidx]))

    #Redefining QtGui.MainWindow method in order to cleanly destroy socket 
    #connection when the user clicks the 'X' button at the top of the window
    def closeEvent(self, event):
        self.exitApplication()
        event.accept()
#END Qnet class

class BufferQueueIO(QIODevice):
    def __init__(self, bufQ, parent):
        super(BufferQueueIO, self).__init__(parent)
        self.buffer = QByteArray()
        self.bufQ = bufQ

    def start(self):
        self.open(QIODevice.ReadOnly)

    def stop(self):
        self.m_pos = 0
        self.close()

    def readData(self, maxlen):
        if self.bufQ.qsize() >= 2:
            self.buffer.append(self.bufQ.get())

        if self.buffer.length() < maxlen:
             # FIXME, return correct length QByteArray of zeros
            return QByteArray(bytearray((0,)*10)).data()
        else:
            outp = self.buffer.mid(0, maxlen).data()
            self.buffer.remove(0, maxlen)
            return outp

    def writeData(self, data):
        return 0

    def bytesAvailable(self):
        return self.m_buffer.size() + super(BufferQueueIO, self).bytesAvailable()

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

