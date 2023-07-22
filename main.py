import configparser
import multiprocessing
import os
import re
import sys
import threading
import ctypes
import time
from ctypes import windll

import pyautogui
import winsound
from PIL import ImageGrab
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QButtonGroup, QRadioButton
from PyQt5.QtWidgets import QWidget, QGridLayout, QScrollArea, QFrame
from paddleocr import PaddleOCR
from pynput import keyboard
import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32ui
import logging

is_gpu = False  # 默认不开启GPU
is_show_not_find_window = True
window_size = None
INPUT_MOUSE = 0
MOUSEEVENTF_ABSOLUTE = 0x8000  # 使用绝对坐标
MOUSEEVENTF_MOVE = 0x0001  # 移动鼠标
MOUSEEVENTF_LEFTDOWN = 0x0002  # 按下左键
MOUSEEVENTF_LEFTUP = 0x0004  # 释放左键
logging.disable(logging.DEBUG)  # 关闭DEBUG日志的打印
logging.disable(logging.WARNING)  # 关闭WARNING日志的打印
# cap_win_name = "League of Legends (TM) Client"
# cap_win_name = "FolderView"

money_range = (813, 877, 131, 37)  # 金币所在位置

rect = (480, 1040, 1000, 30)  # 英雄所在区域

rect_image = (259, 871, 1230, 204)

cap_win_name = "League of Legends (TM) Client"

cv2_win_name = "win"
top_window_width = 300
# 调整图片尺寸
folder_path = "images/624"  # 替换为包含图片的文件夹路径
width = 190
height = 108
# 请求下来的图存储路径
save_p = "images/320"
# 读取的文件夹路径
rw_path = "images/120"
config = configparser.ConfigParser()
ini_file = '1bit.ini'
ocr = None
lol_hwnd = win32gui.FindWindow('RiotWindowClass', None)


def get_files():
    images_files = os.path.join(os.getcwd(), rw_path)
    files = os.listdir(images_files)
    images = []
    for f in files:
        if f.endswith('.png') or f.endswith('.jpg'):
            path = os.path.join(rw_path, f)  # 在文件名前面拼接路径
            decoded_file_name = decode_unicode_escape(path.encode('raw_unicode_escape').decode("utf-8"))
            images.append(decoded_file_name)

    # 按价格从小到大排序
    images = sorted(images, key=lambda x: extract_filename(x)[1])

    # 创建费用分类字典
    card_dict = {1: [], 2: [], 3: [], 4: [], 5: []}

    # 将卡片按费用分类
    for img in images:
        name, price = extract_filename(img)
        card_dict[price].append(img)
    return card_dict


# 定义结构体和常量
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class Input(ctypes.Structure):
    class Union(ctypes.Union):
        _fields_ = [("mi", MouseInput)]

    _fields_ = [("type", ctypes.c_ulong),
                ("union", Union)]


def grab_gpt_win(grab_rect=None, toColor=True):
    hwnd = win32gui.GetDesktopWindow()
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    screen_width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
    screen_height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
    x, y, w, h = grab_rect or (0, 0, screen_width, screen_height)
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    saveDC.BitBlt((0, 0), (w, h), mfcDC, (x, y), win32con.SRCCOPY)

    signed_ints_array = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(signed_ints_array, dtype="uint8")
    img.shape = (h, w, 4)
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    if toColor:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
    return img


# 加载user32.dll
user32 = ctypes.WinDLL("user32.dll")

# 定义SendInput函数
SendInput = ctypes.windll.user32.SendInput
SendInput.restype = ctypes.c_uint
SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(Input), ctypes.c_int]


def ht_move(x, y):
    long_position = win32api.MAKELONG(x, y)
    # 模拟鼠标按下
    win32api.SendMessage(lol_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position)
    # 模拟鼠标弹起
    win32api.SendMessage(lol_hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, long_position)


def qt_move(x, y):
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)


