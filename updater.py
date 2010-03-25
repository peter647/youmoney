# coding: utf-8
import os, sys
import urllib, urlparse, httplib
import socket, urllib2, time
import shutil, zipfile
import traceback, md5
import version
import wx
from ui import logfile, config, i18n

home  = os.path.dirname(os.path.abspath(sys.argv[0]))
cf = config.Configure()
langdir = os.path.join(home, 'lang')
try:
    i18n.install(langdir, [cf['lang']])
except:
    i18n.install(langdir, ['en_US'])
    cf['lang'] = 'en_US'
    cf.dump()


class BackupError (Exception):
    pass

class InstallError (Exception):
    pass


def sumfile(filename):
    m = md5.new()
    fobj = open(filename, 'r')
    while True:
        d = fobj.read(8086)
        if not d:
            break
        m.update(d)
    fobj.close()
    return m.hexdigest()

class Downloader:
    def __init__(self, url, savepath, callback):
        self.url   = url
        self.local = savepath
        self.localsize = 0
        self.callback = callback
        
        if os.path.isfile(savepath):
            self.localsize = os.path.getsize(savepath)

        parts = urlparse.urlsplit(self.url)
        self.host = parts[1]
        self.relurl = parts[2]

        self.h = None

    def getheader(self, size=0):        
        if self.h:
            self.h.close()

        self.h = httplib.HTTP()
        #self.h.set_debuglevel(1)
        self.h.connect(self.host)
        self.h.putrequest('GET', self.relurl)
        self.h.putheader('Host', self.host)
        self.h.putheader('User-Agent', 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)')
        self.h.putheader('Accept', '*/*')
        self.h.putheader('Accept-Language', 'zh-cn')
        self.h.putheader('Connection', 'Keep-Alive')

        if size > 0:
            self.h.putheader('Range', 'bytes=%d-' % (size))

        self.h.endheaders()
         
        return self.h.getreply()

    def getdata(self, length):
        logfile.info('length:', length)
        f = open(self.local, 'a+b')
        num = 0 
        bufsize = 8192
        try:     
            while True:
                leave = length - num
                if leave < bufsize:
                    bufsize = leave
                data = self.h.file.read(bufsize)
                if not data:
                    break
                num += len(data)
                f.write(data)
                logfile.info('download size:', num)
                rate = float(self.filesize - length + num) / self.filesize
                going, skip = self.callback.Update(200 + rate * 700, _('Download package') + '... %.2d%%' % (rate * 100))
                if not going:
                    f.close()
                    return
        except Exception, e:
            logfile.info(traceback.format_exc()) 

        f.close()

    def download(self):
        status, reason, headers = self.getheader(0)
        self.filesize = int(headers.getheader('Content-Length'))
        self.callback.Update(150, _('Package size') + ': ' + str(self.filesize))
        logfile.info('local size:', self.localsize, 'http size:', self.filesize)
        
        if self.filesize == self.localsize:
            return

        if self.localsize > self.filesize:
            self.localsize = 0
            os.remove(self.local)
            
        status, reason, headers = self.getheader(self.localsize)
        self.callback.Update(200, _('Download package') + ' ... 0%')
        self.getdata(self.filesize - self.localsize)


