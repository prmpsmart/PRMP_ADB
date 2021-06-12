
import os, subprocess, shlex, threading, time, io, itertools

from prmp_gui import *
from prmp_miscs import *
from adb_images import ADB_IMAGES


DEFAULT_PATH = '/storage/emulated'
DEFAULT_DB = 'android_datas.db'

ADB_EXE = r'adb.exe'

def check_assets():
    name = lambda p: os.path.splitext(p)[0]
    assets = ['adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'application.ico', 'generic.ico', 'melted.ico']
    adb, ico = assets[:3], assets[3:]

    for a in adb:
        if not os.path.exists(a):
            vv = PRMP_ADB32[name(a)]
            f = PRMP_File(a, b64=vv['data'])
            f.save()

    for a in ico:
        if not os.path.exists(a):
            data = ADB_IMAGES['ico'][name(a)]
            f = PRMP_File(a, b64=data)
            f.save()

check_assets()

class ADB_Error(Exception): ...


class Process:
    last_error = ''
    
    def __init__(self, process, quiet=False):
        self.data = self.stdout = process.stdout.read()
        self.error = self.stderr = process.stderr.read()

        self.data_error = self.data, self.error

        if self.stderr and not self.stdout and not quiet:
            Process.last_error = self.stderr
            raise ADB_Error(self.stderr)


class Command:

    @classmethod
    def _exec(cls, args='', **kwargs):
        if args:
            if isinstance(args, str): args = shlex.split(args)
            # print(args)
        
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, **kwargs)
        return process

    @classmethod
    def exec(cls, args='', quiet=False,  **kwargs): return Process(cls._exec(args, **kwargs), quiet)


class ADB:
    sub_command = ''

    @classmethod
    def _exec(cls, args='', **kwargs):
        if args:
            if isinstance(args, str): args = shlex.split(args)
            if cls.sub_command: args = [cls.sub_command, *args]
            args = [ADB_EXE, *args]
        else: args = [ADB_EXE]
        
        cls.process =  process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, **kwargs)
        return process


    @classmethod
    def exec(cls, args='', quiet=False, **kwargs): return Process(cls._exec(args, **kwargs), quiet)


class File_Transfer(ADB):

    def __init__(self, src, dest):
        self.src = str(src)
        self.dest = str(dest)
        super().__init__()
    
    def exec(self, **kwargs): return super().exec([self.src, self.dest], **kwargs)


class Pull(File_Transfer): sub_command = 'pull'


class Push(File_Transfer): sub_command = 'push'


class Shell(ADB): sub_command = 'shell'


class Base:
    def get(self, name, default=None): return getattr(self, name, default)

    @property
    def subs(self): return  []

    def __len__(self):
        if self.subs: return len(self[:])
        return 0
    
    def __eq__(self, other):
        if not other: return False
        if isinstance(other, str): return (str(other) == self.name)
        return (other.name == self.name) and (other.parent == self.parent)
    
    @property
    def className(self): return self.__class__.__name__

    @property
    def name(self): return f'{self.className}({self.basename}, size={self.size})'

    def __repr__(self): return f'<{self.name}>'
    
    def __str__(self): return self.path

    def __bool__(self): return True

    def __hash__(self): return hash((self.name, self.parent))

    def slash(self, path):
        if path.startswith('/'): path = path[1:]
        if path.endswith('/'): path = path[:-1]
        return path
    
    @property
    def basename(self): return os.path.basename(self.path)
    
    def download(self, dest):
        proc = Pull(self.path, dest).exec()
        return proc
    
    def float_size(self, size):
        if isinstance(size, bytes): size = size.decode()
        size = str(size)
        if not size: size = '0'
        
        byte = 1024
        si_dt = {'K': byte, 'M': byte**2, 'G': byte**3}
        si = size[-1]

        if si in si_dt:
            dt = si_dt[si]
            dat = float(size[:-1]) * dt
        else: dat = float(size)/2 * byte
        
        return dat
    
    def format_size(self, size):
        byte = 1024
        si_dt = {'K': byte, 'M': byte**2, 'G': byte**3}
        size = float(size)

        if size >= si_dt['G']: dat = f"{size/si_dt['G']:.02f} G"
        elif size >= si_dt['M']: dat = f"{size/si_dt['M']:.02f} M"
        elif size >= si_dt['K']: dat = f"{size/si_dt['K']:.02f} K"
        else: dat = f"{size:.02f} B"

        return dat

    def pull(self, dest):
        proc = Pull(self.path, dest).exec()
        return proc.data_error