def ab_move(x, y):
    # 获取屏幕宽度和高度
    screen_width = ctypes.windll.user32.GetSystemMetrics(0)
    screen_height = ctypes.windll.user32.GetSystemMetrics(1)

    # 计算鼠标绝对位置坐标
    absolute_x = int(x / screen_width * 65535)
    absolute_y = int(y / screen_height * 65535)

    # 构造一个鼠标移动的Input结构体
    input_struct = Input()
    input_struct.type = INPUT_MOUSE
    input_struct.union.mi.dx = absolute_x
    input_struct.union.mi.dy = absolute_y
    input_struct.union.mi.dwFlags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE

    # 发送鼠标移动事件
    inputs = (Input * 1)(input_struct)
    SendInput(1, inputs, ctypes.sizeof(inputs[0]))


def left_click():
    # 构造一个按下左键的Input结构体
    input_struct_down = Input()
    input_struct_down.type = INPUT_MOUSE
    input_struct_down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN

    # 构造一个释放左键的Input结构体
    input_struct_up = Input()
    input_struct_up.type = INPUT_MOUSE
    input_struct_up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP

    # 发送鼠标左键按下事件
    inputs = (Input * 2)(input_struct_down, input_struct_up)
    SendInput(2, inputs, ctypes.sizeof(inputs[0]))


def extract_filename(path):
    # 去除文件夹路径
    filename = path.split("/")[-1]
    # 去除尾部的文件夹路径
    filename = filename.rsplit("\\", 1)[-1]
    # 去除后缀名
    filename = filename.split(".")[0]

    # 使用正则表达式匹配数字并提取
    match = re.search(r'\d+', filename)
    price = match.group() if match else ''
    if price == '':
        price = '1'  # 如果价格为空字符串，则默认设置为1
    # 切割字符串
    name = filename.replace(price, '')  # 去除数字部分的前缀
    # 返回英雄名和价格
    return name, int(price)


