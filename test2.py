from filesystem import *



# s = Shell()
# data, error = s.exec(b'ls /sdcard/xender -pRhs')
# data = data.decode()
data = open('test.txt', 'rb').read().decode()

fo = FileSystem(data=data)

audio = fo.get_folder('audio')

print(audio.path)
# print(fo.folders)