class File(Base):
    file = 1

    @property
    def subs(self): return []

    def __init__(self, parent, path, size):
        self.parent = parent
        self.path = path
        self.full_size = self.float_size(size)
        self.size = self.format_size(self.full_size)
    
    @property
    def ext(self): return os.path.splitext(self.basename)[1][1:]


class Folder(Base):
    file = 0

    def __init__(self, parent=None, path=''):
        self.parent = parent
        self.path = path
        self.all_folders = self.folders = {}
        self.files = {}

    def get_parent_folder(self, name):
        if isinstance(name, bytes): name = name.decode()
        name = name.lower()

        parent = os.path.dirname(str(name))
        # print(f'{name} <> "{parent}" <> {[self.path, "/storage"]}')

        if parent in [self.path, '/storage']: return self
        elif parent in self.all_folders: return self.all_folders.get(parent)
        # else: raise ValueError(f'{parent} is not in this filesystem')

    def add_folder(self, path):
        folder = Folder(self, path)
        self.folders[path.lower()] = folder
        return folder

    def add_file(self, path, size='0'):
        file = File(self, path, size)
        self.files[path.lower()] = file
        return file
    
    def create_file(self, path, size='0'):
        parent = self.get_parent_folder(path)
        if parent and parent.path != self.path: file = parent.create_file(path, size)
        else: file = self.add_file(path, size)

        return file
    
    def create_folder(self, name):
        parent = self.get_parent_folder(name)
        if parent and parent.path != self.path: folder = parent.create_folder(name)
        else: folder = self.add_folder(name)

        return folder
    
    @property
    def folder_s(self): return list(self.folders.values())
    
    @property
    def subs(self): return self[:]

    @property
    def file_s(self): return list(self.files.values())
    
    def __getitem__(self, item):
        items = [*self.folders.values(), *self.files.values()]
        return items[item]
        
    def get_folder(self, folder):
        folder = f'{self.path}/{self.slash(folder)}'.lower()
        return self.folders.get(folder)
    
    @property
    def folders_count(self):
        count = len(self.folder_s)
        for folder in self.folder_s: count += folder.folders_count
        return count

    @property
    def files_count(self):
        count = len(self.file_s)
        for folder in self.folder_s: count += folder.files_count
        return count
    
    @property
    def full_size(self):
        size = sum([float(file.full_size) for file in self.file_s])
        for folder in self.folder_s: size += folder.full_size
        return size
    
    @property
    def size(self): return self.format_size(self.full_size)


class Root_Directory(Folder):
    path = '/'

    def __init__(self, device):
        super().__init__(device, self.path)
        self.device = device
        
        self.all_folders = {}
        self.all_files = {}
        
        if device.filesystems:
            strs_fs = [fs.mounted_on for fs in device.filesystems[-2:]]
            if strs_fs[0] != DEFAULT_PATH: strs_fs = ['/sdcard']

            for fs in strs_fs: self.load(fs)

    @property
    def basename(self): return self.path

    def create_file(self, path, size='0'):
        file = super().create_file(path, size)
        self.all_files[file.path.lower()] = file
        return file
    
    def create_folder(self, path):
        folder = super().create_folder(path)
        self.all_folders[folder.path.lower()] = folder
        return folder

    def load(self, path):
        if path == DEFAULT_PATH: path = '/sdcard'

        data, error = Shell.exec(f'ls {path} -pRhs', 1).data_error
        data = data.decode()
        # data = path

        if not data: raise ADB_Error(f'An error must have occured, no data to parse.', error)

        lines = data.splitlines()
        last_folder = ''

        for line in lines:
            if line:
                if line.endswith(':'):
                    last_folder = self.create_folder(line[:-1]).path

                if 'total ' in line or line.endswith('/') or line.endswith(':'): continue

                line = line.lstrip(' ')
                a = line.split(' ', 1)
                a.reverse()

                file_path = f'{last_folder}/{a[0]}'
                a[0] = file_path

                # if last_folder:
                #     file = last_folder.add_file(a[0], a[1])
                #     self.all_files[file.path] = file
                self.create_file(*a)


