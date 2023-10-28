import cv2 as cv
import numpy as np
import os
import pyautogui
import time
import keyboard
import tkinter as tk
from threading import Thread, Lock
from PIL import Image, ImageOps
import win32gui, win32ui, win32con
from tkinter import ttk

class WindowCapture:

    # properties
    w = 0
    h = 0
    hwnd = None
    screenshot = None
    cropped_x = 0
    cropped_y = 0
    offset_x = 0
    offset_y = 0

    # constructor
    def __init__(self, window_name=None):
        # create a thread lock object
        self.lock = Lock()
        # find the handle for the window we want to capture.
        # if no window name is given, capture the entire screen
        if window_name is None:
            self.hwnd = win32gui.GetDesktopWindow()
        else:
            self.hwnd = win32gui.FindWindow(None, window_name)
            if not self.hwnd:
                raise Exception('Window not found: {}'.format(window_name))

        # get the window size
        window_rect = win32gui.GetWindowRect(self.hwnd)
        self.w = window_rect[2] - window_rect[0]
        self.h = window_rect[3] - window_rect[1]

        # account for the window border and titlebar and cut them off
        border_pixels = 8
        titlebar_pixels = 8
        self.w = self.w - (border_pixels * 2)
        self.h = self.h - titlebar_pixels - border_pixels
        self.cropped_x = border_pixels
        self.cropped_y = titlebar_pixels

        # set the cropped coordinates offset so we can translate screenshot
        # images into actual screen positions
        self.offset_x = window_rect[0] + self.cropped_x
        self.offset_y = window_rect[1] + self.cropped_y

    def get_screenshot(self):

        # get the window image data
        wDC = win32gui.GetWindowDC(self.hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, self.w, self.h)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (self.w, self.h), dcObj, (self.cropped_x, self.cropped_y), win32con.SRCCOPY)

        # convert the raw data into a format opencv can read
        signedIntsArray = dataBitMap.GetBitmapBits(True)
        img = np.frombuffer(signedIntsArray, dtype='uint8')
        img.shape = (self.h, self.w, 4)

        # free resources
        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())

        # drop the alpha channel
        img = img[...,:3]

        # make image C_CONTIGUOUS to avoid errors that look like:
        img = np.ascontiguousarray(img)

        return img

    def get_screen_position(self, pos):
        return (pos[0] + self.offset_x, pos[1] + self.offset_y)
    # threading methods
    def start(self):
        self.stopped = False
        t = Thread(target=self.run)
        t.start()

    def stop(self):
        self.stopped = True

    def run(self):

        while not self.stopped:
            # get an updated image of the game
            screenshot = self.get_screenshot()
            # lock the thread while updating the results
            self.lock.acquire()
            self.screenshot = screenshot
            self.lock.release()

class Vision:

    # properties
    needle_img = None
    needle_w = 0
    needle_h = 0
    method = None

    # constructor
    def __init__(self, needle_img_path, method=cv.TM_CCOEFF_NORMED):
        # load the image we're trying to match
        self.needle_img = cv.imread(needle_img_path, cv.IMREAD_UNCHANGED)
        # Save the dimensions of the needle image
        self.needle_w = self.needle_img.shape[1]
        self.needle_h = self.needle_img.shape[0]
        self.method = method

    def findLoc(self, haystack_img, threshold=0.5):
        # run the OpenCV algorithm
        result = cv.matchTemplate(haystack_img, self.needle_img, self.method)
        # Get the best position from the match result that exceed our threshold
        min_val, result_threshold, min_loc, location = cv.minMaxLoc(result)

        if result_threshold > threshold:

            return location[0]+ int(self.needle_w/2),location[1]+ int(self.needle_h/2)
        else:
            return [-1,-1]

    def find(self, haystack_img, threshold=0.5):
        # run the OpenCV algorithm
        result = cv.matchTemplate(haystack_img, self.needle_img, self.method)
        # Get the all the positions from the match result that exceed our threshold
        min_val, result_threshold, min_loc, location = cv.minMaxLoc(result)
        if result_threshold > threshold:
            return 0
        else:
            return 1

