import sys, os

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem, QHeaderView, QCheckBox
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from functools import partial

import serial
import argparse
import sys
import time
import numpy as np
import os

testData = {
    "TOP_LEVEL" : {
        "hex": "0x00",
        "signals" : {
            "Counter 0" : {
                "hex": "0x00",
                "type": "uint16"
            },
            "Counter 1" : {
                "hex": "0x01",
                "type": "uint16"
            },
            "Counter 2" : {
                "hex": "0x02",
                "type": "uint16"
            },
            "Counter 3" : {
                "hex": "0x03",
                "type": "uint16"
            },
            "Counter 4" : {
                "hex": "0x04",
                "type": "uint16"
            },
            "Counter 5" : {
                "hex": "0x05",
                "type": "uint16"
            },
            "Counter 6" : {
                "hex": "0x06",
                "type": "uint16"
            },
            "Counter 7" : {
                "hex": "0x07",
                "type": "uint16"
            },
            "BTN" : {
                "hex": "0x08",
                "type": "hex"
            },
            "LEDs" : {
                "hex": "0x09",
                "type": "hex"
            },
            "Nothing 0x00" : {
                "hex": "0x0A",
                "type": "hex",
                "update": False
            }
        }
    },
    "Delay" : {
        "hex": "0x01",
        "signals": {
            "cnt" : {
                "hex": "0x00",
                "type": "uint16"
            },
            "CNT_MAX" : {
                "hex": "0x01",
                "type": "uint16"
            },
            "Fire" : {
                "hex": "0x02",
                "type": "hex"
            },
            "Nothing 0" : {
                "hex": "0x03",
                "type": "hex"
            },
            "Nothing 1" : {
                "hex": "0x03",
                "type": "hex"
            }
        }
    }
}


import threading
import struct