class FileSystem:
    def __str__(self): return self.mounted_on
    def __repr__(self): return f'<{self.name}>'
    
    @property
    def subs(self): return []
    @property
    def name(self): return f'FileSystem({self.mounted_on})'

    def __init__(self, data, type=1):
        self.type = type
        if self.type == 1: self.path, self.total, self.used, self.available, self.percentage_use, self.mounted_on = data.split()
        
        elif self.type == 2: self.path, self.total, self.used, self.available = data.split()


        self.used = Base.float_size(self, self.used)
        self.available = Base.float_size(self, self.available)
        self.total = Base.float_size(self, self.total)

    @property
    def used_size(self): return Base.format_size(self, self.used)
    @property
    def available_size(self): return Base.format_size(self, self.available)
    @property
    def total_size(self): return Base.format_size(self, self.total)


class Device:
    def get(self, name, default=None): return getattr(self, name, default)
    
    def _split(self, data): return data.split(':')[1]
    def _splits(self, *datas): return [self._split(data) for data in datas]

    def _split2(self, data): return data.split(': [')[1][:-1]
    def _splits2(self, *datas): return [self._split2(data) for data in datas]
    subs = []

    def __init__(self, data, dummy=False):
        self.dummy = dummy
        self.root_directory = None

        self.unique, _, self.product, self.model, self.name, self.transport_id = data.split()

        self.product, self.name, self.model, self.transport_id = self._splits(self.product, self.name, self.model, self.transport_id)
        
        self.brand = self.manufacturer = ''
        self.filesystems = []

        self.load()
    
    def load(self):
        if not self.dummy:
            ADB.exec('root')
            self.getprop()
            self.df()
            self.root_directory = Root_Directory(self)

    def getprop(self):
        process = Shell.exec('getprop')
        data = process.data.decode()
        for line in data.splitlines():
            if 'ro.product.brand' in line: self.brand = self._split2(line)
            elif 'ro.product.manufacturer' in line: self.manufacturer = self._split2(line)

    def df(self):
        process = Shell.exec('df')
        data = process.data.decode()
        header, *datas = data.splitlines()
        header = header.split()
        
        if header == 'Filesystem                                                     1K-blocks    Used Available Use% Mounted on'.split(): type = 1
        elif header == 'Filesystem               Size     Used     Free   Blksize'.split(): type = 2
        
        for data in datas:
            if data and 'Permission denied' not in data:
                filesystem = FileSystem(data, type)
                self.filesystems.append(filesystem)
    
    def __str__(self): return f'Device{self.name, self.unique}'
    def __repr__(self): return f'{self}>'


class Devices:
    devices = {}
    
    @classmethod
    def list(cls): return list(cls.devices.values())

    @classmethod
    def add_device(cls, device):
        if device.dummy:
            device.dummy = False
            device.load()
        Devices.devices[device.unique] = device

    @classmethod
    def create_devices(cls, dummy=False):
        process = ADB.exec('devices -l')
        data = process.data.decode()
        data = data.strip()
        _, *datas = data.splitlines()
        dummies = []

        if len(datas) == 0: raise ADB_Error('No device is connected')
        
        for data in datas:
            if 'unauthorized' in data: raise ADB_Error('''This adb server's $ADB_VENDOR_KEYS is not set
Try 'adb kill-server' if that seems wrong.
Otherwise check for a confirmation dialog on your device.
List of devices attached''')
            elif 'offline' in data: raise ADB_Error('Device is cuurently offline, please detach and reattach the USB cable on the device.')
            
            else:
                device = Device(data, dummy)
                if not dummy: cls.devices[device.unique] = device
                else: dummies.append(device)
        
        if dummies: return dummies


def load():
    f = PRMP_File(DEFAULT_DB)
    try:
        obj = f.loadObj()
        Devices.devices.update(obj)
        return obj
    except: ...