class BotState:

    # set states of the char
    MANA_FULL = 0
    MANA_LOW = 1
    life_GREEN = 2
    life_YELLOW = 3
    life_RED = 4
    INICIADO = 5
    life_FULL = 6
    FOOD_FULL = 7
    FOOD_LOW = 8
    NO_HAST = 9
    HASTED = 10

class Detection:

    # threading properties
    stopped = True
    lock = None
    # properties
    state = None
    state_life = None
    state_mana = None
    state_food = None
    state_hast = None
    screenshot = None
    loc_life = []
    porcentagem = 0

    # constructor
    def __init__(self, char_name, label_text, p_strong_heal, p_medium_heal, p_low_heal, p_mana):
        # create a thread lock object
        self.lock = Lock()
        # % of life to use high heal
        self.p_strong_heal = (int(p_strong_heal))
        # % of life to use medium heal
        self.p_medium_heal = (int(p_medium_heal))
        # % of life to use low heal
        self.p_low_heal = (int(p_low_heal))
        # % of life to use mana potion
        self.p_mana = (int(p_mana))
        #pixel to check life
        self.plx_strong_heal = (int(93/100 * self.p_strong_heal))
        self.plx_medium_heal = (int(93/100 * self.p_medium_heal))
        self.plx_low_heal = (int(93/100 * self.p_low_heal))
        #pixel to check mana
        self.plx_mana = (int(93/100 * self.p_mana))
        #img
        self.life = Vision('life.jpg')
        self.food = Vision('food.jpg')
        self.hast = Vision('hast.png')

        self.label_text = label_text
        self.char_name = char_name
        # start WindowCapture
        self.wincap = WindowCapture(f'Tibia - {self.char_name}')
        # take a screenshot
        self.screenshot = self.wincap.get_screenshot()
        # take coordenates of life pxl and check
        self.loc_life = self.life.findLoc(self.screenshot, 0.95)
        if self.loc_life[0] == -1:
            self.label_text['text'] = f'Erro: Não achou as barras de status'
        else:
            self.label_text['text'] = f'Está no jogo'
            # take the life bar coordenates and ajust to mana
            self.loc_life = [self.loc_life[0]+8, self.loc_life[1]]
            self.loc_mana = [self.loc_life[0]+8, self.loc_life[1]+14]
            self.loc_barra_top = [self.loc_life[0]-6, self.loc_life[1]+167]
            self.loc_barra_bot = [self.loc_life[0]+101, self.loc_life[1]+180]
            self.state = BotState.INICIADO
    # update screenshot
    def update(self, screenshot):
        self.lock.acquire()
        self.screenshot = screenshot
        self.lock.release()
    # check if for life and mana pxl
    def bar_state(self, porcentagem, barra):
        result = False
        if barra == "life":
            b, g, r = self.screenshot[self.loc_life[1], self.loc_life[0]+ porcentagem]
            if r != 255:
                result = True
            else:
                 result = False

        elif barra == "mana":
            b, g, r = self.screenshot[self.loc_mana[1], self.loc_mana[0]+ porcentagem]
            if r != 95:
                result = True
            else:
                result = False
        return result
    # check for imagens on status bar
    def status_state(self, status):
        result = False
        if status == "food":
            check_food = self.food.find(self.screenshot)
            if check_food == 0:
                result = True
            else:
                result = False

        if status == "hast":
            check_hast = self.hast.find(self.screenshot)
            if check_hast == 0:
                result = True
            else:
                result = False

        return result
    # start the thread
    def start(self):
        self.stopped = False
        t = Thread(target=self.run)
        t.start()

    # stop the thread
    def stop(self):

        self.stopped = True

    def run(self):

        # start to take screenshot
        self.wincap.start()
        # main loop
        while not self.stopped:
            if self.state == BotState.INICIADO:
                # do object detection
                if self.wincap.screenshot is None:
                    continue
                # give a new screenshot to detection
                self.screenshot = self.wincap.screenshot
                # updade screenshot
                self.update(self.screenshot)
                #check life
                estado_life_vermelha = self.bar_state(self.plx_strong_heal, "life")
                if estado_life_vermelha:
                    self.state_life = BotState.life_RED
                #check life
                estado_life_amarela = self.bar_state(self.plx_medium_heal, "life")
                if estado_life_amarela:
                    self.state_life = BotState.life_YELLOW
                #check life
                estado_life_verde = self.bar_state(self.plx_low_heal, "life")
                if estado_life_verde:
                    self.state_life = BotState.life_GREEN
                else:
                    self.state_life = BotState.life_FULL
                #check mana
                estado_mana = self.bar_state(self.plx_mana, "mana")
                if estado_mana:
                    self.state_mana = BotState.MANA_LOW
                else:
                    self.state_mana = BotState.MANA_FULL
                #check food
                estado_food = self.status_state("food")
                if estado_food:
                    self.state_food = BotState.FOOD_LOW
                else:
                    self.state_food = BotState.FOOD_FULL
                #check hast
                estado_hast = self.status_state("hast")
                if estado_hast:
                    self.state_hast = BotState.HASTED
                else:
                    self.state_hast = BotState.NO_HAST

