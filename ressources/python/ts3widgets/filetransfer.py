import os

from . import _errprint

import ts3lib
from ts3defines import ERROR_ok, ERROR_database_empty_result, FileListType
import pytson
from pytsonui import setupUi
import ts3client

from pluginhost import PluginHost
from signalslot import Signal

from PythonQt.QtCore import (Qt, QAbstractItemModel, QModelIndex)
from PythonQt.QtGui import (QDialog, QStyledItemDelegate, QIcon, QHeaderView,
                            QSortFilterProxyModel, QFileDialog)

from datetime import datetime


def splitpath(path):
    """

    """
    return ["/"] + list(filter(None, path.split('/')))


def joinpath(*args):
    """

    """
    return "/" + "/".join(filter(lambda x: x not in ["/", ""], args))


def bytesToStr(size):
    bias = 1024.0
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']

    for u in units:
        if abs(size) < bias:
            return "%3.2f %s" % (size, u)
        size /= bias

    return "%3.2f PiB" % size


class File(object):
    """

    """

    def __init__(self, path, name, size, date, atype, incompletesize):
        self.path = path
        self.name = name
        self.size = size
        self.datetime = datetime.fromtimestamp(date)
        self.type = atype
        self.incompletesize = incompletesize

    @property
    def isDirectory(self):
        """

        """
        return self.type == FileListType.FileListType_Directory

    @property
    def icon(self):
        """

        """
        if self.isDirectory:
            return QIcon.fromTheme("folder")
        else:
            ext = os.path.splitext(self.name)[-1][1:].lower()
            theme = None

            if ext in ['exe', 'dll', 'bat', 'dylib', 'sh', 'run']:
                theme = "application-x-executable"
            elif ext in ['mp3', 'ogg', 'wav', 'wma', 'flac']:
                theme = "audio-x-generic"
            elif ext in ['ttf', 'woff', 'eot']:
                theme = "font-x-generic"
            elif ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', ' bmp']:
                theme = "image-x-generic"
            elif ext in ['avi', 'wmv', 'qt', 'mkv', 'flv', 'mpg', 'ram', 'mov',
                         'mp4']:
                theme = "video-x-generic"

            if not theme:
                theme = "text-x-generic"

            return QIcon.fromTheme(theme)


class FileListModel(QAbstractItemModel, pytson.Translatable):
    """

    """

    def __init__(self, schid, cid, password, parent=None):
        """

        """
        super(QAbstractItemModel, self).__init__(parent)

        self.schid = schid
        self.cid = cid
        self.password = password

        self.pathChanged = Signal()

        self._path = None
        self.newpath = None
        self.files = []
        self.newfiles = []

        self.titles = [self._tr("Name"), self._tr("Size"), self._tr("Type"),
                       self._tr("Last Changed")]

        PluginHost.registerCallbackProxy(self)

    def __del__(self):
        """

        """
        PluginHost.unregisterCallbackProxy(self)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, val):
        self._reload(val)

    @property
    def currentFiles(self):
        return self.files

    def _reload(self, path=None):
        if path:
            self.newpath = path
        else:
            self.newpath = self._path

        self.retcode = ts3lib.createReturnCode()
        err = ts3lib.requestFileList(self.schid, self.cid, self.password,
                                     self.newpath, self.retcode)
        if err != ERROR_ok:
            _errprint(self._tr("Error requesting filellist"), err, self.schid,
                      self.cid)

    def onFileListEvent(self, schid, channelID, path, name, size, date,
                        atype, incompletesize, returnCode):
        if (schid != self.schid or channelID != self.cid or
           returnCode != self.retcode):
            return

        self.newfiles.append(File(path, name, size, date, atype,
                                  incompletesize))

    def onFileListFinishedEvent(self, schid, channelID, path):
        if (schid != self.schid or channelID != self.cid or
           path != self.newpath):
            return
        #might be unneeded (event is catched in onServerErrorEvent)

    def onServerErrorEvent(self, schid, errorMessage, error, returnCode,
                           extraMessage):
        if schid != self.schid or returnCode != self.retcode:
            return

        if error in [ERROR_ok, ERROR_database_empty_result]:
            self.beginResetModel()
            self.files = self.newfiles
            self.newfiles = []
            self.endResetModel()

            if self._path != self.newpath:
                self._path = self.newpath
                self.pathChanged.emit(self._path)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.titles[section]

        return None

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid():
            return QModelIndex()

        return self.createIndex(row, column)

    def parent(self, idx):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self.files)

    def columnCount(self, parent=QModelIndex()):
        return len(self.titles)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None

        f = self.files[idx.row()]
        if idx.column() == 0:
            if role == Qt.DisplayRole:
                return f.name
            elif role == Qt.DecorationRole:
                return f.icon
            elif role == Qt.UserRole:
                if f.isDirectory:
                    return "a%s" % f.name
                else:
                    return "b%s" % f.name
        elif role == Qt.DisplayRole:
            if idx.column() == 1 and not f.isDirectory:
                return bytesToStr(f.size)
            elif idx.column() == 2:
                if f.isDirectory:
                    return self._tr("Directory")
                else:
                    return self._tr("File")
            elif idx.column() == 3:
                return f.datetime.strftime(pytson.tr("filetransfer",
                                                     "%Y-%m-%d %H:%M:%S"))
        return None

    def fileByIndex(self, idx):
        return self.files[idx.row()]