def save(create=0):
    load()

    if create: Devices.create_devices()

    obj = Devices.devices

    try: os.remove(DEFAULT_DB)
    except: ...

    f = PRMP_File(DEFAULT_DB)
    f.saveObj(obj)
    f.save()

load()
image_size = (24, 24)
images = dict(**ADB_IMAGES['png'])
images.update(ADB_IMAGES['gif'])
images.update(ADB_IMAGES['ico'])




class Gui(PRMP_MainWindow):
    images_images = {}
    loaded = 0
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        
        if not Gui.loaded:
            imgs = ['folder', 'mp3', 'mp4', 'jpg', 'png', 'pdf', 'doc', 'zip', 'docx', 'xls', 'xlsx', 'py', 'pyc', 'dll', 'jpeg', 'hlp', 'gif', 'gif2']
            imgs += ['cached', 'case', 'file_s', 'hide', 'match', 'path', 'reload', 'root_d', 'search', 'show', 'usb', 'pull', 'push', 'melted', 'generic']
            a = 22
                
            for img in imgs: Gui.images_images[img] = PRMP_Image(img, b64=images[img], for_tk=1, resize=(a, a))

            Gui.loaded = 1


class ErrorBox(PRMP_MsgBox):

    def __init__(self, master, geo=(300, 200), res=20, compound='left', yes={'text': 'Ok'}, no={}, **kwargs):
        super().__init__(master, _type='error', prmpIcon='melted.ico', tkIcon='melted.ico', geo=geo, resize=(0, 0), yes=dict(compound=compound, image=PRMP_Image('ok', b64=images['ok'], for_tk=1, resize=(res, res)), **yes), no=dict(text='No', compound=compound, image=PRMP_Image('cancel', b64=images['cancel'], for_tk=1, resize=(res, res)), **no), **kwargs)


class IconWidget:
    _count = 0
    WidgetClass = None

    def __init__(self, master, text='', image='', relief='flat', tip=1, resize=(25, 25), compound='none', new=True, imgKw={}, **kwargs):
        self.WidgetClass.__init__(self, master, text=text, image=PRMP_Image(image, for_tk=1, resize=resize, name=f'IconButton._count{IconButton._count}', **imgKw) if new else image, tip=tip, compound=compound, relief=relief, **kwargs)

        IconButton._count += 1
        if IconButton._count > 200: IconButton._count = 0

    def _paint(self):
        super()._paint()
        self.configure(foreground=PRMP_Theme.DEFAULT_FOREGROUND_COLOR, background=PRMP_Theme.DEFAULT_BACKGROUND_COLOR)


class IconButton(IconWidget, Button):
    WidgetClass = Button
    def __init__(self, master, **kwargs): IconWidget.__init__(self, master, **kwargs)


class IconCheckbutton(IconWidget, Checkbutton):
    WidgetClass = Checkbutton
    def __init__(self, master, **kwargs): IconWidget.__init__(self, master, **kwargs)


class EnterPath(PRMP_Dialog):
    def __init__(self, master=None, default='', text='', **kwargs):
        self.default = default
        self.text = text
        super().__init__(master, tooltype=1, asb=0, atb=0, geo=(300, 200), tm=1, be=1, **kwargs)

    def _setupDialog(self):
        font = dict(family='Times New Roman', weight='bold', size=23)
        Label(self.cont, text=self.text, relief='flat', anchor='w', font=font.copy(), place=dict(relx=.05, rely=.05, relw=.9, relh=.33), image=PRMP_Image('path', b64=images['path'], for_tk=1, resize=(50, 50)), compound='right')
        
        font['size'] = 15
        self.path = Entry(self.cont, font=font.copy(), place=dict(relx=.05, rely=.38, relw=.9, relh=.2))
        self.path.set(self.default)
        self.path.focus()

        IconButton(self.cont, text='CANCEL', place=dict(relx=.52, rely=.75, relw=.2, relh=.24), relief='flat', command=self.destroy , image='cancel.png', imgKw=dict(b64=images['cancel']), resize=(40, 40))

        IconButton(self.cont, text='OK', place=dict(relx=.78, rely=.75, relw=.2, relh=.24), relief='flat', command=self.actionn, image='ok.png', imgKw=dict(b64=images['ok']), resize=(40, 40))

        self.bind('<Return>', self.actionn)
        self.addResultsWidgets(['path'])

    
    def save(self): ...
    
    def action(self): ...

    def dest(self): self.after(100, self.destroySelf)
    
    def actionn(self, e=0):
        self.processInput()
        self.destroyDialog()