class UART2Debug(object):

    def __init__(self, signalConfig=None, updateFunc=None, updateTime=1.0) -> None:
        
        self.read_thread_running = True
        self.inited = False
        self.serialPort = None
        self.serial_thread = None
        if signalConfig is not None:
            self.setSignalConfig(signalConfig)

        self.updateTime = updateTime
        self.dataCBs = []
        self.registerDataUpdateCB(updateFunc)
        self.connectionCBs = []

    def setSignalConfig(self, signalConfig):
        # Reorganize this dict to be one dimensional 
        sigCfg = {}
        for entityName, entity in signalConfig.items():
            for signalName, signal in signalConfig[entityName]["signals"].items():
                key = f"{entityName}_*_{signalName}"
                sigCfg[key] = signal
                sigCfg[key]["sel"] = entity["hex"]
                sigCfg[key]["signal"] = signalName
                sigCfg[key]["entity"] = entityName
                if "update" not in sigCfg[key]:
                    sigCfg[key]["update"] = True

        self.signalConfig = sigCfg

    def setSignalConfigFromFile(self, fn):
        with open(fn, "r") as f:
            signalConfig = json.load(f)
            self.setSignalConfig(signalConfig)

    def registerDataUpdateCB(self, updateFunc):
        """
        Register a data update function.
        """
        if updateFunc is not None:
            self.dataCBs.append(updateFunc)

    def registerConnectCB(self, connectionCB):
        """
        Register a function that is called on a connection.
        """
        if connectionCB is not None:
            self.connectionCBs.append(connectionCB)

    def accurate_delay(self, delay):
        """
        Function to provide accurate time delay in millisecond
        This is required since Windows does not allow delays < 15ms
        """
        _ = time.perf_counter() + delay/1000
        while time.perf_counter() < _:
            pass

    def send2connectionCBs(self, connected, e=""):
        """
        Update connection cbs on change.
        """
        for cb in self.connectionCBs:
            cb(connected, error=str(e))

    def connectionError(self, e=""):
        """
        Some error happened during uart read/write 
        """
        print("Error while connection")
        self.disconnect()
        self.send2connectionCBs(False, e=e)

    def waitForConnection(self):
        """
        Actively wait for correct response from debug2uart.
        """
        while self.running:
            # Flush input
            try:
                ch = self.serialPort.read_all()
                self.serialPort.write(b"\xfe")
                ch = self.serialPort.read(1)
            except Exception as e:
                self.connectionError(e)
                return
            if len(ch) != 1:
                print("try again")
                time.sleep(0.5)
                continue
            elif ch != b"\xfe": #struct.unpack('>B', ch)[0] != 254:
                print(f"wrong answer {ch}")
                time.sleep(1.0)
                continue
            print("Connection successful")
            return

    def readSignal(self, cfgEntry):
        return self.readAddress(cfgEntry["hex"], sel=cfgEntry["sel"] if "sel" in cfgEntry else None)

    def readAddress(self, addr, sel=None):
        """
        Read bytes of a given address.
        """
        try:
            # Flush input
            # if serialPort.inWaiting() > 0:
            #     ch = serialPort.read_all()
            self.serialPort.write(b"\x00")
            # Write output
            if sel is not None: self.serialPort.write(struct.pack('>B', sel))
            self.serialPort.write(struct.pack('>B', addr))
            self.accurate_delay(0.5)
            ch = self.serialPort.read(4)
        except Exception as e:
            self.connectionError(e)
            return None
            
        if len(ch) != 4:
            return None
        return ch


    def blockRead(self, addresses, sels=None):
        """
        Block read of bytes from the given addresses
        """
        try:
            # Flush remaining incoming data
            _ = self.serialPort.read_all()
        except Exception as e:
            self.connectionError(e)
        # All register read requests at once
        for i,addr in enumerate(addresses):
            byts = b"\x00"
            if sels is not None and i < len(sels) and sels[i] is not None: 
                byts += struct.pack('>B', sels[i])

            byts += struct.pack('>B', addr)
            try:
                self.serialPort.write(byts)
                self.serialPort.flush()
            except Exception as e:
                self.connectionError(e)
                return None
            # As fast as possible
            self.accurate_delay(0.6)
        try:
            # Read all at once
            ch = self.serialPort.read(len(addresses)*4)
        except Exception as e:
            self.connectionError(e)
            return None
        if len(ch) != len(addresses)*4:
            return None
        # Split
        res = []
        for i in range(len(addresses)):
            res.append(ch[i*4:(i+1)*4])
        return res

    def readValue(self, addr):
        """
        Read hex values from register address
        """
        btes = self.readAddress(addr)
        if btes is None: return None
        self.convBytes2Type(btes, "hex")

    def convBytes2Type(self, btes, typ):
        """
        Convert the given bytes to the given type
        """
        if typ == "int8": return struct.unpack('<b', btes[:1])[0]
        if typ == "uint8": return struct.unpack('<B', btes[:1])[0]
        if typ == "int16": return struct.unpack('<h', btes[:2])[0]
        elif typ == "uint16": return struct.unpack('<H', btes[:2])[0]
        elif typ == "int32": return struct.unpack('<i', btes)[0]
        elif typ == "uint32": return struct.unpack('<L', btes)[0]
        elif typ == "char": return chr(struct.unpack('<B', btes)[0])
        elif typ == "hex": return hex(struct.unpack('<L', btes)[0])
        elif typ == "float": return struct.unpack('<f', btes)[0]

    def send2dataUpdateCBs(self, data):
        """
        Send data to all cbs
        """
        for cb in self.dataCBs:
            cb(data)

    def entityAddress(self, entityKey):
        """Return the sel address of an entity from cfg"""
        return self.signalConfig[entityKey]["hex"]

    def update_uart(self):
        """
        Thread to update uart
        """
        while self.running:
            # Only if port is open
            if self.serialPort is not None and self.serialPort.is_open:
                if not self.inited: 
                    print("try init")
                    self.waitForConnection()
                    self.send2connectionCBs(True)
                    self.inited = True
                else:
                    data = {}
                    # All registers in one chunk
                    addresses = {k: int(self.signalConfig[k]["hex"], 16) for k in self.signalConfig if self.signalConfig[k]["update"]}
                    sels = [None if "sel" not in self.signalConfig[k] else int(self.signalConfig[k]["sel"], 16) for k in self.signalConfig if self.signalConfig[k]["update"]]
                    res = self.blockRead([addresses[k] for k in addresses], sels)
                    if res != None:
                        for r,k in zip(res, addresses):
                            data[k] = self.convBytes2Type(r, self.signalConfig[k]["type"])
                        self.send2dataUpdateCBs(data)

                    # Register by register (slow and on windows at least 15ms wait)
                    # Flush remaining
                    # if serialPort.inWaiting() > 0:
                    #     _ = serialPort.read_all()
                    # for k in cfg:
                    #     addr = int(cfg[k]["hex"], 16)
                    #     btes = readAddress(addr)
                    #     accurate_delay(0.5)
                    #     if btes is None: 
                    #         data[k] = "unknown"
                    #     else:
                    #         data[k] = convBytes2Type(btes, cfg[k]["type"])
                    # updateFunc(data)
            time.sleep(self.updateTime)

    def connect(self):
        """
        Connect to the serialport
        """
        if self.serialPort is not None:
            print("port already open")
            return False

        self.inited = False
        self.serialPort = serial.Serial(args.port, baudrate=args.baud, timeout=1.0)
        try:
            self.serialPort.open()
        except:
            pass
        if not self.serialPort.is_open:
            print("cannot open serialport" + str(args.port))
            return False
        print("serialport connection successfull")
        
        self.serial_thread = threading.Thread(target=self.update_uart)
        self.serial_thread.daemon = True
        self.running = True
        self.serial_thread.start()
        return True

    def disconnect(self):
        """
        Disconnect from the serialport
        """
        if self.serialPort is not None and self.serialPort.is_open:
            self.serialPort.close()
        else:
            print("already closed")
        self.serialPort = None
        self.running = False
        self.serial_thread.join()
        self.serial_thread = None
        self.inited = False
        self.send2connectionCBs(False)