def decode_unicode_escape(string):
    pattern = re.compile(r'\\u([\da-fA-F]{4})')
    result = re.sub(pattern, lambda x: chr(int(x.group(1), 16)), string)
    return result


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # ui图片列表
        self.dict_list = ALL_IMAGE_LIST
        # 是否开启
        self.is_open = True
        # 添加这个属性
        self.is_running = True
        # 是否展示截图范围窗口
        self.debug = False
        # 配置文件名
        self.ini_file = '1bit.ini'
        # 存储图片选中状态的字典
        self.selected_images = {}
        # 选中列表
        self.active_list = []
        # 读取配置文件
        self.load_ini_file()
        # 加载样式
        self.load_styles()
        # 设置ico
        self.setWindowIcon(QIcon('1.ico'))
        # 创建并启动键盘监听线程
        self.keyboard_thread = threading.Thread(target=self.keyboard_listener)
        self.keyboard_thread.start()

        # 创建网格布局
        layout = QGridLayout()
        layout.setSpacing(10)  # 设置间距
        content_widget = QWidget()  # 创建内容部件
        content_widget.setLayout(layout)  # 将布局设置给内容部件

        # 添加图片到布局中
        row = 0
        col = 0

        for fee, zone in self.dict_list.items():
            fee_label = QLabel(f"{fee}费区:")
            fee_label.setStyleSheet("""
                QLabel {
                    color: green;
                    font-size:36px;
                }
            """)
            fee_label.setAlignment(Qt.AlignLeft)
            layout.addWidget(fee_label, row, col, 1, 4)

            # print(zone, 'rows')

            for i, file in enumerate(zone):
                name, price = extract_filename(file)
                image_frame = QFrame()
                image_label = QLabel(image_frame)
                self.selected_images[name] = False  # 初始化选中状态
                image_frame.setStyleSheet(
                    """ 
                      QFrame:hover{
                            border: 1px solid red;
                      }
                       QFrame > QLabel {
                            border: 0;  /* 移除内部QLabel的边框样式 */
                      }
                       QFrame > QLabel:hover{
                            border: 0;  /* 移除内部QLabel的边框样式 */
                       }      
                    """)
                if name in self.active_list:
                    self.active_styles(image_frame, image_label)  # 初始化选中样式
                    self.selected_images[name] = True  # 初始化选中状态

                image_label.setPixmap(QPixmap(file))

                name_label = QLabel(f"英雄名称：{name} 费用：{price}")

                name_label.setStyleSheet(
                    """
                       QLabel {
                           color: white;
                           font-size:18px;
                       }
                   """)

                image_frame.mouseDoubleClickEvent = self.create_double_click_event(image_frame, fee, i, image_label)

                # 将图像和名称标签的对齐方式设置为居中对齐
                image_label.setAlignment(Qt.AlignHCenter)
                name_label.setAlignment(Qt.AlignHCenter)

                frame_layout = QVBoxLayout()
                frame_layout.addWidget(image_label)
                frame_layout.addWidget(name_label)

                # 将帧布局的对齐方式设置为居中对齐
                frame_layout.setAlignment(Qt.AlignHCenter)

                image_frame.setLayout(frame_layout)

                item_row = row + (i // 4) + 1  # 计算当前图片应该在布局中的行索引
                item_col = col + (i % 4)  # 计算当前图片应该在布局中的列索引

                layout.addWidget(image_frame, item_row, item_col)

            last_row_items = len(zone) % 4  # 最后一行的图片数量
            if last_row_items != 4:  # 如果最后一行不足4个图片
                empty_cols = 4 - last_row_items
                empty_frame = QFrame()
                empty_label = QLabel(empty_frame)
                empty_label.setStyleSheet("background-color: rgba(0, 0, 0, 0)")  # 设置背景透明
                layout.addWidget(empty_frame, row + (len(zone) // 4) + 1, col + last_row_items, 1, empty_cols)

            row += (len(zone) // 4) + 2  # 调整行号，为下一个费区预留空白行

        # 创建滚动区域，并将内容部件放入其中
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content_widget)

        # 设置窗口最小宽度
        self.setMinimumWidth(1200)
        self.setMinimumHeight(600)

        # 将滚动区域设置为主窗口的布局
        self.setLayout(QGridLayout())
        self.layout().addWidget(scroll_area)

        # 在程序启动时启动find_hero函数
        # threading.Thread(target=self.find_hero).start()
        threading.Thread(target=self.find_image_hero).start()

    def find_image_hero(self):
        while 1:
            self.get_image_xy("images/hero/ys.png")

    @staticmethod
    def get_image_xy(path, conf=.8):
        print('找到没')
        if pyautogui.locateOnScreen(path, confidence=conf, region=rect_image) is not None:
            pos = pyautogui.center(pyautogui.locateOnScreen(path, confidence=conf, region=rect_image))
            print(pos, 'post')
            x, y = pos
            ab_move(x, y)
            left_click()

    @staticmethod
    def active_styles(dom, d2):
        dom.setStyleSheet(
            """
            QFrame {
                background: rgb(61, 61, 61);
                border: 2px solid red;
            }
            QFrame > QLabel {
                border: 0;  /* 移除内部QLabel的边框样式 */
            }
            QFrame > QLabel:hover{
                border: 0;  /* 移除内部QLabel的边框样式 */
            }
            """
        )

    @staticmethod
    def remove_styles(dom, d2):
        dom.setStyleSheet(
            """ 
                QFrame{
                    background: transparent;  /* 设置背景色为亮绿色 */
                    border:0;
                }
                QFrame:hover{
                    border: 1px solid red;
                }
                QFrame > QLabel{
                    border: 0;  /* 移除内部QLabel的边框样式 */
                }
                QFrame > QLabel:hover{
                    border: 0;  /* 移除内部QLabel的边框样式 */
                }
            """)

    @staticmethod
    def debug_fun(image):
        cv2.namedWindow(cv2_win_name, cv2.WINDOW_NORMAL)  # 创建窗口
        cv2.resizeWindow(cv2_win_name, rect[0] + rect[1], int(top_window_width * (rect[3] / rect[2])))  # 重置窗口大小
        cv2.moveWindow(cv2_win_name, 0, 0)
        cv2.setWindowProperty(cv2_win_name, cv2.WND_PROP_TOPMOST, 1)  # 设置窗口置顶
        cv2.imshow(cv2_win_name, image)
        cv2.waitKey(1)

    def create_double_click_event(self, frame, free, index, image_label):
        def mouseDoubleClickEvent(event):
            # 判断是否已经存在相同的名称
            name, price = extract_filename(self.dict_list[free][index])
            self.selected_images[name] = not self.selected_images[name]
            # 更改样式
            if name not in self.active_list:
                print(f"选中图片 所属费别：{free}费 下标:{index} 图片名称：{name}")
                # 添加名称到数组
                self.active_list.append(name)
                self.active_styles(frame, image_label)
            else:
                print(f"选中图片 所属费别：{free}费 下标:{index} 图片名称：{name}")
                # 从数组中移除名称
                self.active_list.remove(name)
                self.remove_styles(frame, image_label)

            print(self.active_list, 'change list')
            self.update_ini_file()  # 同步ini

        return mouseDoubleClickEvent

    def on_press_c(self, key):
        if key == keyboard.KeyCode(char='+'):
            self.is_open = not self.is_open
            print(f"开启状态：{self.is_open}")
            if self.is_open:
                winsound.PlaySound('music/8855.wav', flags=1)
            else:
                winsound.PlaySound('music/close.wav', flags=1)
        if key == keyboard.KeyCode(char='`'):
            print('---')
            left = 483
            t = 940
            w = 180
            h = 98
            i = 0
            for _ in range(5):
                T = left + (i * 203)
                offset = 0
                if i == 4:
                    offset = 3
                save_range = (T, t, w - offset, h)
                image = grab_gpt_win(save_range, False)  # 截图
                timestamp = str(int(time.time()))  # 获取当前时间戳
                print(T, 'left')
                save_path = f"images/hero/hero_{timestamp}{i}.png"
                cv2.imwrite(save_path, image)
                i += 1
                print(f"已保存图片至 {save_path}")

    def find_hero(self):
        while self.is_running:
            if not self.is_open:
                time.sleep(0.01)
                continue
            image = grab_gpt_win(rect)  # 截图
            result = ocr.ocr(image, det=True, cls=True)[0]  # 推理
            if result:
                self.move_hero(result)  # 移动
            if self.debug:
                self.debug_fun(image)  # debug

    def move_hero(self, result):
        boxes = [line[0] for line in result]
        txt_list = [line[1][0] for line in result]
        scores = [line[1][1] for line in result]
        if txt_list:  # 检查列表是否为空
            for box, txt, confidence in zip(boxes, txt_list, scores):
                if txt in self.active_list and confidence > 0.65:
                    x_center = int((box[0][0] + box[2][0]) / 2)
                    y_center = int((box[0][1] + box[2][1]) / 2)
                    offset = 50  # 50
                    x = (x_center + offset) + rect[0]
                    y = (y_center - offset) + rect[1]
                    ab_move(x, y)
                    # 进行点击操作
                    left_click()
                    print(f"已找到 置信度：{confidence} 目标：{txt} ")

    def keyboard_listener(self):
        # 创建键盘监听器
        listener = keyboard.Listener(on_press=self.on_press_c)
        # 启动监听器
        listener.start()

    def update_ini_file(self):
        global config
        if os.access(self.ini_file, os.W_OK):
            config.set('section_name', 'group', ','.join(self.active_list))
            with open(self.ini_file, 'w') as file:
                config.write(file)

    def load_ini_file(self):
        if os.access(self.ini_file, os.R_OK):
            if os.path.isfile(self.ini_file):
                config.read(self.ini_file)
                group = config.get('section_name', 'group')
                self.active_list = group.split(',') if group else []
                print(self.active_list, '初始化时的列表')
            else:
                self.active_list = []
                # 创建新的INI文件并初始化配置项
                config['section_name'] = {'group': ''}
                with open(self.ini_file, 'w') as file:
                    config.write(file)

    def load_styles(self):
        # 设置窗口透明度
        self.setStyleSheet("""
                  /* 设置窗口背景颜色 */
                  background-color: rgb(15,15,15);  /* 使用深色背景 */

                  /* 设置窗口圆角 */
                  border-radius: 10px;

                  /* 设置按钮样式 */
                  QPushButton {
                      background-color: #444;  /* 设置按钮背景色为深灰色 */
                      color: #fff;  /* 设置按钮文字颜色为白色 */
                      border: none;
                      padding: 10px 20px;
                      border-radius: 5px;
                  }
                  QPushButton:hover {
                      background-color: #666;  /* 设置鼠标悬停时的背景色为较浅的灰色 */
                  }
                  QPushButton:pressed {
                      background-color: #333;  /* 设置按下时的背景色为稍深的灰色 */
                  }

                  /* 设置标签样式 */
                  QLabel {
                      color: #fff;  /* 设置文字颜色为白色 */
                      font-size: 16px;
                  }

                  /* 设置文本框样式 */
                  QLineEdit {
                      background-color: #333;  /* 设置文本框背景色为深灰色 */
                      color: #fff;  /* 设置文本框文字颜色为白色 */
                      border: 1px solid #666;  /* 设置文本框边框样式为浅灰色 */
                      border-radius: 5px;
                      padding: 5px;
                  }
              """)
        # 配置窗口标题
        self.setWindowTitle("云顶秒卡小工具 小键盘+号开关 管理员模式运行 鼠标双击选中 or 取消")

    def closeEvent(self, event):
        self.is_running = False  # 设置标志位

        self.keyboard_thread.join()

        app.quit()


class StartWindow(QWidget):
    def __init__(self):
        global is_gpu, ocr
        super().__init__()
        self.setWindowTitle("作者1bit 软件免费 软件免费 软件免费 如对您有帮助 请支持一下 谢谢 ")
        self.setFixedSize(600, 400)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # 设置窗口前置
        self.load_styles()
        self.setWindowIcon(QIcon('1.ico'))
        # 创建布局和控件
        layout = QVBoxLayout()
        self.setLayout(layout)
        # 创建 CSS 类
        css_class = "white-label { color: white; font-size:18px; }"
        # 将 CSS 类应用于所有标签
        self.setStyleSheet(css_class)
        # 创建水平布局
        hbox = QHBoxLayout()

        # 添加第一个图片和标签
        image1_label = QLabel(self)
        pixmap1 = QPixmap('images/1.jpg')
        image1_label.setPixmap(pixmap1)

        label1 = QLabel("微信扫上面↑↑↑~", self)
        label1.setObjectName("white-label")
        label1.setAlignment(Qt.AlignCenter)
        # 创建垂直布局并添加图片和标签
        vbox1 = QVBoxLayout()
        vbox1.addWidget(image1_label, alignment=Qt.AlignCenter)
        vbox1.addWidget(label1, alignment=Qt.AlignCenter)

        # 将垂直布局添加到水平布局中
        hbox.addLayout(vbox1)

        # 添加间隔
        hbox.addSpacing(30)

        # 添加第二个图片和标签
        image2_label = QLabel(self)
        pixmap2 = QPixmap('images/2.png')
        image2_label.setPixmap(pixmap2)

        label2 = QLabel("支付宝扫上面↑↑↑~", self)
        label2.setObjectName("white-label")
        label2.setAlignment(Qt.AlignCenter)

        # 创建垂直布局并添加图片和标签
        vbox2 = QVBoxLayout()
        vbox2.addWidget(image2_label, alignment=Qt.AlignCenter)
        vbox2.addWidget(label2, alignment=Qt.AlignCenter)

        # 将垂直布局添加到水平布局中
        hbox.addLayout(vbox2)

        # 添加水平布局到垂直布局中
        layout.addLayout(hbox)

        # 添加布局
        h_layout = QHBoxLayout()

        # 添加Label
        label = QLabel("启用GPT推理", self)

        # 设置左边距为50像素，下边距为30像素
        h_layout.setContentsMargins(35, 0, 0, 30)

        # 设置标签和按钮之间的间距为50像素
        h_layout.setSpacing(50)

        # 添加按钮组
        self.gpu_button_group = QButtonGroup(self)
        self.gpu_button_group.setExclusive(True)  # 确保只能选择一个按钮

        # 添加按钮
        self.gpu_button1 = QRadioButton("是", self)
        self.gpu_button2 = QRadioButton("否", self)

        self.gpu_button_group.addButton(self.gpu_button1, 0)
        self.gpu_button_group.addButton(self.gpu_button2, 1)

        # 默认选择"否"
        self.gpu_button2.setChecked(True)

        self.gpu_button_group.buttonClicked[int].connect(self.update_is_gpu)

        # 设置stretch因子，使Label和按钮均分一行
        h_layout.addWidget(label, 1)
        h_layout.addWidget(self.gpu_button1, 1)
        h_layout.addWidget(self.gpu_button2, 1)

        # 将布局添加到主布局中（假设主布局为垂直布局，命名为layout）
        layout.addLayout(h_layout)

        button = QPushButton("进入主程序", self)
        button.clicked.connect(self.open_main_window)

        button.setStyleSheet('''
            QPushButton {
                background-color: rgb(61, 61, 61);
                color: white;
                font-size: 20px;
                border-radius: 10px;
                padding: 5px;
            }
        ''')

        layout.addWidget(button)

        # 设置窗口样式
        self.setStyleSheet("""
            StartWindow {
                background-color: rgb(30, 30, 30);
            }
        """)

    @staticmethod
    def update_is_gpu(gpu_button):
        global is_gpu
        if gpu_button == 0:
            is_gpu = True
        else:
            is_gpu = False
        print(f"是否开启GPU:{is_gpu}")

    def load_styles(self):
        # 设置窗口透明度
        self.setStyleSheet("""
                      /* 设置窗口圆角 */
                      border-radius: 10px;

                      /* 设置按钮样式 */
                      QPushButton {
                          background-color: #444;  /* 设置按钮背景色为深灰色 */
                          color: #fff;  /* 设置按钮文字颜色为白色 */
                          border: none;
                          padding: 10px 20px;
                          border-radius: 5px;
                      }
                      QPushButton:hover {
                          background-color: #666;  /* 设置鼠标悬停时的背景色为较浅的灰色 */
                      }
                      QPushButton:pressed {
                          background-color: #333;  /* 设置按下时的背景色为稍深的灰色 */
                      }

                      /* 设置标签样式 */
                      QLabel {
                          color: #fff;  /* 设置文字颜色为白色 */
                          font-size: 16px;
                      }

                      /* 设置文本框样式 */
                      QLineEdit {
                          background-color: #333;  /* 设置文本框背景色为深灰色 */
                          color: #fff;  /* 设置文本框文字颜色为白色 */
                          border: 1px solid #666;  /* 设置文本框边框样式为浅灰色 */
                          border-radius: 5px;
                          padding: 5px;
                      }
                  """)

    def open_main_window(self):
        global ocr
        print(f"正在开始加载推理模型")
        det_model_dir = ".paddleocr/whl/det/ch/ch_ppocr_server_v2.0_det_infer"
        rec_model_dir = ""
        cls_model_dir = ""
        ocr = PaddleOCR(det_model_dir=det_model_dir, use_angle_cls=True, use_gpu=is_gpu, lang="ch")
        print(f"加载完成", is_gpu)

        self.close()
        # 创建并显示主窗口
        main_window = MainWindow()
        main_window.show()
        # 将窗口前置
        main_window.setWindowState(main_window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        main_window.activateWindow()
        main_window.raise_()


if __name__ == '__main__':
    # 解决多线程打包问题
    multiprocessing.freeze_support()
    if not windll.shell32.IsUserAnAdmin():
        ctypes.windll.user32.MessageBoxW(0, "需要管理员权限来运行此程序", "权限错误", 0x10)
        sys.exit()

    ALL_IMAGE_LIST = get_files()
    # print(ALL_IMAGE_LIST, 'ALL_IMAGE_LIST')
    # 创建应用程序实例
    app = QApplication([])
    # 设置图标
    app.setWindowIcon(QIcon('1.icon'))
    # 创建并显示 StartWindow
    start_window = StartWindow()
    start_window.show()

    # 运行应用程序主循环
    sys.exit(app.exec())
