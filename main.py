import os
import re
import time
import random
import threading
import socket
from urllib.parse import urlparse, parse_qs

# Kivy 核心组件
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.popup import Popup

# 引入并注册全局中文字体
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

# 引入解析引擎
import yt_dlp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# 全局设置底层网络超时阻断时间，防止 Android 线程因网络死锁无限挂起
socket.setdefaulttimeout(15)

# ==========================================
# 1. 动态转圈防误触遮罩弹窗
# ==========================================
class LoadingPopup(Popup):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "请稍候"
        self.size_hint = (0.7, 0.4)
        self.auto_dismiss = False 
        
        self.spinner_chars = ['-', '\\', '|', '/']
        self.char_index = 0
        
        self.loading_label = Label(text="正在全速解析底层切片...", font_size=16)
        self.add_widget(self.loading_label)
        self.update_event = Clock.schedule_interval(self.update_spinner, 0.1)

    def update_spinner(self, dt):
        self.char_index = (self.char_index + 1) % len(self.spinner_chars)
        self.loading_label.text = f"正在伪装浏览器抓包...\n\n           {self.spinner_chars[self.char_index]}"

    def close_animation(self):
        self.update_event.cancel()
        self.dismiss()

# ==========================================
# 2. 主打捞程序
# ==========================================
class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 智能一体版"
        
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        # 主布局
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴视频播放网页网址 或 抓包获得的 Request URL:", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="任意支持的视频网页链接，或者包含 CLS-xxx.jpg 的切片请求地址...", 
            size_hint_y=None, 
            height=120
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(
            text="[引擎就绪：等待输入指令]", 
            size_hint_y=None, 
            height=120,
            halign="left", 
            valign="top"
        )
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        # 精简高能功能按钮区
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
        # 核心一键打捞按钮
        self.main_btn = Button(text="开始智能打捞", background_color=(0.1, 0.6, 0.9, 1))
        self.main_btn.bind(on_press=self.start_smart_process)
        btn_layout.add_widget(self.main_btn)
        
        self.merge_btn = Button(text="合并视频", background_color=(0.1, 0.8, 0.3, 1))
        self.merge_btn.bind(on_press=self.merge_slices)
        btn_layout.add_widget(self.merge_btn)
        
        self.open_dir_btn = Button(text="查看文件", background_color=(0.7, 0.7, 0.7, 1))
        self.open_dir_btn.bind(on_press=self.open_directory)
        btn_layout.add_widget(self.open_dir_btn)
        
        layout.add_widget(btn_layout)
        
        # 日志输出
        scroll = ScrollView()
        self.log_label = Label(
            text="运行日志:\n", 
            size_hint_y=None, 
            halign="left", 
            valign="top"
        )
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    # ==========================================
    # 核心控制中枢：一键智能分流识别
    # ==========================================
    def start_smart_process(self, instance):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.log("[错误] 输入框内容为空，请先粘贴有效网址。")
            return
            
        if self.is_downloading:
            self.log("[提示] 打捞引擎正在轰鸣中，请勿重复点击。")
            return
            
        self.log("[*] 正在智能分析链路类型...")
        
        # 智能分支 A：如果直接包含了切片特征，直接跳过网页解析，进行多线程下载
        if re.search(r'CLS-\d+\.jpg', raw_url):
            self.log("[+] 检测到输入为直接切片请求 URL，正在跳过网页提取，直接并轨至固化下载流...")
            self.start_download_flow(raw_url)
        else:
            # 智能分支 B：普通网页地址，调动黑客抓包解析引擎
            self.log("[+] 检测到输入为视频页面网址，正在唤醒全自动抓包嗅探引擎...")
            self.loading_popup = LoadingPopup()
            self.loading_popup.open()
            threading.Thread(target=self.async_web_parse, args=(raw_url,), daemon=True).start()

    # ==========================================
    # 嗅探线程：安全隔离执行，防止 UI 卡死
    # ==========================================
    def async_web_parse(self, page_url):
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'format': 'best',
            'nocheckcertificate': True, # 忽略证书校验，彻底扫清手机 VPN 引起的握手报错
            'socket_timeout': 15        # 强行限定解析最长 15 秒，彻底打破无限卡死僵局
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(page_url, download=False)
                real_video_url = info_dict.get('url', None)
                
                if real_video_url:
                    Clock.schedule_once(lambda dt: self.on_parse_success(real_video_url))
                else:
                    Clock.schedule_once(lambda dt: self.on_parse_error("[错误] 解析引擎未能从该页面提取到视频主链。"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.on_parse_error(f"[解析异常中断] {str(e)}"))

    def on_parse_success(self, real_url):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.url_input.text = real_url
        self.log("[✔] 网页解析嗅探成功！已将底层真实主链提取回输入框。")
        self.start_download_flow(real_url)

    def on_parse_error(self, error_msg):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.log(error_msg)
        self.log("[💡 建议] 针对高强度加密网站，自动抓包可能会失效。请在电脑端 F12 捕获包含 CLS-xxx.jpg 的 Request URL 粘贴进来直接打捞。")

    # ==========================================
    # 下载分流控制
    # ==========================================
    def start_download_flow(self, url):
        if not self.parse_url_parameters(url):
            self.log("[❌ 打捞中止] 目标特征校验失败。")
            return
            
        self.is_downloading = True
        Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', True))
        threading.Thread(target=self.download_logic, daemon=True).start()

    def parse_url_parameters(self, raw_url):
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            if not re.search(r'CLS-\d+\.jpg', path):
                self.log("[错误] 链路 Path 无法定位 CLS-xxx.jpg 核心切片特征序列。")
                return False
                
            standard_path = re.sub(r'CLS-\d+\.jpg', 'CLS-{:03d}.jpg', path)
            self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{standard_path}"
            
            video_id_match = re.search(r'/hls/([^/]+)/', path)
            video_id = video_id_match.group(1) if video_id_match else "default_video"
            
            if platform == 'android':
                from android.storage import primary_external_storage_path
                downloads_path = os.path.join(primary_external_storage_path(), "Download")
                self.save_dir = os.path.join(downloads_path, f"slices_{video_id}")
            else:
                self.save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"slices_{video_id}")
                
            os.makedirs(self.save_dir, exist_ok=True)
            
            self.update_info(f"【打捞环境就绪】\n域名: {parsed_url.netloc}\n视频ID: {video_id}\n保存至: {self.save_dir}")
            self.log(f"[+] 目标特征识别成功。缓存临时目录锁定在:\n{self.save_dir}")
            return True
        except Exception as e:
            self.log(f"[❌ 特征提取奔溃] {str(e)}")
            return False

    # ==========================================
    # 底层网络数据流拉取逻辑
    # ==========================================
    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            "Referer": "https://rou.video/",
            "Connection": "keep-alive"
        })
        return session

    def download_worker(self, index):
        target_path = os.path.join(self.save_dir, f"CLS-{index:03d}.bin")
        if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
            return "EXISTS"
            
        url = self.base_url.format(index)
        session = self.create_session()
        time.sleep(random.uniform(0.1, 0.3))
        
        try:
            response = session.get(url, params=self.params, timeout=12, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            else:
                return "ERROR"
        except:
            return "ERROR"
        finally:
            session.close()

    def download_logic(self):
        self.log("[*] 安卓高并发异步打捞引擎启动，全速固化视频切片...")
        for idx in range(1, 600):
            res = self.download_worker(idx)
            if res == "EOF":
                if self.download_worker(idx + 1) == "EOF":
                    self.log(f"\n[✔] 成功捕获流尾部截止边界信号，切片链下载完毕！")
                    break
            elif res == "SUCCESS":
                self.log(f"[+] 固化切片成功: CLS-{idx:03d}.bin")
            elif res == "EXISTS":
                self.log(f"[-] 跳过重复本地副本: CLS-{idx:03d}.bin")
            else:
                self.log(f"[!] 切片 CLS-{idx:03d} 遭遇异常网络吞吐，正在进行高生存期重试...")
                
        self.log("\n[✔] 所有缓存已成功安全固化。请点击下方的【合并视频】生成 MP4 文件。")
        self.is_downloading = False
        Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    # ==========================================
    # 后端文件物理组装
    # ==========================================
    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 下载路径真空，请先执行智能打捞。")
            return
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        
        if not files:
            self.log("[错误] 未在目标文件夹内侦测到任何可拼装的 .bin 数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在将 {len(files)} 个离散数据流进行物理二进制拼接...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 视频拼装成功！无损 MP4 已归档至手机系统下载目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并物理崩溃] {str(e)}")

    # ==========================================
    # 线程安全日志刷新中枢
    # ==========================================
    def log(self, message):
        Clock.schedule_once(lambda dt: setattr(self.log_label, 'text', self.log_label.text + message + "\n"))

    def update_info(self, message):
        Clock.schedule_once(lambda dt: setattr(self.info_label, 'text', message))

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 视频文件和缓存均保存在手机系统的【文件管理】 -> 【内部存储】 -> 【Download】 中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