class LabelledIntField(QtWidgets.QWidget):
    def __init__(self, title, initial_value=None, unit="", endEditCB=None):
        QtWidgets.QWidget.__init__(self)
        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)
        
        self.label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.label.setText(title)
        self.label.setFont(QFont("Arial",weight=QFont.Bold))
        layout.addWidget(self.label)

        innerLayout = QtWidgets.QHBoxLayout()
        self.lineEdit = QtWidgets.QLineEdit(self,  alignment=QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.lineEdit.setFixedWidth(60)
        self.lineEdit.setValidator(QtGui.QIntValidator())
        if initial_value != None:
            self.lineEdit.setText(str(int(initial_value)))
        innerLayout.addWidget(self.lineEdit)

        label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        label.setText(unit)
        innerLayout.setSpacing(0)
        innerLayout.addWidget(label)

        layout.addLayout(innerLayout)

        layout.addStretch()
        if endEditCB != None:
            self.lineEdit.editingFinished.connect(endEditCB)
        
    def setLabelWidth(self, width):
        self.label.setFixedWidth(width)
        
    def setInputWidth(self, width):
        self.lineEdit.setFixedWidth(width)
        
    def getValue(self):
        return int(self.lineEdit.text())

    def setValue(self, val):
        return self.lineEdit.setText(str(val))

# Helper alignment delegates
class AlignRightDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super(AlignRightDelegate, self).initStyleOption(option, index)
        option.displayAlignment = QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
class AlignCenterDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super(AlignCenterDelegate, self).initStyleOption(option, index)
        option.displayAlignment = QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter
class AlignLeftDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super(AlignLeftDelegate, self).initStyleOption(option, index)
        option.displayAlignment = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
class BoldNoParentsDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.parent().row() == -1:
            option.font.setWeight(QFont.Bold)
        QtWidgets.QStyledItemDelegate.paint(self, painter, option, index)
class BoldDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.font.setWeight(QFont.Bold)
        QtWidgets.QStyledItemDelegate.paint(self, painter, option, index)

styleSheet = """
    QTreeView::item:open {
        background-color: #c5ebfb;
    }  
"""
class UART2DebugWidget(QtWidgets.QWidget):
    def __init__(self, uart2debug, updateFreq=0.1):
        super().__init__()

        self.uart2debug = uart2debug
        self.uart2debug.registerConnectCB(self.connectionStatusChanged)
        self.uart2debug.registerDataUpdateCB(self.updateData)
        self.updateFreq = updateFreq

        self.setStyleSheet(styleSheet)
        self.tree = QTreeWidget()
        self.headerTitles = ["Name", "Address", "Type", "Value", "Upd"]
        self.tree.setHeaderLabels(self.headerTitles)

        # Standard for all
        delegate = AlignCenterDelegate(self.tree)
        for i in range(len(self.headerTitles)):
            self.tree.setColumnWidth(i, 60)
            self.tree.header().setSectionResizeMode(i, QHeaderView.Fixed)
            self.tree.headerItem().setTextAlignment(i, QtCore.Qt.AlignCenter)
            self.tree.setItemDelegateForColumn(i, delegate)

        # Specifics
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setColumnWidth(len(self.headerTitles)-2, 80)
        self.tree.setColumnWidth(len(self.headerTitles)-1, 30)
        self.tree.header().setStretchLastSection(False)

        delegate = AlignLeftDelegate(self.tree)
        self.tree.setItemDelegateForColumn(0, delegate)
        delegate = AlignRightDelegate(self.tree)
        self.tree.setItemDelegateForColumn(3, delegate)
        self.tree.setItemDelegateForColumn(4, delegate)

        self.initTreeView()

        self.is_connected = False

        # Main window layout
        self.layout = QtWidgets.QVBoxLayout(self)
        self.button_layout = QtWidgets.QHBoxLayout(self)
        self.layout.addWidget(self.tree)
        self.layout.addLayout(self.button_layout)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.button_layout.setContentsMargins(20,0,20,0)

        # Bottom widgets
        self.connectButton = QtWidgets.QPushButton("Connect")
        self.connectButton.clicked.connect(self.connectClicked)

        self.loadButton = QtWidgets.QPushButton("Load Config")
        self.loadButton.clicked.connect(self.getConfigfile)

        self.updateTime = LabelledIntField('Update time:', unit="ms", initial_value=self.updateFreq*1000, endEditCB=self.updateFreqChanged)
        
        self.updateAllCheckBox = QtWidgets.QCheckBox("Update all")

        # Add to layout
        self.button_layout.addWidget(self.connectButton, alignment=QtCore.Qt.AlignLeft)
        self.button_layout.addWidget(self.loadButton, alignment=QtCore.Qt.AlignLeft)
        self.button_layout.addWidget(self.updateTime, alignment=QtCore.Qt.AlignCenter)
        self.button_layout.addWidget(self.updateAllCheckBox, alignment=QtCore.Qt.AlignRight)

        # Own data
        self.data = {k:"unknown" for k in self.uart2debug.signalConfig}

        self.updateAllCheckBox.stateChanged.connect(self.updateAllToggle)
        self.checkSetGroupCheckboxes()

        self.running = True
        
        self.dirty = False
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.setInterval(int(self.updateFreq*1000))
        self.updateTimer.timeout.connect(self.updateContent)
        self.updateTimer.start()
        self.checkAllTimer = None

    def loadConfigFile(self, fn):
        uart2debug.setSignalConfigFromFile(fn)
        self.initTreeView()
        self.checkSetGroupCheckboxes()

    def getConfigfile(self):
        fname = QtWidgets.QFileDialog.getOpenFileName(self, 'Open file', 
            '~',"JSON files (*.json)")
        self.loadConfigFile(fname[0])

    def initTreeView(self):
        self.tree.clear()
        self.treeItems = {}
        self.checkboxes = []
        self.entityCheckboxes = {}
        self.tree.setColumnCount(len(self.headerTitles))

        self.groupedSignals = {}
        for key, entry in self.uart2debug.signalConfig.items():
            if entry["entity"] in self.groupedSignals:
                self.groupedSignals[entry["entity"]].append(entry["signal"])
            else:
                self.groupedSignals[entry["entity"]] = [entry["signal"]]

        for entityName, items in self.groupedSignals.items():
            # Get address of entity by getting dict 
            # entry of first signal in group 
            firstSignal = next(i for i in items)
            key = f"{entityName}_*_{firstSignal}"
            entitySelAddress = self.uart2debug.signalConfig[key]["sel"]
            entityItem = QTreeWidgetItem([entityName, entitySelAddress])
            for signalName in items:
                key = f"{entityName}_*_{signalName}"
                entry = self.uart2debug.signalConfig[key]
                signalItem = QTreeWidgetItem([signalName, entry["hex"], entry["type"], "unknown", ""])
                entityItem.addChild(signalItem)
            self.treeItems[entityName] = entityItem


        self.tree.insertTopLevelItems(0, [i for _,i in self.treeItems.items()])
        self.tree.setAnimated(True)

        # Expand only parents
        proxy = self.tree.model()
        for row in range(proxy.rowCount()):
            index = proxy.index(row, 0)
            self.tree.expand(index)

        # Add update checkbox to each entry
        j = 0
        # Loop over entities
        for entityName,treeItem in self.treeItems.items():
            checkBox = QCheckBox("")
            checkBox.setStyleSheet("padding-left:10px; margin-right:50%;")
            checkBox.stateChanged.connect(partial(self.entityUpdateCheckBox,entityName))
            self.entityCheckboxes[entityName] = checkBox
            self.tree.setItemWidget(treeItem, len(self.headerTitles)-1, checkBox)

            # Loop over signals
            for i in range(treeItem.childCount()):
                checkBox = QCheckBox("")
                checkBox.setChecked(self.signalCfgFromIdx(j)["update"])
                checkBox.setStyleSheet("padding-left:10px; margin-right:50%;")
                self.tree.setItemWidget(treeItem.child(i), len(self.headerTitles)-1, checkBox)
                checkBox.toggled.connect(partial(self.checkBoxToggle,j))
                self.checkboxes.append(checkBox)
                j += 1
                
        self.tree.setItemDelegateForColumn(1, BoldNoParentsDelegate(self))
        self.tree.setItemDelegateForColumn(0, BoldDelegate(self))


    def updateFreqChanged(self):
        val = self.updateTime.getValue()
        if val is None or val < 20:
            self.updateTime.setValue(20)
            val = 20
        self.updateTimer.stop()
        self.uart2debug.updateTime = val/1000.0
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.setInterval(val)
        self.updateTimer.timeout.connect(self.updateContent)
        self.updateTimer.start()

    def keyFromIdx(self, i):
        keys = list(self.uart2debug.signalConfig.keys())
        if i >= 0 and i < len(keys): return keys[i]
        return None

    def signalCfgFromIdx(self, i):
        k = self.keyFromIdx(i)
        if k is None: return None
        return self.uart2debug.signalConfig[k]
        return None
        
    def connectionStatusChanged(self, connected, error=""):
        if connected:
            print("Connected")
            self.is_connected = True
            self.connectButton.setText("Disconnect")
        else:
            print("Disconnected")
            self.is_connected = False
            self.connectButton.setText("Connect")
        if error != "":
            print(f"Error: {error}")

    def connect(self):
        print("trying to connect")
        con = self.uart2debug.connect()
        if con: self.connectButton.setText("Waiting")
        else: self.connectButton.setText("Connect")

    def disconnect(self):
        print("trying to disconnect")
        self.connectButton.setText("Connect")
        self.uart2debug.disconnect()
        self.is_connected = False
    
    @QtCore.Slot()
    def connectClicked(self):
        if self.is_connected: 
            self.disconnect()
        else: 
            self.connect()
    
    def checkGroup(self, g=None):
        if g is None:
            states = [i["update"] for _,i in self.uart2debug.signalConfig.items()]
        else:
            states = [i["update"] for _,i in self.uart2debug.signalConfig.items() if i["entity"] == g]
        allChecked = all(states)
        allUnchecked = all([not s for s in states])
        if allChecked: return Qt.Checked
        elif allUnchecked: return Qt.Unchecked
        else: return Qt.PartiallyChecked

    def checkSetGroupCheckboxes(self):
        self.updateAllCheckBox.stateChanged.disconnect()
        state = self.checkGroup()
        self.updateAllCheckBox.setCheckState(state)
        self.updateAllCheckBox.stateChanged.connect(self.updateAllToggle)

        for entityName, checkBox in self.entityCheckboxes.items():
            checkBox.stateChanged.disconnect()
            state = self.checkGroup(g=entityName)
            checkBox.setCheckState(state)
            checkBox.stateChanged.connect(partial(self.entityUpdateCheckBox,entityName))

        self.checkAllTimer = None

    def checkBoxToggle(self, row, state):
        k = self.keyFromIdx(row)
        if k is not None:
            self.uart2debug.signalConfig[k]["update"] = state
        if self.checkAllTimer is None:
            self.checkAllTimer = QtCore.QTimer(self)
            self.checkAllTimer.singleShot(100, self.checkSetGroupCheckboxes)

    def updateAllToggle(self, state):
        if state != Qt.PartiallyChecked:
            for checkBox in self.checkboxes:
                checkBox.setChecked(state)
        # Otherwise click cycles through all states rather than
        # alternating between checked and not checked
        else:
            self.updateAllCheckBox.setCheckState(Qt.Checked)

    def entityUpdateCheckBox(self, entityName, state):
        # TODO: 
        if state != Qt.PartiallyChecked:
            print(f"Update: {entityName}: {state}")

            for i,checkBox in enumerate(self.checkboxes):
                k = self.keyFromIdx(i)
                if self.uart2debug.signalConfig[k]["entity"] == entityName:
                    checkBox.setChecked(state)
        # Otherwise click cycles through all states rather than
        # alternating between checked and not checked
        else:
            try:
                checkBox = next(c for name,c in self.entityCheckboxes.items() if name == entityName)
                checkBox.setCheckState(Qt.Checked)
            except:
                pass

    def handleItemClicked(self, item):
        print(item.checkState())
        if item.column() == 3:
            print('"%s" Checked' % item.text())
        else:
            print('"%s" Clicked' % item.text())

    # def addEntry(self, i, j, text, editable=False, bold=False):
    #     entry = QTreeWidgetItem(text)
    #     if bold:
    #         f = QFont()
    #         f.setBold(True)
    #         entry.setFont(f)
    #     if not editable:
    #         entry.setFlags(Qt.ItemIsEnabled)
    #     self.tree.setItem(i, j, entry)

    def updateData(self, dic):
        for k in dic:
            self.data[k] = dic[k]
        self.dirty = True

    def updateContent(self):
        if self.dirty:
            for i,k in enumerate(self.data):
                if self.uart2debug.signalConfig[k]["update"]:
                    entity, signal = k.split("_*_")
                    treeItem = self.treeItems[entity]
                    index = self.groupedSignals[entity].index(signal)
                    self.tree.topLevelItem(0).child(1).setText(1, f"Test:")
                    treeItem.child(index).setText(3, f"{self.data[k]}")

        self.dirty = False
    
    def stop(self):
        self.updateTimer.stop()

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, uart2debug, updateFreq=0.1):
        # You must call the super class method
        QtWidgets.QMainWindow.__init__(self)
        self.setWindowTitle("FPGA data")             # Set the window title
        self.central_widget = UART2DebugWidget(uart2debug, updateFreq=updateFreq)
        self.setCentralWidget(self.central_widget)       # Install the central widget
        self.setMinimumSize(QSize(800, 600))         # Set sizes 