class SearchPath(EnterPath):

    def _setupDialog(self):
        super()._setupDialog()
        self.case = IconCheckbutton(self.cont, text='Case', place=dict(relx=.03, rely=.78, relw=.2, relh=.16), image='case', new=False)
        self.match = IconCheckbutton(self.cont, text='Match', place=dict(relx=.26, rely=.78, relw=.2, relh=.16), image='match', new=False)
        self.addResultsWidgets(['case', 'match'])


class FolderView(Frame):

    name, size, type, files, folders = dict(text='Name', attr='basename', width=160), dict(text='Size'), dict(text='Type', attr='ext'), dict(text='Files', attr='files_count', width=10), dict(text='Folders', attr='folders_count', width=10)
    _number = 0

    def __init__(self, master, command=None, **kwargs):
        super().__init__(master, **kwargs)
        FolderView._number += 1
        self.device = master.device
        self.columns = 4
        self.command = command
        self.number = FolderView._number
        

        self.folder_name = Button(self, text='Folder View', place=dict(relx=0, rely=0, relh=.05, relw=1), command=lambda: EnterPath(self, callback=self.receiveJump, default=self.folder_name.get(), text='Jump to path   '), font=dict(family='Times New Roman', weight='bold', size=15))

        self.view = Hierachy(self, place=dict(relx=0, rely=.05, relh=.95, relw=1), image_get=self.image_get)

        self.set_columns()
        self.view.tree.bind('<3>', self.contextMenu)
        self.view.tree.bind('<Double-1>', self.folderContextMenu)

        self.viewObjs = self.view.viewObjs
    
    def image_get(self, obj):
        if obj.file: ext = obj.ext.lower()
        else: ext = 'folder'

        img = Gui.images_images.get(ext, 'hlp')
        return img
    
    def sendCommand(self):
        if self.command: self.command(self.number, self.view.selected())
    
    def receiveJump(self, path):
        path = path.get('path')
        if path:
            path = path.lower()
            root_d = self.device.root_directory

            if len(root_d) >= self.number:
                root = root_d[self.number-1]
                
                folder = root_d.all_folders.get(path)
                if folder:
                    if folder.path.startswith(root.path):
                        self.folder_name.config(text=path)
                        self.viewObjs(folder)
                    else: folder = None
    
                if not folder: ErrorBox(self, title='Path Error', msg=f'The provided path: {path} is invalid.')

    def contextMenu(self, event=None): ...

    def folderContextMenu(self, event=None):
        selected = self.view.tree.selected()
        if selected: self.folder_name.config(text=selected.path)

    def set_columns(self, size=1, type=1, files=0, folders=0):
        columns = [self.name]
        if size: columns.append(self.size)
        if type: columns.append(self.type)
        if files: columns.append(self.files)
        if folders: columns.append(self.folders)

        self.columns = len(columns)
        self.view.setColumns(columns)

    # def openCores(self, obj):
    #     print(obj)


class FolderViews(SFrame):

    def __init__(self, master, device=None, fds=(), **kwargs):
        super().__init__(master, **kwargs)

        self.device = device
        self.current_view = None
        self.view1 = FolderView(self, place=dict(x=0, y=0, relh=1, relw=.5))
        self.view2 = FolderView(self, place=dict(relx=.5, y=0, relh=1, relw=.5))

        views = [self.view1, self.view2]

        rd = fds or device.root_directory

        for folder, view in itertools.zip_longest(rd, views):
            if view:
                view.bind('<FocusIn>', self.set_current_view)
                if folder: view.viewObjs(folder)
    
    def set_current_view(self, event): self.current_view = event.widget
    
    def place_view(self): ...