class Healer():
    # threading properties
    stopped = True
    lock = None
    def __init__(self,char_name, p_low_heal, p_medium_heal, p_strong_heal, p_mana, label_text, hk_cura_menor, hk_cura_media, hk_cura_maior, hk_cura_mana, hk_food, cb_food, hk_hast, cb_hast):
        self.label_text = label_text
        self.char_name = char_name
        # hotkey
        self.cura_menor = hk_cura_menor
        self.cura_media = hk_cura_media
        self.cura_maior = hk_cura_maior
        self.cura_mana = hk_cura_mana
        self.hk_food = hk_food
        self.hk_hast = hk_hast
        # check box
        self.cb_food = cb_food
        self.cb_hast = hk_hast
        # % of heals
        self.p_low_heal = p_low_heal
        self.p_medium_heal = p_medium_heal
        self.p_strong_heal = p_strong_heal
        self.p_mana = p_mana
        # used potion cooldown
        self.t_cd_pot_used = 0
        # potion cooldown
        self.t_cd_pot= 0
        # used skill cooldown
        self.t_cd_skill_used = 0
        # skill cooldown
        self.t_cd_skill= 0
        # used hast cooldown
        self.t_cd_hast_used = 0
        # hast cooldown
        self.t_cd_hast= 0
        # actions calls
        self.mana_low_call = False
        self.mana_full_call = False
        self.life_low_call = False
        self.life_med_call = False
        self.life_high_call = False
        self.life_full_call = False

    def run(self):

        # start detectador class
        self.detector = Detection(self.char_name, self.label_text, self.p_strong_heal, self.p_medium_heal, self.p_low_heal, self.p_mana)
        # start thread
        self.detector.start()

        while not self.stopped:
            # start status check
            self.t_cd_pot = time.perf_counter()
            if self.detector.state_life == BotState.life_RED:
                self.life_high_call = False
                self.life_med_call = False
                self.life_full_call = False
                if self.t_cd_pot - self.t_cd_pot_used >= 1:
                    life_high_call = False
                    pyautogui.press(self.cura_maior)
                    self.t_cd_pot_used = time.perf_counter()
                    if self.life_low_call == False:
                        self.life_low_call = True
                        self.label_text['text'] = f"Curar life {self.p_strong_heal} %"

            if self.detector.state_life == BotState.life_YELLOW:
                self.life_high_call = False
                self.life_low_call = False
                self.life_full_call = False
                if self.t_cd_pot - self.t_cd_pot_used >= 1:
                    pyautogui.press(self.cura_media)
                    self.t_cd_pot_used = time.perf_counter()
                    if self.life_med_call == False:
                        self.life_med_call = True
                        self.label_text['text'] = f"Curar life {self.p_medium_heal} %"

            self.t_cd_skill = time.perf_counter()
            if self.detector.state_life == BotState.life_GREEN:
                self.life_med_call = False
                self.life_low_call = False
                self.life_full_call = False
                if self.t_cd_skill - self.t_cd_skill_used >= 1:
                    pyautogui.press(self.cura_menor)
                    self.t_cd_skill_used = time.perf_counter()
                    if self.life_high_call == False:
                        self.life_high_call = True
                        self.label_text['text'] = f"Curar life {self.p_low_heal} %"

            if self.detector.state_life == BotState.life_FULL:
                self.life_med_call = False
                self.life_low_call = False
                self.life_high_call = False
                if self.life_full_call == False:
                    self.life_full_call = True
                    self.label_text['text'] = f"life 100 %"

            if self.detector.state_mana == BotState.MANA_FULL:
                self.mana_low_call = False
                if self.mana_full_call == False:
                    self.mana_full_call = True
                    self.label_text['text'] = f"Mana 100 %"

            self.t_cd_pot = time.perf_counter()

            if self.detector.state_mana == BotState.MANA_LOW and self.detector.state_life != BotState.life_RED:
                self.mana_full_call = False
                if self.t_cd_pot - self.t_cd_pot_used >= 1:
                    pyautogui.press(self.cura_mana)
                    self.t_cd_pot_used = time.perf_counter()
                    if self.mana_low_call == False:
                        self.mana_low_call = True
                        self.label_text['text'] = f"Curar mana {self.p_mana} %"
            '''#usar Food
            if self.detector.state_food == BotState.FOOD_LOW:
                pyautogui.press(self.hk_food)
                self.label_text['text'] = f" Usando Food %"'''

            print("Check hast")
            self.t_cd_hast = time.perf_counter()
            print(self.detector.state_hast)
            if self.detector.state_hast == BotState.NO_HAST:
                if self.t_cd_hast - self.t_cd_hast_used >= 2:
                    pyautogui.press(self.hk_hast)
                    self.label_text['text'] = f" Usando Hast %"
                    self.t_cd_hast_used = time.perf_counter()

    def start(self):
        # Avisa a thread para inicar a função
        self.stopped = False
        t = Thread(target=self.run)
        t.start()

    def stop(self):
        #Avisa a thread para Parar
        self.stopped = True
        self.detector.wincap.stop()
        self.detector.stop()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        #setup
        self.title('Healer')
        self.iconbitmap(r'logo.ico')
        self.geometry("300x300")
        self.wm_attributes("-topmost", True)
        #widgets
        self.Tabs = Notebook(self)
        self.nameMenu = Menu(self.Tabs.tab1)
        self.healerSetup = HealerSetup(self.Tabs.tab1)
        self.buttonMenu = ButtonMenu(self.Tabs.tab1, self.start, self.stop)
        self.textMenu = TextMenu(self.Tabs.tab1)
        self.suportSetup = SuportSetup(self.Tabs.tab2)
        self.stopped_macro = False
        #run
        self.mainloop()

    def start(self):

        self.healer = Healer(self.nameMenu.e_0.get(), self.healerSetup.e_3.get(), self.healerSetup.e_2.get(), self.healerSetup.e_1.get(),
        self.healerSetup.e_4.get(), self.textMenu.l_5, self.healerSetup.e_3_1.get(), self.healerSetup.e_2_1.get(), self.healerSetup.e_1_1.get(), self.healerSetup.e_4_1.get(), self.suportSetup.e_hk_food, self.suportSetup.cb_food_var, self.suportSetup.e_hk_hast, self.suportSetup.cb_hast_var)
        self.healer.start()

    def stop(self):
        self.textMenu.l_5['text'] = f"Macro Parado"
        self.healer.stop()