import signal 

def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    # sys.stderr.write('\r')
    # if QtWidgets.QMessageBox.question(None, '', "Are you sure you want to quit?",
    #                         QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
    #                         QtWidgets.QMessageBox.No) == QtWidgets.QMessageBox.Yes:
    QApplication.quit()




def initParser():
    import argparse
    parser = argparse.ArgumentParser(description="Signal tap interface to readout signals on an FPGA over a uart connection.\
                                                  Use in conjunction with the debug2uart_register or debug2_uart_ram VHDL module.\
                                                  Based on your design, provide a corresponding JSON file with signal names, addresses and \
                                                  data types.")
    parser.add_argument("port", type=str,
                        help="SerialPort path. COMX on windows, /dev/ttyXXX on Unix/Posix systems.")
    parser.add_argument("--baud", type=int, default=115200,
                        help="Baudrate of serialport")
    parser.add_argument("-u", "--updateTime", type=float, default=1.0,
                        help="Time in seconds to update all values")
    parser.add_argument("--cfg", type=str, default="uart2bus.json",
                        help="JSON with register configuration")
    return parser


import json

# _______________Can be called as main__________________
if __name__ == '__main__':
    
    keyboard_input = ""
    parser = initParser()
    args = parser.parse_args()
    signalConfig = testData

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    uart2debug = UART2Debug(updateTime=args.updateTime)

    if os.path.exists(args.cfg):
        uart2debug.setSignalConfigFromFile(args.cfg)
    else:
        uart2debug.setSignalConfig(testData)




    app = QtWidgets.QApplication(sys.argv)


    mw = MainWindow(uart2debug, args.updateTime)
    mw.resize(800, 600)

    mw.show()

    app.exec()

    mw.stop()

    uart2debug.disconnect()