class FolderViews_Window(Gui):

    def __init__(self, master=None, title='', geo=(800, 600), device=None, fds=(), **kwargs):
        super().__init__(master, title=title, geo=geo, asb=0, resize=(1, 0), tw=1, tipping=1, be=1, **kwargs)
        self.cont['relief'] = 'flat'

        self.setPRMPIcon('generic', b64=images['generic'])
        self.setTkIcon('generic.ico')
        
        x, y = geo

        frame = SFrame(self.cont, place=dict(x=2, y=y-82, h=48, w=x-5), relief='flat')
        resize = 40, 40

        self.folder = IconCheckbutton(frame, config=dict(text='Folder?'), place=dict(x=420, y=4, h=44, w=70), relief='flat', image='folder', imgKw=dict(b64=images['folder']), hl=1, resize=resize)

        self.path = LabelEntry(frame, topKwargs=dict(text='Path'), bottomKwargs=dict(_type='path', very=1, tipKwargs=dict(text='Double click for dialog window.')), place=dict(x=2, y=2, relh=.9, w=400), orient='h', longent=.3)
        self.path.B.bind('<Double-1>', lambda e: self.path.set(dialogFunc(path=1, folder=self.folder.get())))

        
        IconButton(frame, config=dict(text='Pull'), place=dict(x=500, y=4, h=44, w=70), image='pull', imgKw=dict(b64=images['pull']), hl=1, resize=(55, 55), command=lambda: self.action('pull'))
        
        IconButton(frame, config=dict(text='Push'), place=dict(x=580, y=4, h=44, w=70), image='push', imgKw=dict(b64=images['push']), hl=1, resize=resize, command=lambda: self.action('push'))
        
        self.views = FolderViews(self.cont, place=dict(relx=0, y=2, h=y-80, relw=1), relief='groove', device=device, fds=fds)

        if device and not fds: self.setTitle(f'{device.name}-{device.unique} Folders')

        self.topest.paint()
        # self._paint()
        if not master: self.mainloop()
    
    def get_fd(self):
        view = self.views.current_view
        if view:
            fd = view.view.selected()
            if fd: return fd
            else: ErrorBox(self, title='Selection Error', msg='Select atleast one file or folder!')
        else: ErrorBox(self, title='Focus Error', msg='Selected one view!')
    
    def _action(self, w):
        if not w: return

        if self.act == 'PULL': command = Pull; self.tuple.reverse()
        else: command = Push

        process = command(*self.tuple)
        self._processing(process)

    def _processing(self, process):
        process = process.exec(quiet=1)
        data, error = process.data_error
        # print(process.data_error)

        if error or b'adb: error' in data: ErrorBox(self, title=f'{self.act} Error', msg=error.decode() or data.decode())
        else: PRMP_MsgBox(self, title=f'{self.act} Successful', msg=f'{data.decode()}\n from\n "{self.tuple[0]}"\n -->> \n"{self.tuple[1]}"', yes=dict(compound='left', image=PRMP_Image('ok', b64=images['ok'], for_tk=1, resize=(24, 24)), text='Ok'), geo=(400, 300), delay=0)

    
    def action(self, act):
        if not self.path.verify(): ErrorBox(self, title='Path Error', msg='Invalid Path Error!')

        computer_path = self.path.get()
        mobile_path = self.get_fd()
        self.tuple = [computer_path, mobile_path]

        self.act = act = act.upper()
        other = 'DOWNLOAD' if act == 'PULL' else 'UPLOAD'
        res = 24
        PRMP_MsgBox(self, title=act.title(), msg=f'Are you sure to {act}({other}) {mobile_path} into {computer_path}?', callback=self._action, ask=1, yes=dict(compound='left', image=PRMP_Image('ok', b64=images['ok'], for_tk=1, resize=(res, res)), text='Yes'), no=dict(text='No', compound='left', image=PRMP_Image('cancel', b64=images['cancel'], for_tk=1, resize=(res, res))), geo=(400, 300))