class Updater:
    def __init__(self, callback):
        self.home  = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.callback = callback 
        if sys.platform == 'win32':
            self.tmpdir = os.path.join(self.home, 'tmp')
        else:
            self.tmpdir = os.path.join(os.environ['HOME'], '.youmoney', 'tmp')

        if not os.path.isdir(self.tmpdir):
            os.mkdir(self.tmpdir)

        self.info = {}
        
        self.openinfo()

    def openinfo(self):
        socket.setdefaulttimeout = 30
        updatefile = ['http://www.pythonid.com/youmoney/update2.txt', 
                      'http://youmoney.googlecode.com/files/update2.txt']
        num = 0
        for url in updatefile:
            self.callback.Update(50 * num, _('Download update.txt') + '...')
            logfile.info('get:', url)
            try:
                op = urllib2.urlopen(url)
                lines = op.readlines()
            except:
                logfile.info(traceback.format_exc())
                num += 1
                continue
        
            logfile.info(lines)

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    continue
                
                parts = line.split('\t')
                self.info[parts[0]] = parts[1]
             
            return
        
        raise IOError, 'get update.txt error!'
        self.callback.Update(100)

    def download(self):
        verstr = self.info['version']
        if int(version.VERSION.replace('.','')) >= int(verstr.replace('.', '')):
            logfile.info('not need update:', version.VERSION, verstr)
            return

        if sys.platform == 'darwin':
            logfile.info('auto update not support Mac OS X.')
            return

        prefix = 'http://youmoney.googlecode.com/files/'
        noinstallfile = prefix + 'YouMoney-noinstall-%s.zip' % (verstr)
        srcfile = prefix + 'YouMoney-src-%s.zip' % (verstr)

        srcmainfile = os.path.join(self.home, 'youmoney.py')
        fileurl = srcfile
        if os.path.isfile(srcmainfile):
            if sys.platform.startswith('linux') and self.home.startswith('/usr/share'):
                logfile.info('Linux rpm and deb install not support auto update')
                return
            fileurl = srcfile
        else:     
            if sys.platform == 'win32':
                exe = os.path.join(self.home, 'youmoney.exe')
                if os.path.isfile(exe):
                    fileurl = noinstallfile
                else:
                    fileurl = srcfile
            elif sys.platform == 'darwin':
                logfile.info('Mac OS X not support binary auto update.')
                return
            elif sys.platform.startswith('linux'):
                fileurl = srcfile
        
        filepath = os.path.join(self.tmpdir, os.path.basename(fileurl))
        self.path = filepath
        logfile.info('try download %s' % fileurl)
        logfile.info('save:', filepath)
        
        count = 3
        while count > 0: 
            try:
                dw = Downloader(fileurl, filepath, self.callback)
                dw.download()
            except:
                logfile.info(traceback.format_exc())
                count -= 1
                continue 
            break
        
        self.callback.Update(900, _('Validate package') + '...')
        size = os.path.getsize(filepath)
        if dw.filesize > size:
            return

        md5str = sumfile(filepath)
        name = os.path.basename(fileurl)

        if md5str == self.info[name]:
            logfile.info('file md5 check ok!')
            return filepath
        elif filesize >= dw.filesize:
            logfile.info('file md5 check failed. remove')
            os.remove(filepath)
            return
    
    def install(self, filename):
        #self.backup()
        issrc = False
        if filename.find('src') > 0:
            issrc = True

        f = zipfile.ZipFile(filename, 'r')
        for info in f.infolist():
            if info.file_size == 0:
                continue
            filepath = info.filename
            if not issrc and filepath.find('/.hg/') > 0:
                continue
            pos = filepath.find('/')
            newpath = os.path.join(self.home, filepath[pos+1:].replace('/', os.sep))
            newdir = os.path.dirname(newpath)

            if not os.path.isdir(newdir):
                os.mkdirs(newdir)

            newf = open(newpath, 'wb')
            newf.write(f.read(filepath))
            newf.close()

            logfile.info('copy:', info.filename, 'to:', newpath)
        f.close()

    def backup(self):
        backdir = os.path.join(self.home, 'tmp', 'backup') 
        if os.path.isdir(backdir):
            shutil.rmtree(backdir)

        os.mkdir(backdir)
        
        allfiles = []
        
        for topdir in os.listdir(self.home):
            logfile.info('topdir:', topdir)
            if topdir in ['.hg', 'tmp'] or topdir.endswith(('.swp', '.log')):
                continue
            toppath = os.path.join(self.home, topdir)
            if os.path.isdir(toppath):
                logfile.info('walk:', toppath)
                for root,dirs,files in os.walk(toppath):
                    for fname in files:
                        logfile.info('filename:', fname)
                        fpath = os.path.join(root, fname)
                        if fpath.endswith('.swp'):
                            continue
                        newpath = os.path.join(self.home, 'tmp', 'backup', fpath[len(self.home):].lstrip(os.sep))
                        newdir = os.path.dirname(newpath)
                        if not os.path.isdir(newdir):
                            os.makedirs(newdir)
                        shutil.copyfile(fpath, newpath)
                        allfiles.append(fpath)
                        logfile.info('copy:', fpath, newpath)
            else:
                newpath = os.path.join(self.home, 'tmp', 'backup', toppath[len(self.home):].lstrip(os.sep))
                newdir = os.path.dirname(newpath)
                if not os.path.isdir(newdir):
                    os.makedirs(newdir)
                shutil.copyfile(toppath, newpath)
                allfiles.append(toppath)
                logfile.info('copy:', toppath, newpath)
 
        for fname in allfiles:
            logfile.info('remove file:', fname)
            try:
                os.remove(fname)
            except:
                newname = fname + '.backup.' + str(time.time())
                logfile.info('rename:', newname)
                os.rename(fname, newname)
         

def test():
    verstr = sys.argv[1]
    home  = os.path.dirname(os.path.abspath(sys.argv[0]))
    logname = os.path.join(home, 'youmoney.update.log')
    #logfile.install(logname)
    logfile.install('stdout')

    up = Updater()
    try:
        filepath = up.download(verstr)
        if filepath:
            up.backup()
            up.install(filepath)
            os.remove(filepath)
    except:
        logfile.info(traceback.format_exc())

class UpdaterApp (wx.App):
    def __init__(self):
        wx.App.__init__(self, 0)

    def OnInit(self):
        max = 1000
        dlg = wx.ProgressDialog(_("YouMoney Updater"), _("Updating") + "...",
                               maximum = max,parent=None,
                               style = wx.PD_CAN_ABORT| wx.PD_APP_MODAL
                                | wx.PD_ELAPSED_TIME| wx.PD_REMAINING_TIME)

        up = Updater(dlg)
        filepath = None
        try:
            dlg.Update(0, _('Updating') + '...')
            filepath = up.download()
            dlg.Update(950, _('Backup old data') + '...')
            if filepath:
                up.backup()
                up.install(filepath)

            os.remove(filepath)
        except:
            logfile.info(traceback.format_exc())

        if filepath:
            dlg.Update(1000, _('Update complete!'))
        else:
            going, skip = dlg.Update(999)
            if going:
                dlg.Update(1000, _('Update failed!'))
            else:
                dlg.Update(1000, _('Update cancled!'))
        dlg.Destroy()
         
        return True


def main():
    logname = os.path.join(home, 'youmoney.update.log')
    logfile.install(logname)
    #logfile.install('stdout')

    app = UpdaterApp()
    app.MainLoop()


if __name__ == '__main__':
    main()




