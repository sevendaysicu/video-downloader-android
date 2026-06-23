import os
import re
import time
import random
import threading
from urllib.parse import urlparse, parse_qs

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.popup import Popup

# 引入中文字体
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

import yt_dlp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LoadingPopup(Popup):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "请稍候"
        self.size_hint = (0.7, 0.4)
        self.auto_dismiss = False 
        self.spinner_chars = ['-', '\\', '|', '/']
        self.char_index = 0
        self.loading_label = Label(text="正在全速解析底层切片...", font_size=16)
        self.content = self.loading_label 
        self.update_event = Clock.schedule_interval(self.update_spinner, 0.1)

    def update_spinner(self, dt):
        self.char_index = (self.char_index + 1) % len(self.spinner_chars)
        self.loading_label.text = f"正在伪装浏览器抓包...\n\n           {self.spinner_chars[self.char_index]}"

    def close_animation(self):
        self.update_event.cancel()
        self.dismiss()

class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 永不闪退版"
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴播放网址 或 完整的切片请求URL:", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="示例 1: https://rou.video/video/123\n示例 2: https://cdn.xxx.com/hls/CLS-001.jpg?v=6", 
            size_hint_y=None, 
            height=300
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(text="[引擎就绪：等待输入指令]", size_hint_y=None, height=120, halign="left", valign="top")
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
        self.log_label = Label(text="运行日志:\n", size_hint_y=None, halign="left", valign="top")
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    @mainthread
    def log(self, message):
        lines = self.log_label.text.split('\n')
        lines.append(str(message))
        if len(lines) > 40:
            lines = lines[-40:]
        self.log_label.text = '\n'.join(lines)

    @mainthread
    def update_info(self, message):
        self.info_label.text = str(message)

    def start_smart_process(self, instance):
        try:
            raw_url = self.url_input.text.strip()
            if not raw_url:
                self.log("[错误] 输入框为空！")
                return
            if self.is_downloading:
                return
                
            self.log("\n" + "="*30)
            
            # 安全检查：必须含有 http 开头
            if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                self.log("[❌ 阻断] 链接格式不合法！")
                self.log("必须包含完整的 http:// 或 https:// 开头。")
                return
            
            # 判断是否包含完整的域名
            parsed = urlparse(raw_url)
            if not parsed.netloc or '.' not in parsed.netloc:
                self.log("[❌ 阻断] 检测到残缺网址！")
                self.log("网址中缺少有效的服务器域名部分，请重新复制完整的 Request URL。")
                return

            self.log("[*] 智能分析链路已启动...")
            
            # 如果本身就是带有 CLS 切片特征的链接，直接进下载流
            if re.search(r'CLS-\d+\.jpg', raw_url):
                self.start_download_flow(raw_url)
            else:
                # 否则说明输入的是普通网页，启动后台嗅探
                self.loading_popup = LoadingPopup()
                self.loading_popup.open()
                threading.Thread(target=self.async_web_parse, args=(raw_url,), daemon=True).start()
                
        except Exception as e:
            self.log(f"\n[主控异常]: {str(e)}")

    def async_web_parse(self, page_url):
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'best', 'nocheckcertificate': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(page_url, download=False)
                # 【核心加固】使用 .get() 且提供默认值，坚决防止 KeyError
                real_video_url = info_dict.get('url', None) if info_dict else None
                
                if real_video_url:
                    Clock.schedule_once(lambda dt: self.on_parse_success(real_video_url))
                else:
                    Clock.schedule_once(lambda dt: self.on_parse_error("[提示] 该网页有强加密混淆，无法自动嗅探。请使用抓包工具获取完整的 CLS-xxx.jpg 请求地址直接粘贴进来下载。"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.on_parse_error(f"[解析限制] 该网站限制了自动化工具抓包。\n建议：请使用黄鸟抓取包含“CLS-xxx.jpg”的完整长链接贴进来。"))

    def on_parse_success(self, real_url):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.url_input.text = real_url
        self.log("[✔] 网页嗅探成功！即将开始打捞...")
        self.start_download_flow(real_url)

    def on_parse_error(self, error_msg):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.log(error_msg)

    def start_download_flow(self, url):
        if not self.parse_url_parameters(url):
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
            self.update_info(f"【环境就绪】服务器: {parsed_url.netloc}\n目录: {self.save_dir}")
            return True
        except Exception as e:
            self.log(f"[特征解析失败] {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
            return "ERROR"
        finally:
            if 'session' in locals():
                session.close()

    def download_logic(self):
        try:
            self.log("[*] 下载流水线已接通...")
            error_count = 0
            
            for idx in range(1, 600):
                if not self.is_downloading:
                    break
                res = self.download_worker(idx)
                
                if res == "EOF":
                    if self.download_worker(idx + 1) == "EOF":
                        self.log(f"\n[✔] 侦测到尾部边界，打捞完毕！")
                        break
                elif res == "SUCCESS":
                    self.log(f"[+] 下载完成: CLS-{idx:03d}.bin")
                    error_count = 0
                elif res == "EXISTS":
                    self.log(f"[-] 跳过已存在: CLS-{idx:03d}.bin")
                    error_count = 0
                elif res == "ERROR":
                    error_count += 1
                    if error_count >= 5:
                        self.log("\n[🚫 熔断] 连续5次请求无响应，已自动阻断防护。")
                        break
                        
            self.log("\n[✔] 任务结束。请点击【合并视频】生成MP4。")
        except Exception as e:
            self.log(f"\n[运行异常]: {str(e)[:50]}")
        finally:
            self.is_downloading = False
            Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 找不到可合并的数据目录。")
            return
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        if not files:
            self.log("[错误] 目录内没有检测到有效数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在组装 {len(files)} 个片段...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 视频生成成功！保存在:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并失败] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 文件已安全存入系统【内部存储】->【Download】文件夹。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