class FileBrowser(QDialog, pytson.Translatable):
    """

    """

    def __init__(self, schid, cid, password='', path='/', parent=None, *,
                 staticpath=False, readonly=False, downloaddir=None,
                 iconpack=None):
        """

        """
        super(QDialog, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

        try:
            setupUi(self, pytson.getPluginPath("ressources", "filebrowser.ui"),
                    iconpack=iconpack)
        except Exception as e:
            self.delete()
            raise e

        self.schid = schid
        self.cid = cid
        self.password = password
        self.path = None

        self.staticpath = staticpath
        self.readonly = readonly

        if not self.readonly and not downloaddir:
            cfg = ts3client.Config()
            q = cfg.query("SELECT value FROM filetransfer "
                          "WHERE key='DownloadDir'")
            del cfg

            if q.next():
                self.downloaddir = q.value("value")
            else:
                self.delete()
                raise Exception("Error getting DownloadDir from config")
        else:
            self.downloaddir = downloaddir

        self.fileDoubleClicked = Signal()
        self.contextMenuRequested = Signal()

        self.transdlg = None

        self.listmodel = FileListModel(schid, cid, password, self)
        self.listmodel.pathChanged.connect(self.onPathChanged)

        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSortRole(Qt.UserRole)
        self.proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setSourceModel(self.listmodel)

        self.listmodel.path = path

        self.adjustUi()

    def adjustUi(self):
        """

        """
        self.filterFrame.hide()

        self.iconButton.setChecked(True)
        self.stack.setCurrentWidget(self.listPage)

        self.list.setModel(self.proxy)
        self.table.setModel(self.proxy)
        self.table.sortByColumn(0, Qt.AscendingOrder)

        if self.staticpath:
            self.upButton.setEnabled(False)
            self.homeButton.setEnabled(False)

        if self.readonly:
            self.uploadButton.setEnabled(False)
            self.downloadButton.setEnabled(False)
            self.directoryButton.setEnabled(False)
            self.deleteButton.setEnabled(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.uploadButton.connect("clicked()", self.uploadFiles)
        self.downloadButton.connect("clicked()", self.downloadFiles)
        self.deleteButton.connect("clicked()", self.deleteFiles)
        self.list.connect("doubleClicked(QModelIndex)", self.viewDoubleClicked)
        self.table.connect("doubleClicked(QModelIndex)",
                           self.viewDoubleClicked)

    def _showTransfers(self):
        if not self.transdlg:
            self.transdlg = FileTransferDialog(self.schid, self.cid,
                                               self.password, self)
            self.transdlg.show()

    def onPathChanged(self, newpath):
        self.path = newpath
        self.pathEdit.setText(newpath)

        inroot = newpath == "/"
        self.upButton.setEnabled(not inroot)
        self.homeButton.setEnabled(not inroot)

    def on_pathEdit_returnPressed(self):
        oldpath = self.listmodel.path
        if not self.readonly:
            self.listmodel.path = self.pathEdit.text

        self.pathEdit.text = oldpath

    def on_iconButton_toggled(self, act):
        if act:
            self.stack.setCurrentWidget(self.listPage)

    def on_detailedButton_toggled(self, act):
        if act:
            self.stack.setCurrentWidget(self.tablePage)

    def on_filterButton_clicked(self):
        self.filterFrame.show()

    def on_clearButton_clicked(self):
        self.filterEdit.clear()
        self.filterFrame.hide()

    def on_filterEdit_textChanged(self, newtext):
        self.proxy.setFilterRegExp(newtext)

    def on_upButton_clicked(self):
        if self.staticpath:
            return
        if self.path == "/":
            return

        self.listmodel.path = joinpath(*splitpath(self.path)[:-1])

    def on_homeButton_clicked(self):
        if self.staticpath:
            return

        self.listmodel.path = "/"

    def on_refreshButton_clicked(self):
        self.listmodel.path = self.listmodel.path

    def uploadFiles(self):
        if self.readonly:
            return

        files = QFileDialog.getOpenFileNames(self, self._tr("Upload files"),
                                             self.downloaddir)

        fca = FileCollisionAction.overwrite
        curfiles = {f.name: f for f in self.listmodel.currentFiles}
        for f in files:
            fname = os.path.split(f)[-1]
            if fname in curfiles:
                if not fca & FileCollisionAction.toall:
                    fca = FileCollisionDialog.getAction(f, curfiles[fname],
                                                        False, len(files) > 1,
                                                        self)

                if fca == 0:
                    return

                if fca & FileCollisionAction.skip:
                    if not fca & FileCollisionAction.toall:
                        fca = FileCollisionAction.overwrite
                    break

            self._showTransfers()
            self.transdlg.addUpload(self.path, f,
                                    fca & FileCollisionAction.overwrite,
                                    fca & FileCollisionAction.resume)

            if not fca & FileCollisionAction.toall:
                fca = FileCollisionAction.overwrite

    def downloadFiles(self, files=None):
        if self.readonly:
            return

        #TODO

    def on_directoryButton_clicked(self):
        if self.readonly:
            return

        #TODO

    def deleteFiles(self, files=None):
        if self.readonly:
            return

        #TODO

    def on_table_customContextMenuRequested(self, pos):
        selfiles = [self.proxy.mapToSource(x) for x in
                    self.table.selectionModel().selectedIndexes()]

        if self.readonly:
            self.contextMenuRequested.emit(selfiles,
                                           self.table.mapToGlobal(pos))
        else:
            #TODO
            pass

    def on_list_customContextMenuRequested(self, pos):
        selfiles = [self.proxy.mapToSource(x) for x in
                    self.list.selectionModel().selectedIndexes()]

        if self.readonly:
            self.contextMenuRequested.emit(selfiles,
                                           self.list.mapToGlobal(pos))
        else:
            #TODO
            pass

    def viewDoubleClicked(self, idx):
        if not idx.isValid():
            return

        f = self.listmodel.fileByIndex(self.proxy.mapToSource(idx))
        if f.isDirectory:
            if self.staticpath:
                self.fileDoubleClicked.emit(f)
            else:
                self.listmodel.path = joinpath(self.path, f.name)
        else:
            if self.readonly:
                self.fileDoubleClicked.emit(f)
            else:
                self.downloadFiles([f])


class FileCollisionAction(object):
    overwrite = 1
    resume = 2
    skip = 4
    toall = 8


class FileCollisionDialog(QDialog, pytson.Translatable):
    """

    """
    @classmethod
    def getAction(cls, localfile, remotefile, isdownload, multi, parent=None):
        """

        """
        dlg = cls(localfile, remotefile, isdownload, multi, parent)
        return dlg.exec_()

    def __init__(self, localfile, remotefile, isdownload, multi, parent=None):
        """

        """
        super(QDialog, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

        try:
            setupUi(self, pytson.getPluginPath("ressources",
                                               "filecollision.ui"))
        except Exception as e:
            self.delete()
            raise e

        if not multi:
            self.multiButton.setVisible(False)
            self.skipallButton.setVisible(False)

        locsize = os.path.getsize(localfile)
        if locsize == remotefile.size:
            self.resumeButton.hide()

            self.actionLabel.text = self._tr("Do you want to overwrite the "
                                             "existing file")
        else:
            self.actionLabel.text = self._tr("Do you want to overwrite or "
                                             "resume the existing file")

        self.filenameLabel.text = "<b>%s</b>" % remotefile.name

        datefmt = pytson.tr("filetransfer", "%Y-%m-%d %H:%M:%S")
        locdate = datetime.fromtimestamp(os.path.getmtime(localfile))
        filefmt = "Size: <b>%s</b><br />Date: <b>%s</b>"

        locstr = filefmt % (bytesToStr(locsize), locdate.strftime(datefmt))
        remstr = filefmt % (bytesToStr(remotefile.size),
                            remotefile.datetime.strftime(datefmt))

        if isdownload:
            self.existingLabel.text = locstr
            self.newLabel.text = remstr
        else:
            self.existingLabel.text = remstr
            self.newLabel.text = locstr

    def on_overwriteButton_clicked(self):
        ret = FileCollisionAction.overwrite
        if self.multiButton.isChecked():
            ret = ret | FileCollisionAction.toall

        self.done(ret)

    def on_resumeButton_clicked(self):
        ret = FileCollisionAction.resume
        if self.multiButton.isChecked():
            ret = ret | FileCollisionAction.toall

        self.done(ret)

    def on_skipButton_clicked(self):
        ret = FileCollisionAction.skip
        if self.multiButton.isChecked():
            ret = ret | FileCollisionAction.toall

        self.done(ret)

    def on_skipallButton_clicked(self):
        self.done(FileCollisionAction.skip | FileCollisionAction.toall)

    def on_cancelButton_clicked(self):
        self.done(0)


class FileTransfer(object):
    """

    """
    pass


class FileTransferModel(QAbstractItemModel):
    """

    """
    pass


class FileTransferDelegate(QStyledItemDelegate):
    """

    """
    pass


class FileTransferDialog(QDialog):
    """

    """
    def __init__(self, schid, cid, password, parent=None):
        super(QDialog, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

        try:
            setupUi(self, pytson.getPluginPath("ressources",
                                               "filetransfer.ui"))
        except Exception as e:
            self.delete()
            raise e

        self.resize(770, 250)

    def on_closeButton_clicked(self):
        self.close()

    def on_cleanupButton_clicked(self):
        pass

    def addUpload(self, path, localfile, overwrite, resume):
        """

        """
        pass

    def addDownloads(self, files):
        pass
