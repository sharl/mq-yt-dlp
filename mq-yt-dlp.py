# -*- coding: utf-8 -*-
import ctypes
import io
import json
import logging
import logging.handlers
import os
import subprocess
import threading
import time
import webbrowser

import tkinter as tk
from tkinter import ttk, messagebox
import sv_ttk           # extra

import darkdetect as dd
import pika
import pyperclip
import requests

from PIL import Image
from bs4 import BeautifulSoup as bs
from copy import copy
from pystray import Icon, Menu, MenuItem

APP_NAME = 'mq-yt-dlp'
CONFIG_FILE = 'url_settings.json'
BASE_URL = 'https://github.com/yt-dlp'
MAIN_QUEUE = 'yt-dlp'
FAIL_QUEUE = f'failed-{MAIN_QUEUE}'
EXCHANGE = ''
DLX_EXCHANGE = 'dlx_exchange'
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
PreferredAppMode = {
    'Light': 0,
    'Dark': 1,
}
# https://github.com/moses-palmer/pystray/issues/130
theme = dd.theme()
preferredappmode = PreferredAppMode[theme]
ctypes.windll['uxtheme.dll'][135](preferredappmode)


def load_safe_prefixes():
    default = [
        'https://www.youtube.com/watch?',
        'https://www.youtube.com/shorts/',
        'https://www.youtube.com/playlist?list=',
        'https://youtu.be/',
        'https://tver.jp/episodes/',
        'https://www.nicovideo.jp/watch/',
        'https://abema.tv/video/episode/',
    ]
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default


# グローバル変数として保持（Producerが参照する）
safe_url_prefixes = load_safe_prefixes()


def apply_theme_style(root):
    """OSのテーマに合わせてsv_ttkとタイトルバーを適用する"""
    sv_ttk.set_theme(theme.lower())
    # DWMの属性に対応
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    cValue = ctypes.c_int(preferredappmode)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(cValue),
        ctypes.sizeof(cValue),
    )


class SettingsWindow:
    def __init__(self, on_save_callback):
        self.on_save_callback = on_save_callback

        FONT_SIZE = 14
        FONT_MONO = 'Consolas'

        self.root = tk.Tk()
        self.root.title('URL Prefixes Settings')
        self.root.minsize(500, 500)

        # OSテーマ適用
        apply_theme_style(self.root)

        # ttkウィジェットのスタイルを一括設定
        style = ttk.Style()
        # Entry, Button, Label(ttk版) のフォントを統一
        style.configure('TButton', font=(FONT_MONO, FONT_SIZE))
        style.configure('Accent.TButton', font=(FONT_MONO, FONT_SIZE, 'bold'))
        style.configure('TLabel', font=(FONT_MONO, FONT_SIZE, 'bold'))
        style.configure('TEntry', font=(FONT_MONO, FONT_SIZE))

        # メインフレーム
        main_frame = ttk.Frame(self.root, padding='20')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ラベル (ttk.Label を使うことで style が効く)
        ttk.Label(main_frame, text='Safe URL Prefixes:').pack(anchor='w', pady=(0, 5))

        # リストボックス
        # highlightcolor を指定するとフォーカス時に綺麗になります
        self.listbox = tk.Listbox(
            main_frame,
            width=60,
            height=10,
            relief='flat',
            borderwidth=0,
            highlightthickness=1,
            font=(FONT_MONO, FONT_SIZE),
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        # 入力エリア
        self.entry = ttk.Entry(main_frame, font=(FONT_MONO, FONT_SIZE))
        self.entry.bind('<Return>', lambda e: self.add())
        self.entry.pack(fill=tk.X, pady=10)

        # ボタンエリア
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text='Add New', command=self.add).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text='Update', command=self.update_item).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text='Delete', command=self.delete).pack(side=tk.LEFT, padx=2)

        # 保存ボタン
        ttk.Button(
            main_frame,
            text='Save & Close',
            style='Accent.TButton',
            command=self.save,
        ).pack(fill=tk.X, pady=(20, 0))

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

        global safe_url_prefixes
        for p in safe_url_prefixes:
            self.listbox.insert(tk.END, p)

        self.root.mainloop()

    def on_select(self, event):
        """リストが選択されたらEntryに値を表示する"""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            value = self.listbox.get(index)
            self.entry.delete(0, tk.END)
            self.entry.insert(0, value)

    def add(self):
        """新規追加"""
        val = self.entry.get().strip()
        if val:
            self.listbox.insert(tk.END, val)
            self.entry.delete(0, tk.END)

    def update_item(self):
        """選択中の項目をEntryの内容で上書きする"""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            val = self.entry.get().strip()
            if val:
                self.listbox.delete(index)
                self.listbox.insert(index, val)
                self.listbox.select_set(index)          # 選択状態を維持
        else:
            messagebox.showinfo('Info', '更新する項目を一覧から選択してください。')

    def delete(self):
        """削除"""
        sel = self.listbox.curselection()
        if sel:
            self.listbox.delete(sel)
            self.entry.delete(0, tk.END)

    def save(self):
        new_list = list(self.listbox.get(0, tk.END))
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_list, f, indent=4, ensure_ascii=False)
        self.on_save_callback(new_list)
        self.on_close()

    def on_close(self):
        self.root.quit()
        self.root.destroy()


logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(f'log_{APP_NAME}.log', maxBytes=1000000, backupCount=0),
        logging.StreamHandler(),
    ],
    datefmt='%x %X'
)
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.DEBUG)


def waitForNewPaste(timeout=0):
    current = pyperclip.paste()
    start = time.monotonic()
    while True:
        time.sleep(0.1)
        text = pyperclip.paste()
        if text != current:
            return text
        if timeout > 0 and time.monotonic() - start > timeout:
            raise pyperclip.PyperclipTimeoutException(f'waitForNewPaste() timed out after {timeout} seconds.')


class Producer:
    def __init__(self, timeout=0):
        message = str()
        try:
            message = waitForNewPaste(timeout=timeout)
        except pyperclip.PyperclipTimeoutException:
            return

        try:
            for line in message.split():
                url = line.strip()
                if url.startswith(tuple(safe_url_prefixes)):
                    try:
                        with pika.BlockingConnection(pika.ConnectionParameters(host='127.0.0.1')) as connection:
                            channel = connection.channel()
                            channel.queue_declare(
                                queue=MAIN_QUEUE,
                                durable=True,
                                arguments={
                                    'x-dead-letter-exchange': DLX_EXCHANGE,
                                    'x-dead-letter-routing-key': MAIN_QUEUE,
                                }
                            )
                            properties = pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE)
                            channel.basic_publish(exchange=EXCHANGE, routing_key=MAIN_QUEUE, body=url, properties=properties)

                        logger.info(f'{self.__class__.__name__} pub {url}')
                    except Exception as e:
                        logger.warning(f'{self.__class__.__name__} Exception: {e}')
        except Exception as e:
            logger.warning(f'{self.__class__.__name__} Exception: {e}')