class DeviceFileSystems(Gui):

    def __init__(self, master=None, geo=(1150, 350), device=None, **kwargs):
        super().__init__(master, title=f'{device.name} FileSystems', geo=geo, asb=0, resize=(0, 0), tw=1, tm=1, **kwargs)


        self.setPRMPIcon('application', b64=images['application'])
        
        self.setTkIcon(images['application'])

        self.tree = Hierachy(self.cont, place=dict(relx=0, rely=0, relw=1, relh=1), columns=[dict(text='Path', width=370), dict(text='Mounted on', attr='mounted_on', width=50), dict(text='Used', attr='used_size'), dict(text='Available', attr='available_size'), dict(text='Total', attr='total_size'), dict(text='Percentage used', attr='percentage_use', width=10)])

        self.tree.viewObjs(device.filesystems)


class DeviceProperty(PRMP_FillWidgets, LabelFrame):

    def __init__(self, master, device=None, **kwargs):
        LabelFrame.__init__(self, master, text='Choosen Device', **kwargs)
        PRMP_FillWidgets.__init__(self, device)

        self.name = LabelLabel(self, topKwargs=dict(text='Name', relief='flat'), place=dict(relx=0, rely=0, relh=.11, relw=1), orient='h', longent=.3, bottomKwargs=dict(anchor='e'))
        self.manufacturer = LabelLabel(self, topKwargs=dict(text='Manufacturer', relief='flat'), place=dict(relx=0, rely=.11, relh=.11, relw=1), orient='h', longent=.4, bottomKwargs=dict(anchor='e'))
        self.brand = LabelLabel(self, topKwargs=dict(text='Brand', relief='flat'), place=dict(relx=0, rely=.22, relh=.11, relw=1), orient='h', longent=.3, bottomKwargs=dict(anchor='e'))
        self.model = LabelLabel(self, topKwargs=dict(text='Model', relief='flat'), place=dict(relx=0, rely=.33, relh=.11, relw=1), orient='h', longent=.3, bottomKwargs=dict(anchor='e'))
        self.product = LabelLabel(self, topKwargs=dict(text='Product', relief='flat'), place=dict(relx=0, rely=.44, relh=.11, relw=1), orient='h', longent=.3, bottomKwargs=dict(anchor='e'))
        self.unique = LabelLabel(self, topKwargs=dict(text='Unique', relief='flat'), place=dict(relx=0, rely=.55, relh=.11, relw=1), orient='h', longent=.3, bottomKwargs=dict(anchor='e'))
        self.transport_id = LabelLabel(self, topKwargs=dict(text='Transport ID', relief='flat'), place=dict(relx=0, rely=.66, relh=.11, relw=1), orient='h', longent=.35, bottomKwargs=dict(anchor='e'))

        IconButton(self, text='File Systems', place=dict(relx=0, rely=.78, relh=.1, relw=1), command=self.openFileS, image='file_s', compound='left', new=False, hl=1)
        IconButton(self, text='Root Directories', place=dict(relx=0, rely=.89, relh=.1, relw=1), command=self.openRootD, image='root_d', compound='left', new=False, hl=1)

        self.addResultsWidgets(['name', 'manufacturer', 'brand', 'model', 'product', 'unique', 'transport_id'])
        self.set(device)
    
    def openFileS(self):
        if self.values and not self.values.dummy: DeviceFileSystems(self, device=self.values)

    def openRootD(self):
        if self.values and not self.values.dummy: FolderViews_Window(self, device=self.values)


class DevicesView(Table):
    def __init__(self, master, title='', callback=None, image=None, **kwargs):
        super().__init__(master, title=title + ' Devices', titleH=30, treeKwargs=dict(columns=['Name', 'Model', 'Unique', ]), **kwargs)
        self.callback = callback
        self.title.config(relief='flat', image=image, compound='left')
        self.tree.tree.bind('<Double-1>', self.returnChoosen)

    def returnChoosen(self, event=None):
        selected = self.tree.tree.selected()
        self.callback(selected)


