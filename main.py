import os
import re
import time
import random
import threading
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
# 引入并注册全局中文字体
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')  # 注意：这里的 'font.ttf' 要和上传的字体文件名完全一致

# 网络库
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 Android版"
        
        # 核心下载数据
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        # 请求安卓存储权限 (Android 6.0+)
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        # 主布局 (垂直排列)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # 1. 标题与输入框
        layout.add_widget(Label(text="请粘贴完整的切片请求网址 (Request URL):", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="https://v.rn.../CLS-001.jpg?v=6...", 
            size_hint_y=None, 
            height=120
        )
        layout.add_widget(self.url_input)
        
        # 2. 解析信息展示区
        self.info_label = Label(
            text="[等待解析参数...]", 
            size_hint_y=None, 
            height=160,
            halign="left", 
            valign="top"
        )
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        # 3. 功能按钮区
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
        self.download_btn = Button(text="🚀 下载切片", background_color=(0.1, 0.6, 0.9, 1))
        self.download_btn.bind(on_press=self.start_download_thread)
        btn_layout.add_widget(self.download_btn)
        
        self.merge_btn = Button(text="🎬 合并视频", background_color=(0.1, 0.8, 0.3, 1))
        self.merge_btn.bind(on_press=self.merge_slices)
        btn_layout.add_widget(self.merge_btn)
        
        self.open_dir_btn = Button(text="📂 查看文件", background_color=(0.7, 0.7, 0.7, 1))
        self.open_dir_btn.bind(on_press=self.open_directory)
        btn_layout.add_widget(self.open_dir_btn)
        
        layout.add_widget(btn_layout)
        
        # 4. 滚动日志输出区
        scroll = ScrollView()
        self.log_label = Label(
            text="运行日志:\n", 
            size_hint_y=None, 
            halign="left", 
            valign="top"
        )
        self.log_label.bind(size=self.log_label.setter('text_size'))
        # 监听文本高度变化以实现自动滚动
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    def log(self, message):
        # Kivy 要求在主线程中更新 UI
        Clock.schedule_once(lambda dt: setattr(self.log_label, 'text', self.log_label.text + message + "\n"))

    def update_info(self, message):
        Clock.schedule_once(lambda dt: setattr(self.info_label, 'text', message))

    def parse_url(self):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.update_info("❌ 错误：网址不能为空")
            return False
            
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            if not re.search(r'CLS-\d+\.jpg', path):
                self.update_info("❌ 错误：无法定位 CLS-xxx.jpg 序列")
                return False
                
            standard_path = re.sub(r'CLS-\d+\.jpg', 'CLS-{:03d}.jpg', path)
            self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{standard_path}"
            
            video_id_match = re.search(r'/hls/([^/]+)/', path)
            video_id = video_id_match.group(1) if video_id_match else "default_video"
            
            # 设置安卓系统的公共下载目录 (Environment.DIRECTORY_DOWNLOADS)
            if platform == 'android':
                from android.storage import primary_external_storage_path
                downloads_path = os.path.join(primary_external_storage_path(), "Download")
                self.save_dir = os.path.join(downloads_path, f"slices_{video_id}")
            else:
                # 电脑测试环境
                self.save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"slices_{video_id}")
                
            os.makedirs(self.save_dir, exist_ok=True)
            
            self.update_info(
                f"【解析成功】\n域名: {parsed_url.netloc}\n视频ID: {video_id}\n保存至目录: {self.save_dir}"
            )
            return True
        except Exception as e:
            self.update_info(f"❌ 解析异常: {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        # 安卓局域网代理支持（如果手机挂了本地代理，可以去掉或调整此处的端口配置）
        session.proxies = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
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
        time.sleep(random.uniform(0.2, 0.4))
        
        try:
            response = session.get(url, params=self.params, timeout=15, verify=False)
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

    def start_download_thread(self, instance):
        if self.is_downloading or not self.parse_url():
            return
        self.is_downloading = True
        self.download_btn.disabled = True
        threading.Thread(target=self.download_logic, daemon=True).start()

    def download_logic(self):
        self.log("[*] 安卓异步打捞引擎启动...")
        # 循环下载
        for idx in range(1, 600):
            res = self.download_worker(idx)
            if res == "EOF":
                # 再次校验确认结束
                if self.download_worker(idx + 1) == "EOF":
                    self.log(f"\n[✔] 成功捕获尾部信号，切片下载完成！")
                    break
            elif res == "SUCCESS":
                self.log(f"[+] 固化切片: CLS-{idx:03d}.bin")
            elif res == "EXISTS":
                self.log(f"[-] 跳过已存在切片: CLS-{idx:03d}.bin")
            else:
                self.log(f"[X] 切片 CLS-{idx:03d} 异常，重试中...")
                
        self.log("\n[✔] 缓存全部固化。请点击【合并视频】。")
        self.is_downloading = False
        self.download_btn.disabled = False

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[X] 错误：未找到下载路径")
            return
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        
        if not files:
            self.log("[X] 错误：没有检测到可合并的切片")
            return
            
        # 合并到手机 Downloads 公共目录下
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在物理拼装 {len(files)} 个数据流...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 视频拼装成功！保存在手机系统下载目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[X] 合并失败: {str(e)}")

    def open_directory(self, instance):
        # 浏览视频目录，如果是安卓，提示去系统文件管理器查看 Download 文件夹
        if platform == 'android':
            self.log("\n[📂 提示] 视频和缓存均保存在手机系统自带的【文件管理】 -> 【内部存储】 -> 【Download】 文件夹中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