class Consumer:
    def __init__(self, app, icon_normal, icon_active, icon_pause, pause):
        # アイコンの切り替えが必要な場合のみ代入する
        target_icon = icon_pause if pause else icon_normal
        if app.icon != target_icon:
            app.icon = target_icon
            # アイコンを変えたときはメニュー更新不要（タイトルを変えたときだけでOK）

        if pause:
            return

        try:
            # ignore heartbeat
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='127.0.0.1', heartbeat=0))

            self.channel = connection.channel()
            self.channel.exchange_declare(exchange=DLX_EXCHANGE, exchange_type='direct')
            self.channel.queue_declare(queue=FAIL_QUEUE, durable=True)
            self.channel.queue_bind(exchange=DLX_EXCHANGE, queue=FAIL_QUEUE, routing_key=MAIN_QUEUE)
            self.channel.queue_declare(
                queue=MAIN_QUEUE,
                durable=True,
                arguments={
                    'x-dead-letter-exchange': DLX_EXCHANGE,
                    'x-dead-letter-routing-key': MAIN_QUEUE,
                }
            )

            try:
                method_frame, header_frame, body = self.channel.basic_get(MAIN_QUEUE)
                if method_frame:
                    url = body.decode()
                    if url.startswith('http'):
                        logger.info(f'{self.__class__.__name__} job start {url}')
                        app.title = f'downloading {url}'
                        app.icon = icon_active
                        app.update_menu()

                        start = time.time()
                        r = subprocess.run(
                            ['wsl', '/home/linuxbrew/.linuxbrew/bin/yt-dlp', '-q', f"'{url}'"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        end = time.time()

                        print(r)
                        if r.returncode == 0:
                            logger.info(f'{self.__class__.__name__} job finished {end - start}s')
                            self.channel.basic_ack(method_frame.delivery_tag)
                        else:
                            logger.warning(f'{self.__class__.__name__} job failed {url}')
                            self.channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=False)
                    else:
                        time.sleep(0.1)

                    app.title = APP_NAME
                    app.icon = icon_normal
                    app.update_menu()
            except Exception as e:
                logger.warning(f'{self.__class__.__name__} Exception: {e}')

        except Exception as e:
            logger.warning(f'{self.__class__.__name__} Exception: {e}')


class taskTray:
    def __init__(self):
        self.running = False
        self.pause = False
        session = requests.Session()
        with session.get(BASE_URL) as r:
            soup = bs(r.content, 'html.parser')
            img_tag = soup.find('img', itemprop='image')
            avatar_url = img_tag.get('src') if img_tag else None
            if avatar_url:
                self.icon_image = Image.open(io.BytesIO(session.get(avatar_url).content))
                self.icon_active = copy(self.icon_image)
                self.icon_pause = copy(self.icon_image)
                w, h = self.icon_image.size
                color = self.icon_image.getpixel((w // 2, 0))
                replace_active = (255, 0, 0, 255)
                replace_pause = (0, 0, 255, 255)
                for y in range(h):
                    for x in range(w):
                        if self.icon_image.getpixel((x, y)) == color:
                            self.icon_active.putpixel((x, y), replace_active)
                            self.icon_pause.putpixel((x, y), replace_pause)

        menu = Menu(
            MenuItem('Open RabbitMQ manager', self.doOpen),
            MenuItem('Settings', self.openSettings),
            MenuItem('Pause', self.togglePause, default=True, checked=lambda _: self.pause),
            MenuItem('Exit', self.stopApp),
        )
        self.app = Icon(name=f'PYTHON.win32.{APP_NAME}', title=APP_NAME, icon=self.icon_image, menu=menu)

    def doOpen(self):
        webbrowser.open('http://localhost:15672')

    def openSettings(self):
        # 既に開いている場合に重複して開かないためのガード
        if hasattr(self, 'settings_window_active') and self.settings_window_active:
            return

        # Tkinterを別スレッドで実行する
        thread = threading.Thread(target=self._run_settings_ui, daemon=True)
        thread.start()

    def _run_settings_ui(self):
        self.settings_window_active = True
        # スレッド内でTkインスタンスを作成
        SettingsWindow(self.update_prefixes)
        self.settings_window_active = False

    def update_prefixes(self, new_list):
        global safe_url_prefixes
        safe_url_prefixes = new_list
        logger.info('URL Prefixes updated.')

    def togglePause(self):
        self.pause = not self.pause
        self.app.update_menu()

    def pub(self):
        logger.info('pub start')

        while self.running:
            Producer(timeout=1)

        logger.info('pub done')

    def sub(self):
        logger.info('sub start')
        last_pause_state = self.pause

        while self.running:
            # 状態が変わったときだけメニューを更新する
            if last_pause_state != self.pause:
                self.app.update_menu()
                last_pause_state = self.pause

            Consumer(self.app, self.icon_image, self.icon_active, self.icon_pause, self.pause)
            time.sleep(1)

        logger.info('sub done')

    def stopApp(self):
        self.running = False
        self.app.stop()

    def runApp(self):
        self.running = True

        pub_thread = threading.Thread(target=self.pub)
        pub_thread.start()

        sub_thread = threading.Thread(target=self.sub)
        sub_thread.start()

        self.app.run()


if __name__ == '__main__':
    # 高DPIを自前で処理
    try:
        # https://learn.microsoft.com/ja-jp/windows/win32/api/shellscalingapi/ne-shellscalingapi-process_dpi_awareness
        # PROCESS_DPI_UNAWARE = 0,
        # PROCESS_SYSTEM_DPI_AWARE = 1,
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    taskTray().runApp()
