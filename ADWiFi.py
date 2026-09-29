

import os
import io
import sys
import csv
import math
import time
import wave
import socket
import struct
import platform
import tempfile
import subprocess
import threading
import ipaddress
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

try:
    import requests
except ImportError:
    requests = None

try:
    from scapy.all import ARP, Ether, srp
    SCAPY_AVAILABLE = True
except Exception:
    SCAPY_AVAILABLE = False


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")


def play_beep(frequency=750, duration_ms=300, volume=0.5):
    """يولّد نغمة (sine wave) وملف WAV مؤقت ويشغّله — يعمل بدون مكتبات خارجية إضافية."""
    framerate = 44100
    n_samples = int(framerate * duration_ms / 1000)
    amplitude = int(32767 * volume)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        for i in range(n_samples):
            value = int(amplitude * math.sin(2 * math.pi * frequency * (i / framerate)))
            wf.writeframesraw(struct.pack("<h", value))

    tmp_path = os.path.join(tempfile.gettempdir(), "adeeb_beep.wav")
    with open(tmp_path, "wb") as f:
        f.write(buf.getvalue())

    _play_audio_file(tmp_path)


def _play_audio_file(path):
    system = platform.system().lower()
    try:
        if "windows" in system:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
        elif "darwin" in system:  # macOS
            subprocess.run(["afplay", path])
        else:  # Linux
            player = None
            for candidate in ("paplay", "aplay", "ffplay"):
                if subprocess.call(["which", candidate], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                    player = candidate
                    break
            if player == "ffplay":
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
            elif player:
                subprocess.run([player, path])
            else:
                print("\a")  # جرس الطرفية كحل أخير
    except Exception:
        print("\a")


def ring_three_times():
    for _ in range(3):
        play_beep(frequency=850, duration_ms=250)
        time.sleep(0.15)


def speak(message):
    """نطق عربي موثوق قدر الإمكان، بدون إيقاف واجهة البرنامج."""
    try:
        # gTTS + pygame إن كانت المكتبة متوفرة.
        from gtts import gTTS
        import tempfile
        import uuid

        filename = os.path.join(
            tempfile.gettempdir(),
            f"adeeb_tts_{uuid.uuid4().hex}.mp3"
        )
        gTTS(text=message, lang="ar", slow=False).save(filename)

        try:
            from playsound import playsound
            playsound(filename)
        except Exception:
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(filename)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
            except Exception:
                # Windows SAPI fallback
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 155)
                    engine.say(message)
                    engine.runAndWait()
                except Exception:
                    print(message)

        try:
            os.remove(filename)
        except Exception:
            pass

    except Exception:
        # آخر حل: Windows SAPI، ثم عرض النص في الطرفية.
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 155)
            engine.say(message)
            engine.runAndWait()
        except Exception:
            print(message)

def intro_sequence():
    """نطق الافتتاحية + 3 رنّات — تعمل في Thread منفصل حتى لا تُجمّد الواجهة."""
    speak("جار مسح الشبكة المحلية بواسطة خادم أديب يرجى الانتظار")
    ring_three_times()


#الشبكة الحقيقية 
def get_local_ip_and_subnet():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = socket.gethostbyname(socket.gethostname())
    parts = local_ip.split(".")
    return local_ip, ".".join(parts[:3]) + ".0/24"


def get_public_ip():
    """IP العام الحقيقي لشبكتك (كل الأجهزة خلف الراوتر تشترك بنفس IP العام بسبب NAT)."""
    if requests is None:
        return "غير متاح (مكتبة requests غير مثبّتة)"
    endpoints = ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]
    for url in endpoints:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception:
            continue
    return "غير متاح (تحقق من الاتصال بالإنترنت)"


def arp_scan_scapy(subnet_cidr, timeout=2):
    arp = ARP(pdst=subnet_cidr)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    result = srp(ether / arp, timeout=timeout, verbose=0)[0]
    return [{"ip": r.psrc, "mac": r.hwsrc.upper()} for _, r in result]


