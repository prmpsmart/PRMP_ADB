from prmp_lib.prmp_miscs.prmp_images import *
from prmp_lib.prmp_miscs.prmp_setup import *
# import os, gui, shutil

# imgs = ['folder', 'mp3', 'mp4', 'jpg', 'png', 'pdf', 'doc', 'zip', 'docx', 'xls', 'xlsx', 'py', 'pyc', 'dll', 'jpeg', 'hlp', 'gif', 'gif2', 'application', 'cached', 'case', 'file_s', 'generic', 'hide', 'match', 'melted', 'path', 'reload', 'root_d', 'search', 'show', 'usb', 'pull', 'push']

# # print(imgs)
# for a in imgs:
#     img = gui.images[a]
#     shutil.move(img, 'needed')

# PRMP_Images.images_into_py(folder='needed', pyfile='adb_compile/adb_images.py', space=3, add_all=1, prefix='ADB', all_files=1)
PRMP_Setup('build_ext', scripts=['adb/prmp_adb.py']).build()
# PRMP_Setup('pyinstaller', scripts=['adb/adb.py'], console=0, name='PRMP_ADB').build()