class Notebook(ttk.Notebook):
    def __init__(self, parent):
        super().__init__(parent)

        self.tab1 = ttk.Frame(self)
        self.tab2 = ttk.Frame(self)
        self.add(self.tab1, text = 'Healer Setup')
        self.add(self.tab2, text = 'Suport Setup')
        self.pack(fill = 'both', expand = True, padx = 5, pady = 5)

class Menu(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill = 'both', expand = True, padx = 5, pady = 5)
        self.create_widgets()

    def create_widgets(self):
        #Texto nome do char
        self.l_0 = ttk.Label(self, text="Nome do Char:")
        self.l_0.pack(side = 'left', fill = 'both', expand = True)
        #Entrada do char
        self.e_0 = ttk.Entry(self, width = 20)
        self.e_0.insert(0,'Royal John')
        self.e_0.pack(side = 'left', fill = 'x', expand = True)

class HealerSetup(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.cura_maior_frame = ttk.Frame(self)
        self.cura_maior_frame.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.cura_media_frame = ttk.Frame(self)
        self.cura_media_frame.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.cura_menor_frame = ttk.Frame(self)
        self.cura_menor_frame.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.cura_mana_frame = ttk.Frame(self)
        self.cura_mana_frame.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.create_widgets()

    def create_widgets(self):
        #Texto cura maior ----------------------------------------------
        self.l_1 = ttk.Label(self.cura_maior_frame, text="Curar Maior:")
        self.l_1.pack(side = 'left', fill = 'x', expand = False)
        #Entrada cura maior
        self.e_1 = ttk.Entry(self.cura_maior_frame, width = 2)
        self.e_1.pack(side = 'left', fill = 'x', expand = False)
        self.e_1.insert(0,'20')
        #Texto porcentagem
        self.l_1_1 = ttk.Label(self.cura_maior_frame, text="%")
        self.l_1_1.pack(side = 'left', fill = 'x', expand = False)
        #Texto hotkey
        self.l_1_2 = ttk.Label(self.cura_maior_frame, text="HotKey:")
        self.l_1_2.pack(side = 'left', fill = 'x', expand = False)
        #Entrada hotkey cura maior
        self.e_1_1 = ttk.Entry(self.cura_maior_frame, width = 2)
        self.e_1_1.pack(side = 'left', fill = 'x', expand = False)
        self.e_1_1.insert(0,'f4')
        #Texto cura media ----------------------------------------------
        self.label_text = ttk.Label(self.cura_media_frame, text="Curar Media:")
        self.label_text.pack(side = 'left', fill = 'x', expand = False)
        #Entrada cura media
        self.e_2 = ttk.Entry(self.cura_media_frame, width = 2)
        self.e_2.pack(side = 'left', fill = 'x', expand = False)
        self.e_2.insert(0,'50')
        #Texto porcentagem media
        self.label_text_1 = ttk.Label(self.cura_media_frame, text="%")
        self.label_text_1.pack(side = 'left', fill = 'x', expand = False)
        #Texto hotkey
        self.label_text_2 = ttk.Label(self.cura_media_frame, text="HotKey:")
        self.label_text_2.pack(side = 'left', fill = 'x', expand = False)
        #Entrada hotkey cura maior
        self.e_2_1 = ttk.Entry(self.cura_media_frame, width = 2)
        self.e_2_1.pack(side = 'left', fill = 'x', expand = False)
        self.e_2_1.insert(0,'f3')
        #Texto cura menor ----------------------------------------------
        self.l_3 = ttk.Label(self.cura_menor_frame,text="Curar Menor:")
        self.l_3.pack(side = 'left', fill = 'x', expand = False)
        #Entrada cura menor
        self.e_3 = ttk.Entry(self.cura_menor_frame, width = 2)
        self.e_3.pack(side = 'left', fill = 'x', expand = False)
        self.e_3.insert(0,'90')
        #Texto porcentagem
        self.l_3_1 = ttk.Label(self.cura_menor_frame,text="%")
        self.l_3_1.pack(side = 'left', fill = 'x', expand = False)
        #Texto hotkey
        self.l_3_2 = ttk.Label(self.cura_menor_frame, text="HotKey:")
        self.l_3_2.pack(side = 'left', fill = 'x', expand = False)
        #Entrada hotkey cura maior
        self.e_3_1 = ttk.Entry(self.cura_menor_frame, width = 2)
        self.e_3_1.pack(side = 'left', fill = 'x', expand = False)
        self.e_3_1.insert(0,'f1')
        #Texto cura mana ----------------------------------------------
        self.l_4 = ttk.Label(self.cura_mana_frame,text="Curar Mana:")
        self.l_4.pack(side = 'left', fill = 'x', expand = False)
        #Entrada cura mana
        self.e_4 = ttk.Entry(self.cura_mana_frame, width = 2)
        self.e_4.pack(side = 'left', fill = 'x', expand = False)
        self.e_4.insert(0,'20')
        #Texto porcentagem
        self.l_4_1 = ttk.Label(self.cura_mana_frame, text="%")
        self.l_4_1.pack(side = 'left', fill = 'x', expand = False)
        #Texto hotkey
        self.l_4_2 = ttk.Label(self.cura_mana_frame, text="HotKey:")
        self.l_4_2.pack(side = 'left', fill = 'x', expand = False)
        #Entrada hotkey cura maior
        self.e_4_1 = ttk.Entry(self.cura_mana_frame, width = 2)
        self.e_4_1.pack(side = 'left', fill = 'x', expand = False)
        self.e_4_1.insert(0,'f2')

class ButtonMenu(ttk.Frame):
    def __init__(self, parent, bt1_func, bt2_func):
        super().__init__(parent)
        self.pack(fill = 'both', expand = True, padx = 5, pady = 0)
        self.create_widgets(bt1_func, bt2_func)

    def create_widgets(self,bt1_func, bt2_func):
        #Cria botão Iniciar
        self.b_1 = ttk.Button(self, text="Iniciar Macro", command = bt1_func)
        self.b_1.pack(side = 'left', fill = 'x', expand = True)
        #Cria botão Parar
        self.b_2 = ttk.Button(self, text="Parar Macro", command = bt2_func)
        self.b_2.pack(side = 'left', fill = 'x', expand = True)

class TextMenu(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill = 'both', expand = True, padx = 5, pady = 5)
        self.create_widgets()


    def create_widgets(self):
        self.l_5 = ttk.Label(self,text=" Bem vindo ao macro!")
        self.l_5.pack(side = 'left', fill = 'x', expand = True)

class SuportSetup(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill = 'both', expand = True, padx = 5, pady = 5)
        self.create_widgets()

    def create_widgets(self):
        #Texto Hast -------------------------------------------------
        self.l_hast = ttk.Label(self, text="Hast:")
        self.l_hast.pack(side = 'left', fill = 'x')
        #Entrada hotkey hast
        self.e_hk_hast = ttk.Entry(self, width = 2)
        self.e_hk_hast.pack(side = 'left', fill = 'x', expand = False)
        self.e_hk_hast.insert(0,'f6')
        #check box
        self.cb_hast_var = tk.IntVar()
        self.cb_hast = tk.Checkbutton(self, variable = self.cb_hast_var, onvalue=1, offvalue=0)
        self.cb_hast.pack(side = 'left')
        #Texto Food -------------------------------------------------
        self.l_food = ttk.Label(self, text="Food:")
        self.l_food.pack(side = 'left', fill = 'x')
        #Entrada hotkey food
        self.e_hk_food = ttk.Entry(self, width = 2)
        self.e_hk_food.pack(side = 'left', fill = 'x', expand = False)
        self.e_hk_food.insert(0,'f5')
        #check box
        self.cb_food_var = tk.IntVar()
        self.cb_food = tk.Checkbutton(self, variable = self.cb_food_var, onvalue=1, offvalue=0)
        self.cb_food.pack(side = 'left')

App()