def arp_table_fallback():
    system = platform.system().lower()
    devices = []
    try:
        if "windows" in system:
            output = subprocess.check_output("arp -a", shell=True, text=True, errors="ignore")
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].count(".") == 3 and ("-" in parts[1] or ":" in parts[1]):
                    devices.append({"ip": parts[0], "mac": parts[1].upper().replace("-", ":")})
        else:
            output = subprocess.check_output(["arp", "-an"], text=True, errors="ignore")
            for line in output.splitlines():
                if "(" in line and ")" in line and " at " in line:
                    ip = line.split("(")[1].split(")")[0]
                    mac_part = line.split(" at ")[1].split(" ")[0]
                    if ":" in mac_part:
                        devices.append({"ip": ip, "mac": mac_part.upper()})
    except Exception:
        pass
    return devices


def ping_sweep(subnet_cidr, max_workers=40):
    network = ipaddress.ip_network(subnet_cidr, strict=False)
    system = platform.system().lower()
    param = "-n" if "windows" in system else "-c"
    timeout_param = "-w" if "windows" in system else "-W"
    timeout_val = "500" if "windows" in system else "1"

    def ping_one(ip):
        try:
            subprocess.run(["ping", param, "1", timeout_param, timeout_val, str(ip)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    threads = []
    for ip in network.hosts():
        t = threading.Thread(target=ping_one, args=(ip,))
        t.start()
        threads.append(t)
        if len(threads) >= max_workers:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()


def discover_devices(subnet_cidr):
    if SCAPY_AVAILABLE:
        try:
            devices = arp_scan_scapy(subnet_cidr)
            if devices:
                return devices, "scapy (ARP scan مباشر)"
        except Exception:
            pass
    ping_sweep(subnet_cidr)
    return arp_table_fallback(), "ping sweep + جدول ARP (شغّل بصلاحية root/admin لدقّة أعلى)"


OFFLINE_OUI = {
    "3C:5A:B4": "Google, Inc.", "F4:F5:D8": "Google, Inc.", "00:1A:11": "Google, Inc.",
    "AC:37:43": "Apple, Inc.", "F0:18:98": "Apple, Inc.", "A4:83:E7": "Apple, Inc.", "00:1B:63": "Apple, Inc.",
    "B8:27:EB": "Raspberry Pi Foundation", "DC:A6:32": "Raspberry Pi Foundation",
    "F8:32:E4": "Samsung Electronics", "8C:79:F5": "Samsung Electronics",
    "FC:A1:83": "TP-Link Technologies",
    "00:0C:29": "VMware, Inc.", "00:1C:42": "Parallels, Inc.",
}
_vendor_cache = {}


def mac_vendor_lookup(mac):
    if mac in _vendor_cache:
        return _vendor_cache[mac]
    vendor = "غير معروف"
    if requests is not None:
        try:
            resp = requests.get(f"https://api.macvendors.com/{mac}", timeout=2)
            if resp.status_code == 200 and resp.text.strip():
                vendor = resp.text.strip()
        except Exception:
            pass
    if vendor == "غير معروف":
        vendor = OFFLINE_OUI.get(mac.upper()[0:8], "غير معروف")
    _vendor_cache[mac] = vendor
    return vendor


def reverse_dns(ip):
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except Exception:
        return None


def real_ping(ip):
    system = platform.system().lower()
    param = "-n" if "windows" in system else "-c"
    try:
        start = time.time()
        output = subprocess.check_output(["ping", param, "1", str(ip)],
                                          stderr=subprocess.STDOUT, universal_newlines=True, timeout=2)
        elapsed_ms = round((time.time() - start) * 1000, 1)
        ttl = None
        low = output.lower()
        if "ttl=" in low:
            try:
                ttl = int(low.split("ttl=")[1].split()[0].strip(".,"))
            except Exception:
                ttl = None
        return elapsed_ms, ttl
    except Exception:
        return None, None


def guess_os_from_ttl(ttl):
    if ttl is None:
        return "غير معروف"
    if ttl >= 250:
        return "جهاز شبكة (راوتر/سويتش)"
    if ttl >= 120:
        return "على الأغلب Windows"
    if ttl >= 60:
        return "على الأغلب Linux/Android/macOS/iOS"
    return f"غير مؤكد (TTL={ttl})"


def guess_device_type(vendor, hostname, os_guess):
    """تخمين نوع الجهاز من الشركة المصنّعة + اسم الجهاز الحقيقيين — تخمين وليس يقينًا."""
    v = (vendor or "").lower()
    h = (hostname or "").lower()
    if "apple" in v:
        if "iphone" in h:
            return "iPhone"
        if "ipad" in h:
            return "iPad"
        if "macbook" in h or "imac" in h or "mac" in h:
            return "Mac"
        return "جهاز Apple"
    if "raspberry" in v:
        return "Raspberry Pi"
    if "samsung" in v:
        return "هاتف/جهاز Samsung"
    if "tp-link" in v or "netgear" in v or "d-link" in v or "asus" in v and "router" in h:
        return "جهاز شبكة (راوتر/إكستندر)"
    if "windows" in os_guess:
        return "كمبيوتر (Windows)"
    if "linux/android" in os_guess.lower():
        return "هاتف Android على الأغلب"
    return "غير محدد"


def connection_quality(latency_ms):
    """تقدير جودة الاتصال بناءً على ping حقيقي — هذا ليس مسافة فعلية، فقط مؤشر جودة استجابة."""
    if latency_ms is None:
        return "لا يستجيب"
    if latency_ms < 15:
        return "ممتازة (اتصال سريع جدًا)"
    if latency_ms < 50:
        return "جيدة"
    if latency_ms < 150:
        return "متوسطة"
    return "ضعيفة"


#الرادار وقصته 
class RenderEngine3D:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.angle_x = self.angle_y = self.angle_z = 0

    def rotate_point(self, x, y, z):
        rx = math.radians(self.angle_x)
        y1 = y * math.cos(rx) - z * math.sin(rx)
        z1 = y * math.sin(rx) + z * math.cos(rx)
        ry = math.radians(self.angle_y)
        x2 = x * math.cos(ry) + z1 * math.sin(ry)
        z2 = -x * math.sin(ry) + z1 * math.cos(ry)
        rz = math.radians(self.angle_z)
        x3 = x2 * math.cos(rz) - y1 * math.sin(rz)
        y3 = x2 * math.sin(rz) + y1 * math.cos(rz)
        return x3, y3, z2

    def project(self, x, y, z, distance=250):
        fov = distance / (distance + z + 150)
        return int(self.w / 2 + x * fov), int(self.h / 2 - y * fov)

    def get_phone_mesh(self):
        v = [[-30, -60, -5], [30, -60, -5], [30, 60, -5], [-30, 60, -5],
             [-30, -60, 5], [30, -60, 5], [30, 60, 5], [-30, 60, 5]]
        e = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        return v, e

    def get_laptop_mesh(self):
        v = [[-50,-40,-5],[50,-40,-5],[50,0,-5],[-50,0,-5],
             [-50,-40,5],[50,-40,5],[50,0,5],[-50,0,5],
             [-50,0,5],[50,0,5],[50,50,40],[-50,50,40]]
        e = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),
             (0,4),(1,5),(2,6),(3,7),(8,9),(9,10),(10,11),(11,8)]
        return v, e