class Android_FileSystem(Gui):
    
    def __init__(self, master=None, themeIndex=8, geo=(800, 435), **kwargs):
        super().__init__(master, title='Android FileSystem', themeIndex=themeIndex, geo=geo, asb=0, resize=(0, 0), be=1, tipping=1, **kwargs)
        self.cont['relief'] = 'flat'
        self.root.save = self.save

        self.setPRMPIcon('cheer_android', b64=images['cheer_android'])
        self.setTkIcon('generic.ico')
        
        self.image = PRMP_ImageLabel(self.cont, place=dict(x=2, y=2, w=392, h=361), config=dict(relief='flat'), imageKwargs=dict(prmpImage='android_gif', b64=images['android_gif']), imgDelay=200)

        self.details = DeviceProperty(self.cont, place=dict(x=400, y=2, w=396, h=360), relief='flat')

        self.frame = Frame(self.cont)
        self.toggle = IconCheckbutton(self.frame, text='Show Devices', place=dict(relx=0, rely=0, relh=1, relw=.17), command=self.toggleDevices, compound='left', new=False)

        IconButton(self.frame, text='Search', place=dict(relx=.17, rely=0, relh=1, relw=.15), image='search', compound='left', command=self.pop_search, new=False, hl=1)
        
        IconButton(self.frame, text='Reload', place=dict(relx=.32, rely=0, relh=1, relw=.15), image='reload', compound='left', new=False, hl=1)
        
        IconButton(self.frame, text='Check Connection', place=dict(relx=.76, rely=0, relh=1, relw=.22), image='usb', command=lambda: self.check_connection(0), compound='left', new=False, hl=1)

        self.devices = LabelFrame(self.cont, text='Devices')

        self.cached_devices = DevicesView(self.devices, title='Cached', place=dict(relx=0, rely=0, relh=1, relw=.5), callback=self.details.set, image='cached')

        self.connected_devices = DevicesView(self.devices, title='Connected', place=dict(relx=.5, rely=0, relh=1, relw=.5), callback=self.details.set, image='usb')

        self.refresh_cached()

        threading.Thread(target=self.loadUp).start()

        self.toggleDevices()
        self.start()
    
    def pop_search(self):
        if self.details.values: SearchPath(self, callback=self.search_path, text='Search path   ')
        else: ErrorBox(self, title='Choose a device!', msg='You might wanna do yourself a favour by picking a device from the cached devices !')

    def search_path(self, res):
        device = self.details.values
        files = []
        folders = []


        path = res.get('path', '')
        case = res.get('case')
        match = res.get('match')

        if not path: return

        if not case: path = path.lower()
        
        root = device.root_directory
        alls = dict(**root.all_folders, **root.all_files)
        
        
        for ff, obj in alls.items():
            comp_path = obj.path if case else ff
            in_path = comp_path.split('/')[-1]

            if match: valid = path == in_path
            else: valid = path in in_path

            if valid:
                lis = files if obj.file else folders
                lis.append(obj)

        fds = folders, files
        FolderViews_Window(self, device=device, fds=fds, title=f'Search results for {path}')

    def loadUp(self):
        self.check_connection()
        
    def refresh_cached(self, p=0):
        self.cached_devices.viewObjs(Devices.list())
        if p: save()
    
    def check_connection(self, quiet=1):
            try:
                connecteds = Devices.create_devices(1)
                self.connected_devices.viewObjs(connecteds)
                conn = connecteds[0]
                if not self.details.values:
                    device = Devices.devices.get(conn.unique, conn)
                    self.details.set(device)

                if (len(connecteds) == 1) and quiet == 0:
                    Devices.add_device(conn)
                    self.refresh_cached(1)

            except ADB_Error as e:
                self.connected_devices.tree.clear()
                if not quiet: ErrorBox(self, title='An Error Occured.', msg=e, geo=(300, 250))
            except ValueError: ...
            
            if quiet: self.after(1000, self.check_connection)
    
    def toggleDevices(self):
        x, y = self.geo
        h = 265
        if self.toggle.get():
            self.frame.place(relx=0, y=h+100, h=35, relw=1)
            self.toggle.config(text='Hide Devices', image='hide')
            self.placeOnScreen(side=self.side, geometry=(x, y+h))
            y = self.height
            self.devices.place(relx=.002, y=y-h-35, h=h, relw=.996)

        else:
            self.frame.place(relx=0, y=y-70, h=35, relw=1)
            self.toggle.config(text='Show Devices', image='show')
            self.placeOnScreen(side=self.side, geometry=(x, y))
            self.devices.place_forget()

    def save(self): subprocess.check_output('wmic process where name="adb.exe" delete')


# save()
if __name__ == '__main__': Android_FileSystem()

