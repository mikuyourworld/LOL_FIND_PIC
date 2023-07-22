import configparser
import multiprocessing
import os
import re
import sys
import threading
import ctypes
import time
from ctypes import windll
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPainterPath, QPen, QColor
import numpy as np
import pyautogui
import winsound
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QButtonGroup, QRadioButton
from PyQt5.QtWidgets import QWidget, QGridLayout, QScrollArea, QFrame
from pynput import keyboard
import cv2
import win32api
import win32con
import win32gui
import win32ui
import logging

is_debug = False

is_grayscale = False  # 默认不开启
is_show_not_find_window = True
window_size = None
INPUT_MOUSE = 0
MOUSEEVENTF_ABSOLUTE = 0x8000  # 使用绝对坐标
MOUSEEVENTF_MOVE = 0x0001  # 移动鼠标
MOUSEEVENTF_LEFTDOWN = 0x0002  # 按下左键
MOUSEEVENTF_LEFTUP = 0x0004  # 释放左键
logging.disable(logging.DEBUG)  # 关闭DEBUG日志的打印
logging.disable(logging.WARNING)  # 关闭WARNING日志的打印

money_range = (813, 877, 131, 37)  # 金币所在位置

rect = (480, 1030, 1000, 45)  # 英雄所在区域

region = (482, 930, 1000, 110)

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


# 定义结构体和常量
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


# 注册窗口类
wc = win32gui.WNDCLASS()
wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
wc.hbrBackground = win32con.COLOR_WINDOW
wc.lpszClassName = 'PythonWindowClass'
wc.lpfnWndProc = lambda hwnd, msg, wParam, lParam: 0

win32gui.RegisterClass(wc)


class Input(ctypes.Structure):
    class Union(ctypes.Union):
        _fields_ = [("mi", MouseInput)]

    _fields_ = [("type", ctypes.c_ulong),
                ("union", Union)]


# 加载user32.dll
user32 = ctypes.WinDLL("user32.dll")

# 定义SendInput函数
SendInput = ctypes.windll.user32.SendInput
SendInput.restype = ctypes.c_uint
SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(Input), ctypes.c_int]


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


def filter_list(lst, num):
    lst.sort()  # 排序列表
    result = []  # 存储结果的列表
    i = 0
    while i < len(lst):
        current = lst[i]
        result.append(current)  # 将当前元素添加到结果列表中
        j = i + 1
        while j < len(lst) and lst[j][0] - current[0] <= num:
            j += 1
        i = j

    return result


def decode_unicode_escape(string):
    pattern = re.compile(r'\\u([\da-fA-F]{4})')
    result = re.sub(pattern, lambda x: chr(int(x.group(1), 16)), string)
    return result


class MaskLayerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Tracking')
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowTransparentForInput |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(1920, 1080)
        self.rects = []
        print('初始化Mask')

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setOpacity(1)
        qp.setPen(QPen(QColor(255, 165, 0), 2))  # 设置线宽为1像素，颜色为橙黄色

        for x, y, w, h in self.rects:
            rect_path = QPainterPath()
            rect_path.addRect(x, y, w, h)
            qp.drawPath(rect_path)
        qp.end()

    def remove_all(self):
        if len(self.rects):
            self.rects = []
            self.update()

    def add_rects(self, rects):
        self.rects = []
        n_rects = self.rects + rects
        filter_rects = filter_list(n_rects, 10)
        self.rects = filter_rects
        print(f"处理之前：{rects} 当前检测数据：{rects} 合并后：{n_rects} 过滤后：{filter_rects} 最终：{self.rects}")
        self.update()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # ui图片列表
        self.rect_items = None
        self.flag = None
        self.dict_list = ALL_IMAGE_LIST
        # 是否开启
        self.is_open = True
        # 添加这个属性
        self.is_running = True
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

        self.mask_window = MaskLayerWindow()
        self.mask_window.show()

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
        while self.is_running:
            if is_debug:
                im = grab_gpt_win(region)
                self.debug_fun(im)
            # 在适当的时机执行绘制操作
            if self.is_open:
                t1 = time.time()
                self.rect_items = []  # 存储所有矩形坐标的列表
                for name in self.active_list:
                    path = os.path.join("images/hero/", f"{name}.png")
                    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), -1)
                    self.get_image_xy(image, name)

                if not self.rect_items:
                    print(f"啥也没找到remove")
                    self.mask_window.remove_all()  # 如果一次都没找到则remove_all
                else:
                    # 执行绘制操作
                    f_items = filter_list(self.rect_items, 10)
                    self.mask_window.add_rects(f_items)
            time.sleep(0.001)

    def get_image_xy(self, image, name, conf=.7):
        try:
            ims = list(pyautogui.locateAllOnScreen(image=image, confidence=conf, region=region))
            if ims:
                rect_items = []  # 存储矩形坐标的列表
                for match in ims:
                    pos = pyautogui.center(match)
                    w, h = match.width, match.height
                    x, y = pos
                    x, y = int(x - (w / 2)), int(y - (h / 2))  # 取中心坐标
                    # 测试数据
                    rect_item = (x, y, w, h)
                    rect_items.append(rect_item)  # 将矩形坐标添加到列表中
                # 在原有代码中的对应位置调用：
                if rect_items:
                    self.flag = True
                    self.rect_items.extend(rect_items)  # 将当前找到的矩形坐标扩展到整体列表中
        except Exception as e:
            print(f"Error occurred: {e}")

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
        cv2.resizeWindow(cv2_win_name, region[0] + region[1], int(1920 * (region[3] / region[2])))  # 重置窗口大小
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
                self.mask_window.remove_all()
                winsound.PlaySound('music/close.wav', flags=1)
        if key == keyboard.KeyCode(char='`'):
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
        global is_grayscale, ocr
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
        h_layout_debug = QHBoxLayout()
        # 添加Label
        label_debug = QLabel("debug模式", self)

        # 设置左边距为50像素，下边距为30像素
        h_layout_debug.setContentsMargins(35, 0, 0, 30)

        # 设置标签和按钮之间的间距为50像素
        h_layout_debug.setSpacing(50)

        # 添加按钮组
        self.gpu_button_group_debug = QButtonGroup(self)
        self.gpu_button_group_debug.setExclusive(True)  # 确保只能选择一个按钮

        # 添加按钮
        self.gpu_button3 = QRadioButton("是", self)
        self.gpu_button4 = QRadioButton("否", self)

        self.gpu_button_group_debug.addButton(self.gpu_button3, 0)
        self.gpu_button_group_debug.addButton(self.gpu_button4, 1)

        # 默认选择"否"
        self.gpu_button4.setChecked(True)

        self.gpu_button_group_debug.buttonClicked[int].connect(self.update_is_debug)

        # 设置stretch因子，使Label和按钮均分一行
        h_layout_debug.addWidget(label_debug, 1)
        h_layout_debug.addWidget(self.gpu_button3, 1)
        h_layout_debug.addWidget(self.gpu_button4, 1)
        # ___
        # 添加主布局
        layout.addLayout(h_layout_debug)

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
    def update_is_grayscale(gpu_button):
        global is_grayscale
        if gpu_button == 0:
            is_grayscale = True
        else:
            is_grayscale = False
        print(f"是否灰度匹配:{is_grayscale}")

    @staticmethod
    def update_is_debug(gpu_button):
        global is_debug
        if gpu_button == 0:
            is_debug = True
        else:
            is_debug = False
        print(f"是否开启debug:{is_debug}")

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