#الواجهة الخضراء
class CyberRadarApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ADEEB CYBER RADAR — رادار شبكتك الحقيقي")
        self.geometry("1250x780")
        self.configure(fg_color="#030703")

        self.is_running = True
        self.alarm_running = True
        self.devices = []
        self.selected_device = None
        self.local_ip, self.subnet_cidr = get_local_ip_and_subnet()
        self.public_ip = "جارِ الجلب..."
        self.engine_3d = RenderEngine3D(320, 260)
        self.radar_angle = 0

        self.build_ui()

        threading.Thread(target=self.startup_sequence, daemon=True).start()
        threading.Thread(target=self.connection_watch_loop, daemon=True).start()
        threading.Thread(target=self.fetch_public_ip, daemon=True).start()
        threading.Thread(target=self.auto_scan_loop, daemon=True).start()
        threading.Thread(target=self.render_loop, daemon=True).start()

    def startup_sequence(self):
        """ينطق رسالة البداية مرة واحدة، ثم يشغل 3 رنات كل 10 ثوانٍ."""
        speak("جار مسح الشبكة المحلية بواسطة خادم أديب يرجى الانتظار")
        self.alarm_loop()

    def alarm_loop(self):
        """تسلسل الجرس:
        3 رنات قصيرة، انتظار ثانيتين، رنة طويلة،
        انتظار 3 ثوانٍ، ثم 10 رنات سريعة، وبعدها يتكرر.
        """
        while self.is_running and self.alarm_running:
            # 3 رنات قصيرة
            for _ in range(3):
                if not self.is_running or not self.alarm_running:
                    return
                ring_three_times()  # تستخدم رنة النظام الموجودة في الكود
                time.sleep(0.15)

            # انتظار ثانيتين
            if not self._alarm_wait(2):
                return

            # رنة طويلة
            self.long_bell()

            # انتظار 3 ثوانٍ
            if not self._alarm_wait(3):
                return

            # 10 رنات سريعة متتالية
            for _ in range(10):
                if not self.is_running or not self.alarm_running:
                    return
                self.short_bell()
                time.sleep(0.08)

            # يبدأ التسلسل من جديد بعد 5 ثوانٍ من نهاية المجموعة.
            if not self._alarm_wait(5):
                return

    def _alarm_wait(self, seconds):
        """انتظار قابل للإلغاء عند إغلاق البرنامج."""
        steps = max(1, int(seconds * 20))
        for _ in range(steps):
            if not self.is_running or not self.alarm_running:
                return False
            time.sleep(0.05)
        return True

    def short_bell(self):
        """رنة قصيرة."""
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.Beep(1200, 120)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass

    def long_bell(self):
        """رنة طويلة طوووووووووط."""
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.Beep(900, 1200)
            else:
                print("\a", end="", flush=True)
                time.sleep(1.2)
        except Exception:
            pass


   #الui
    def build_ui(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # يسار: الرادار + الجدول
        left = ctk.CTkFrame(self, fg_color="#080F08", border_color="#00FF00", border_width=1)
        left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.top_info = ctk.CTkLabel(left, text="", font=("Courier New", 12, "bold"), text_color="#00FF00", justify="right")
        self.top_info.pack(pady=8)
        self.update_top_info()

        self.radar_canvas = tk.Canvas(left, width=300, height=300, bg="#000000", highlightthickness=1, highlightbackground="#00FF00")
        self.radar_canvas.pack(pady=5)

        radar_note = ctk.CTkLabel(left, text="⚠️ الرادار عنصر تصميمي فقط — لا يمثّل الموقع الفعلي للأجهزة",
                                   text_color="#557755", font=("Arial", 10))
        radar_note.pack()

        self.devices_frame = ctk.CTkScrollableFrame(left, fg_color="#020502", border_color="#005500", border_width=1)
        self.devices_frame.pack(fill="both", expand=True, padx=10, pady=10)

        btn_row = ctk.CTkFrame(left, fg_color="#000000")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(
            btn_row,
            text="🔄 مسح الآن",
            command=self.manual_scan,
            fg_color="#004400",
            hover_color="#006600"
        ).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text="⬇️ تصدير CSV", command=self.export_csv,
                      fg_color="#222222", hover_color="#444444").pack(side="right", padx=5)

        # يمين: 3D + تفاصيل + تحكم
        right = ctk.CTkFrame(self, fg_color="#080F08", border_color="#00FF00", border_width=1)
        right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(right, text="[ تجسيد 3D تجميلي ]", font=("Arial", 13, "bold"), text_color="#00FF00").pack(pady=5)
        self.canvas_3d = tk.Canvas(right, width=300, height=240, bg="#000000", highlightthickness=1, highlightbackground="#00FF00")
        self.canvas_3d.pack(pady=5)

        self.info_box = ctk.CTkTextbox(right, height=230, fg_color="#000000", text_color="#00FF00",
                                        font=("Courier New", 12), border_color="#00FF00", border_width=1)
        self.info_box.pack(fill="x", padx=10, pady=5)
        self.update_info_box("اختر جهازًا من القائمة لعرض بياناته الحقيقية...")

        control = ctk.CTkFrame(right, fg_color="#000000", border_color="#00AA00", border_width=1)
        control.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(control, text="⛔ الحظر عبر لوحة تحكم راوترك الحقيقية", text_color="#FFAA00",
                     font=("Arial", 12, "bold")).pack(pady=(8, 2))
        ctk.CTkButton(control, text="فتح لوحة تحكم الراوتر (192.168.1.1)", command=self.open_router_panel,
                      fg_color="#663300", hover_color="#994400").pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(
            control,
            text="لأتمتة زر الحظر تلقائيًا أعطني موديل راوترك بالضبط — بربط حقيقي بلوحة تحكمك،\n"
                 "بدون تخمين نقاط اتصال. لا تتوفر هنا أداة إسقاط شبكة (deauth) لأنها أداة هجوم\n"
                 "عامة تعمل على أي شبكة قريبة بغض النظر عمّن يملكها.",
            text_color="#AA8855", font=("Arial", 10), justify="right",
        ).pack(padx=10, pady=(0, 8))

    def open_router_panel(self):
        try:
            gateway = ".".join(self.local_ip.split(".")[:3]) + ".1"
            url = f"http://{gateway}"
            if "darwin" in platform.system().lower():
                subprocess.run(["open", url])
            elif "windows" in platform.system().lower():
                os.startfile(url)
            else:
                subprocess.run(["xdg-open", url])
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر فتح المتصفح تلقائيًا. افتح يدويًا: http://{self.local_ip.rsplit('.',1)[0]}.1\n{e}")

    def update_top_info(self):
        mode = "scapy (دقّة كاملة)" if SCAPY_AVAILABLE else "fallback (شغّل بصلاحية root/admin لدقة أعلى)"
        self.top_info.configure(
            text=f"شبكتك المحلية: {self.subnet_cidr}\n"
                 f"جهازك: {self.local_ip}   |   IP العام لشبكتك: {self.public_ip}\n"
                 f"طريقة الفحص: {mode}"
        )

    def fetch_public_ip(self):
        self.public_ip = get_public_ip()
        self.after(0, self.update_top_info)

    # Scan logic
    def auto_scan_loop(self):
        while self.is_running:
            self.run_scan()
            time.sleep(30)

    def manual_scan(self):
        """تشغيل مسح يدوي مع نطق رسالة الانتظار المطلوبة."""
        threading.Thread(target=self._manual_scan_worker, daemon=True).start()

    def _manual_scan_worker(self):
        speak("جار مسح الشبكة المحلية بواسطة خادم أديب يرجى الانتظار")
        self.run_scan()

    def run_scan(self):
        raw_devices, method = discover_devices(self.subnet_cidr)
        enriched = []
        for dev in raw_devices:
            ip, mac = dev["ip"], dev["mac"]
            latency_ms, ttl = real_ping(ip)
            vendor = mac_vendor_lookup(mac)
            hostname = reverse_dns(ip) or "—"
            os_guess = guess_os_from_ttl(ttl)
            dev_type = guess_device_type(vendor, hostname, os_guess)
            quality = connection_quality(latency_ms)
            latency_str = f"{latency_ms} ms" if latency_ms is not None else "لا يستجيب"
            enriched.append({
                "ip": ip, "mac": mac, "vendor": vendor, "hostname": hostname,
                "os_guess": os_guess, "type": dev_type, "latency": latency_str, "quality": quality,
            })
        enriched.sort(key=lambda d: tuple(int(p) for p in d["ip"].split(".")))
        self.devices = enriched
        self.after(0, self.refresh_devices_ui)

    def refresh_devices_ui(self):
        for w in self.devices_frame.winfo_children():
            w.destroy()

        if not self.devices:
            ctk.CTkLabel(
                self.devices_frame,
                text="لا توجد أجهزة مكتشفة حتى الآن",
                text_color="#00AA00"
            ).pack(fill="x", padx=5, pady=8)
            return

        for dev in self.devices:
            dev = self.enrich_device(dev)
            text = (
                f"📡 {dev['hostname']} | "
                f"{dev['ip']} | "
                f"{dev['type']}"
            )
            btn = ctk.CTkButton(
                self.devices_frame,
                text=text,
                fg_color="#002200",
                hover_color="#006600",
                text_color="#00FF00",
                anchor="w",
                command=lambda d=dev: self.show_device(d)
            )
            btn.pack(fill="x", padx=5, pady=3)

    def identify_device_type(self, hostname="", vendor="", ip=""):
        s = f"{hostname} {vendor}".lower()
        if any(x in s for x in ("iphone", "ipad", "ios")):
            return "هاتف/جهاز Apple"
        if any(x in s for x in ("android", "samsung", "xiaomi", "huawei", "oppo", "vivo", "oneplus")):
            return "هاتف Android"
        if any(x in s for x in ("windows", "microsoft", "laptop", "desktop", "pc")):
            return "كمبيوتر Windows"
        if "mac" in s or "apple" in s:
            return "كمبيوتر Apple"
        if any(x in s for x in ("router", "gateway", "mikrotik", "tp-link", "ubiquiti")):
            return "راوتر/شبكة"
        return "جهاز شبكة"

    def enrich_device(self, dev):
        """توحيد معلومات الجهاز دون اختلاق بيانات غير متاحة."""
        vendor = dev.get("vendor") or dev.get("manufacturer") or "غير معروف"
        hostname = dev.get("hostname") or dev.get("name") or "غير معروف"
        ip = dev.get("ip") or "غير معروف"
        mac = dev.get("mac") or "غير معروف"

        # بعض الكواشف ترجع OS باسم مختلف.
        os_name = (
            dev.get("os_guess")
            or dev.get("os")
            or dev.get("operating_system")
            or "غير متاح"
        )

        dtype = dev.get("type") or self.identify_device_type(hostname, vendor, ip)

        dev["vendor"] = vendor
        dev["hostname"] = hostname
        dev["ip"] = ip
        dev["mac"] = mac
        dev["os_guess"] = os_name
        dev["type"] = dtype
        return dev

    def show_device(self, dev):
        """عرض معلومات الجهاز عند اختياره من الرادار أو القائمة."""
        self.selected_device = dev
        dev = self.enrich_device(dev)

        details = (
            "╔══════════════════════════════╗\n"
            "       معلومات الجهاز\n"
            "╚══════════════════════════════╝\n\n"
            f"📡 اسم الجهاز: {dev['hostname']}\n"
            f"🌐 عنوان IP: {dev['ip']}\n"
            f"🔗 عنوان MAC: {dev['mac']}\n"
            f"🏭 الشركة المصنعة: {dev['vendor']}\n"
            f"💻 نظام التشغيل: {dev['os_guess']}\n"
            f"📱 نوع الجهاز: {dev['type']}\n"
            f"⚡ زمن الاستجابة: {dev.get('latency', 'غير متاح')}\n"
            f"📶 جودة الاتصال: {dev.get('quality', 'غير متاحة')}"
        )
        self.update_info_box(details)
        self.draw_radar()
        self.render_3d()

    def select_device(self, dev):
        self.show_device(dev)

    def update_info_box(self, text):
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", text)

    def draw_radar(self):
        canvas = self.radar_canvas
        canvas.delete("all")

        w = int(canvas.winfo_width() or 300)
        h = int(canvas.winfo_height() or 300)
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 2 - 20

        # دوائر الرادار
        for ratio in (1.0, 0.75, 0.5, 0.25):
            r = int(radius * ratio)
            canvas.create_oval(
                cx-r, cy-r, cx+r, cy+r,
                outline="#005500", width=1
            )

        # المحاور
        canvas.create_line(cx-radius, cy, cx+radius, cy, fill="#004400")
        canvas.create_line(cx, cy-radius, cx, cy+radius, fill="#004400")

        # خط المسح
        angle = math.radians(self.radar_angle)
        sx = cx + radius * math.cos(angle)
        sy = cy - radius * math.sin(angle)
        canvas.create_line(cx, cy, sx, sy, fill="#00FF00", width=2)

        # مركز جهاز الفحص
        canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill="#00FF00", outline="")

        # توزيع بصري للأجهزة؛ ليس موقعًا جغرافيًا حقيقيًا.
        devices = list(self.devices)
        count = max(1, len(devices))

        for i, dev in enumerate(devices):
            dev = self.enrich_device(dev)
            a = (2 * math.pi * i / count) + math.radians(20)
            ring = radius * (
                0.30 + 0.60 * ((i % 5) / 4 if count > 1 else 0.5)
            )
            x = cx + ring * math.cos(a)
            y = cy - ring * math.sin(a)

            selected = dev is self.selected_device
            rr = 9 if selected else 7

            circle = canvas.create_oval(
                x-rr, y-rr, x+rr, y+rr,
                fill="#00FF00" if selected else "#008800",
                outline="#AAFFAA" if selected else "#004400",
                width=2
            )

            # كل دائرة مرتبطة بالجهاز نفسه.
            canvas.tag_bind(
                circle,
                "<Button-1>",
                lambda event, d=dev: self.show_device(d)
            )

            label = canvas.create_text(
                x, y-14,
                text=dev["ip"],
                fill="#66FF66",
                font=("Courier New", 8)
            )
            canvas.tag_bind(
                label,
                "<Button-1>",
                lambda event, d=dev: self.show_device(d)
            )

        canvas.create_text(
            cx, h-10,
            text=f"الأجهزة المكتشفة: {len(devices)}",
            fill="#00AA00",
            font=("Arial", 9)
        )

    def render_3d(self):
        canvas = self.canvas_3d
        canvas.delete("all")

        w = int(canvas.winfo_width() or 300)
        h = int(canvas.winfo_height() or 240)
        self.engine_3d.w = w
        self.engine_3d.h = h

        # جهاز مختار: هاتف/لابتوب/شبكة، مع استخدام المجسم كعنصر بصري فقط.
        dev = self.selected_device
        dev_type = (dev or {}).get("type", "").lower()

        if "laptop" in dev_type or "كمبيوتر" in dev_type:
            vertices, edges = self.engine_3d.get_laptop_mesh()
        else:
            vertices, edges = self.engine_3d.get_phone_mesh()

        projected = []
        for x, y, z in vertices:
            rx, ry, rz = self.engine_3d.rotate_point(x, y, z)
            px, py = self.engine_3d.project(rx, ry, rz)
            projected.append((px, py))

        for a, b in edges:
            x1, y1 = projected[a]
            x2, y2 = projected[b]
            canvas.create_line(x1, y1, x2, y2, fill="#00FF00", width=2)

        label = "لا يوجد جهاز محدد" if not dev else dev.get("type", "جهاز")
        canvas.create_text(
            w//2, h-15, text=label,
            fill="#00FF00", font=("Arial", 10, "bold")
        )

    def render_loop(self):
        while self.is_running:
            try:
                self.radar_angle = (self.radar_angle + 4) % 360
                self.engine_3d.angle_y = (self.engine_3d.angle_y + 2) % 360
                self.engine_3d.angle_x = 12 + 8 * math.sin(math.radians(self.radar_angle))

                self.after(0, self.draw_radar)
                self.after(0, self.render_3d)
            except Exception:
                pass
            time.sleep(0.05)

    def export_csv(self):
        if not self.devices:
            messagebox.showinfo("تصدير CSV", "لا توجد أجهزة مكتشفة لتصديرها.")
            return

        try:
            filename = f"adeeb_network_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            path = os.path.abspath(filename)

            fields = [
                "ip", "mac", "vendor", "hostname",
                "os_guess", "type", "latency", "quality"
            ]

            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for dev in self.devices:
                    writer.writerow({field: dev.get(field, "") for field in fields})

            messagebox.showinfo("تم التصدير", f"تم حفظ الملف:\n{path}")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر تصدير CSV:\n{e}")


    def connection_watch_loop(self):
        """يراقب انقطاع الأجهزة ويعلن صوتيًا عند اكتشاف الانقطاع."""
        previous = set()

        while self.is_running:
            try:
                current = {
                    dev.get("mac") or dev.get("ip")
                    for dev in self.devices
                    if dev.get("mac") or dev.get("ip")
                }

                disconnected = previous - current
                for identifier in disconnected:
                    if self.is_running:
                        speak("متصل بخادم أديب الرجاء الاستعمال السلمي")

                previous = current
            except Exception:
                pass

            for _ in range(20):
                if not self.is_running:
                    return
                time.sleep(0.1)

    def on_close(self):
        self.is_running = False
        self.alarm_running = False
        try:
            self.destroy()
        except Exception:
            pass


def main():
    app = CyberRadarApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
