import os
import re
import time
import random
import threading
import socket
import traceback
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
socket.setdefaulttimeout(15)

# ==========================================
# 1. 动态转圈防误触遮罩弹窗（已修复静默崩溃漏洞）
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
        # 【核心修复】必须使用 self.content 赋值，绝不能用 add_widget，防止静默阻断！
        self.content = self.loading_label 
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
        self.title = "视频打捞大师 终极排雷版"
        
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴视频播放网页网址 或 抓包获得的 Request URL:", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="任意支持的视频网页链接，或者包含 CLS-xxx.jpg 的切片请求地址...", 
            size_hint_y=None, 
            height=200  # 调整到更宽大的视野
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
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
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
    # 安全日志输出（放弃装饰器，采用原生强制主线程调度）
    # ==========================================
    def log(self, message):
        def _update(dt):
            self.log_label.text += str(message) + "\n"
        Clock.schedule_once(_update)

    def update_info(self, message):
        def _update(dt):
            self.info_label.text = str(message)
        Clock.schedule_once(_update)

    # ==========================================
    # 核心控制中枢：包裹天罗地网捕捉任意异常
    # ==========================================
    def start_smart_process(self, instance):
        try:
            raw_url = self.url_input.text.strip()
            if not raw_url:
                self.log("[错误] 输入框内容为空，请先粘贴网址。")
                return
                
            if self.is_downloading:
                self.log("[提示] 引擎轰鸣中，请勿重复点击。")
                return
                
            self.log("\n" + "="*30)
            self.log("[*] 智能分析链路已启动...")
            
            if re.search(r'CLS-\d+\.jpg', raw_url):
                self.log("[+] 检测到切片请求，并轨至下载流...")
                self.start_download_flow(raw_url)
            else:
                self.log("[+] 检测到普通网址，唤醒嗅探引擎...")
                # 如果是弹窗问题，下面的代码被 try 包裹，必将暴露！
                self.loading_popup = LoadingPopup()
                self.loading_popup.open()
                threading.Thread(target=self.async_web_parse, args=(raw_url,), daemon=True).start()
                
        except Exception as e:
            # 强行击穿 Kivy 静默保护机制，让死因大白天下
            err_msg = traceback.format_exc()
            self.log(f"\n[按钮触发致命崩溃]:\n{err_msg}")

    # ==========================================
    # 异步嗅探进程追踪
    # ==========================================
    def async_web_parse(self, page_url):
        self.log("[线程] 进入后台解析流水线...")
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'format': 'best',
            'nocheckcertificate': True,
            'socket_timeout': 15
        }
        try:
            self.log("[线程] yt-dlp 引擎启动分析...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(page_url, download=False)
                real_video_url = info_dict.get('url', None)
                
                if real_video_url:
                    Clock.schedule_once(lambda dt: self.on_parse_success(real_video_url))
                else:
                    Clock.schedule_once(lambda dt: self.on_parse_error("[错误] 嗅探完成，但未能提取到底层切片链接。"))
        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self.on_parse_error(f"[解析异常中断] {err}"))

    def on_parse_success(self, real_url):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.url_input.text = real_url
        self.log("[✔] 网页嗅探成功！已提取真实主链。")
        self.start_download_flow(real_url)

    def on_parse_error(self, error_msg):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.log(error_msg)
        self.log("[💡 建议] 若自动抓包失效，请使用浏览器 F12 捕获带有 CLS-xxx.jpg 的底层地址直接打捞。")

    # ==========================================
    # 下载分流控制
    # ==========================================
    def start_download_flow(self, url):
        if not self.parse_url_parameters(url):
            self.log("[❌ 打捞中止] 目标特征校验失败。")
            return
            
        self.is_downloading = True
        self.main_btn.disabled = True
        threading.Thread(target=self.download_logic, daemon=True).start()

    def parse_url_parameters(self, raw_url):
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            if not re.search(r'CLS-\d+\.jpg', path):
                self.log("[错误] 无法定位 CLS-xxx.jpg 切片特征。")
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
            
            self.update_info(f"【打捞环境就绪】\n域名: {parsed_url.netloc}\n保存至: {self.save_dir}")
            self.log("[+] 特征验证成功，缓存建立。")
            return True
        except Exception as e:
            self.log(f"[❌ 特征验证奔溃] {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
            "Referer": "https://rou.video/",
            "Connection": "keep-alive"
        })
        return session

    def download_worker(self, index):
        try:
            target_path = os.path.join(self.save_dir, f"CLS-{index:03d}.bin")
            if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
                return "EXISTS"
                
            url = self.base_url.format(index)
            session = self.create_session()
            time.sleep(random.uniform(0.1, 0.3))
            
            response = session.get(url, params=self.params, timeout=12, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            else:
                return "ERROR"
        except Exception as e:
            self.log(f"[网络异常] CLS-{index:03d}: {str(e)}")
            return "ERROR"
        finally:
            if 'session' in locals():
                session.close()

    def download_logic(self):
        try:
            self.log("[*] 高并发下载流水线启动...")
            for idx in range(1, 600):
                if not self.is_downloading:
                    break
                res = self.download_worker(idx)
                if res == "EOF":
                    if self.download_worker(idx + 1) == "EOF":
                        self.log(f"\n[✔] 捕获尾部信号，切片下载完毕！")
                        break
                elif res == "SUCCESS":
                    self.log(f"[+] 固化: CLS-{idx:03d}.bin")
                elif res == "EXISTS":
                    self.log(f"[-] 跳过重复: CLS-{idx:03d}.bin")
            self.log("\n[✔] 所有缓存固化完成，请点击【合并视频】。")
        except Exception as e:
            err_msg = traceback.format_exc()
            self.log(f"\n[线程致命崩溃]:\n{err_msg}")
        finally:
            self.is_downloading = False
            Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 下载路径为空或不存在。")
            return
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        
        if not files:
            self.log("[错误] 未侦测到可拼装的数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在将 {len(files)} 个片段物理拼装...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 拼装成功！已归档至系统下载目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并崩溃] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 文件保存在手机系统的【文件管理】->【Download】中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
