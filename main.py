import cv2
import socket
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import datetime
import numpy as np
from PIL import Image, ImageTk

class DataCollectionSystem:
    """
    数据采集系统主控程序
    负责控制摄像头录制视频并向从机发送UDP命令控制生理数据采集
    """
    def __init__(self, root):
        # 主窗口设置
        self.root = root
        self.root.title("数据采集系统控制端")
        self.root.geometry("900x600")
        
        # 变量初始化
        self.camera_index = 0
        self.is_recording = False
        self.is_previewing = False
        self.session_id = None
        self.cap = None
        self.out = None
        self.preview_thread = None
        self.record_thread = None
        self.client_ips = []
        self.start_time = None
        self.experiment_duration = 1  # 默认录制时长(分钟)
        self.data_dir = os.path.join(os.getcwd(), "experiment_data")
        
        # UDP设置
        self.udp_port = 5000
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # 创建UI
        self.create_ui()
        
        # 确保数据目录存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def create_ui(self):
        """创建用户界面"""
        # 主框架分为左右两部分
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧：摄像头预览和控制
        left_frame = ttk.LabelFrame(main_frame, text="摄像头控制")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 摄像头预览区域
        self.preview_canvas = tk.Canvas(left_frame, bg="black", width=640, height=480)
        self.preview_canvas.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        # 摄像头控制按钮
        camera_control_frame = ttk.Frame(left_frame)
        camera_control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(camera_control_frame, text="摄像头索引:").pack(side=tk.LEFT)
        self.camera_index_var = tk.StringVar(value="0")
        ttk.Entry(camera_control_frame, textvariable=self.camera_index_var, width=5).pack(side=tk.LEFT, padx=5)
        
        self.preview_btn = ttk.Button(camera_control_frame, text="开始预览", command=self.toggle_preview)
        self.preview_btn.pack(side=tk.LEFT, padx=5)
        
        # 右侧：录制控制和设置
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5, pady=5)
        
        # 录制设置区域
        settings_frame = ttk.LabelFrame(right_frame, text="录制设置")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 录制时长设置
        ttk.Label(settings_frame, text="录制时长(分钟):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.duration_var = tk.StringVar(value="1")
        ttk.Entry(settings_frame, textvariable=self.duration_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        # 保存路径设置
        ttk.Label(settings_frame, text="数据保存路径:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.save_path_var = tk.StringVar(value=self.data_dir)
        path_entry = ttk.Entry(settings_frame, textvariable=self.save_path_var, width=30)
        path_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="浏览...", command=self.browse_save_path).grid(row=1, column=2, padx=5, pady=5)
        
        # 从机IP设置
        ip_frame = ttk.LabelFrame(right_frame, text="从机IP配置")
        ip_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.ip_text = tk.Text(ip_frame, height=5, width=30)
        self.ip_text.pack(fill=tk.X, padx=5, pady=5)
        self.ip_text.insert(tk.END, "192.168.1.2\n192.168.1.3")
        
        ttk.Button(ip_frame, text="扫描局域网设备", command=self.scan_network).pack(padx=5, pady=5)
        
        # 录制控制区域
        control_frame = ttk.LabelFrame(right_frame, text="录制控制")
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.prepare_btn = ttk.Button(control_frame, text="准备", command=self.prepare_experiment)
        self.prepare_btn.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="开始录制", command=self.start_experiment, state=tk.DISABLED)
        self.start_btn.pack(fill=tk.X, padx=5, pady=5)
        
        self.stop_btn = ttk.Button(control_frame, text="停止录制", command=self.stop_experiment, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 状态显示
        status_frame = ttk.LabelFrame(right_frame, text="状态")
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var).pack(padx=5, pady=5)
        
        self.timer_var = tk.StringVar(value="00:00")
        ttk.Label(status_frame, textvariable=self.timer_var, font=("Arial", 24)).pack(padx=5, pady=5)
    
    def browse_save_path(self):
        """选择数据保存路径"""
        directory = filedialog.askdirectory()
        if directory:
            self.save_path_var.set(directory)
            self.data_dir = directory
    
    def toggle_preview(self):
        """切换摄像头预览状态"""
        if self.is_previewing:
            self.stop_preview()
        else:
            self.start_preview()
    
    def start_preview(self):
        """开始摄像头预览"""
        try:
            camera_idx = int(self.camera_index_var.get())
            self.cap = cv2.VideoCapture(camera_idx)
            
            if not self.cap.isOpened():
                messagebox.showerror("错误", f"无法打开摄像头 {camera_idx}")
                return
            
            self.is_previewing = True
            self.preview_btn.config(text="停止预览")
            self.preview_thread = threading.Thread(target=self.update_preview, daemon=True)
            self.preview_thread.start()
            
        except Exception as e:
            messagebox.showerror("错误", f"预览失败: {str(e)}")
    
    def stop_preview(self):
        """停止摄像头预览"""
        self.is_previewing = False
        self.preview_btn.config(text="开始预览")
        if self.cap:
            self.cap.release()
            self.cap = None
    
    def update_preview(self):
        """更新摄像头预览画面"""
        while self.is_previewing:
            ret, frame = self.cap.read()
            if ret:
                # 转换为tkinter可用的格式
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                
                # 调整尺寸以适应画布
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    img = img.resize((canvas_width, canvas_height), Image.LANCZOS)
                
                photo = ImageTk.PhotoImage(image=img)
                
                # 更新画布
                self.preview_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.preview_canvas.image = photo  # 防止垃圾回收
            
            time.sleep(0.03)  # 约30fps
    
    def scan_network(self):
        """扫描局域网设备"""
        # 实际项目中应使用更复杂的扫描方法，这里仅作示例
        self.status_var.set("正在扫描网络...")
        
        # 模拟扫描过程
        def scan_task():
            time.sleep(2)  # 模拟扫描延迟
            example_ips = ["192.168.1.5", "192.168.1.10", "192.168.1.15"]
            self.root.after(0, lambda: self.ip_text.delete(1.0, tk.END))
            self.root.after(0, lambda: self.ip_text.insert(tk.END, "\n".join(example_ips)))
            self.root.after(0, lambda: self.status_var.set("扫描完成"))
        
        threading.Thread(target=scan_task, daemon=True).start()
    
    def prepare_experiment(self):
        """准备录制"""
        try:
            # 验证输入
            minutes = int(self.duration_var.get())
            if minutes <= 0:
                raise ValueError("录制时长必须大于0")
            # 将分钟转换为秒
            self.experiment_duration = minutes * 60
            
            # 获取从机IP列表
            self.client_ips = [ip.strip() for ip in self.ip_text.get(1.0, tk.END).strip().split("\n") if ip.strip()]
            if not self.client_ips:
                raise ValueError("未配置从机IP地址")
            
            # 创建录制会话
            self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join(self.data_dir, self.session_id)
            os.makedirs(session_dir, exist_ok=True)
            
            # 准备摄像头
            if not self.cap or not self.cap.isOpened():
                camera_idx = int(self.camera_index_var.get())
                self.cap = cv2.VideoCapture(camera_idx)
                if not self.cap.isOpened():
                    raise ValueError(f"无法打开摄像头 {camera_idx}")
            
            # 发送准备命令到从机
            for ip in self.client_ips:
                self.send_udp_command(ip, "PREPARE")
            
            # 更新UI
            self.status_var.set("录制准备就绪")
            self.start_btn.config(state=tk.NORMAL)
            self.prepare_btn.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("准备失败", str(e))
    
    def start_experiment(self):
        """开始录制"""
        try:
            # 更新UI状态
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            # 设置视频输出
            session_dir = os.path.join(self.data_dir, self.session_id)
            video_path = os.path.join(session_dir, "video.mp4")
            
            # 获取摄像头属性
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(self.cap.get(cv2.CAP_PROP_FPS))
            
            # 创建视频写入器
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
            
            # 记录开始时间
            self.start_time = time.time()
            
            # 显示屏幕闪烁作为同步信号
            self.flash_sync_signal()
            
            # 发送开始命令到从机
            command_time = time.time()
            for ip in self.client_ips:
                self.send_udp_command(ip, f"START,{command_time}")
            
            # 写入同步信息
            sync_file = os.path.join(session_dir, "sync_info.txt")
            with open(sync_file, "w") as f:
                f.write(f"录制开始时间: {datetime.datetime.now().isoformat()}\n")
                f.write(f"命令发送时间戳: {command_time}\n")
                f.write(f"视频开始时间戳: {self.start_time}\n")
            
            # 开始录制
            self.is_recording = True
            self.record_thread = threading.Thread(target=self.record_video, daemon=True)
            self.record_thread.start()
            
            # 开始计时器
            self.update_timer()
            
            self.status_var.set("正在记录...")
            
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self.stop_experiment()
    
    def flash_sync_signal(self):
        """显示屏幕闪烁作为同步信号"""
        flash_window = tk.Toplevel(self.root)
        flash_window.attributes('-fullscreen', True)
        flash_window.configure(bg='white')
        
        # 闪烁3次
        for _ in range(3):
            flash_window.update()
            time.sleep(0.2)
            flash_window.configure(bg='black')
            flash_window.update()
            time.sleep(0.2)
            flash_window.configure(bg='white')
        
        flash_window.destroy()
    
    def record_video(self):
        """录制视频线程"""
        while self.is_recording:
            ret, frame = self.cap.read()
            if ret:
                # 添加时间戳到帧
                timestamp = time.time() - self.start_time
                cv2.putText(frame, f"Time: {timestamp:.2f}s", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # 写入视频
                self.out.write(frame)
                
                # 检查是否超过录制时长
                if timestamp >= self.experiment_duration:
                    self.root.after(0, self.stop_experiment)
                    break
            
            time.sleep(0.01)
    
    def update_timer(self):
        """更新计时器显示"""
        if self.is_recording and self.start_time:
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.timer_var.set(f"{minutes:02d}:{seconds:02d}")
            
            # 如果仍在录制，继续更新
            if self.is_recording:
                self.root.after(1000, self.update_timer)
    
    def stop_experiment(self):
        """停止录制"""
        if not self.is_recording:
            return
        
        # 停止录制
        self.is_recording = False
        
        # 发送停止命令到从机
        stop_time = time.time()
        for ip in self.client_ips:
            self.send_udp_command(ip, f"STOP,{stop_time}")
        
        # 更新同步信息
        if self.session_id:
            session_dir = os.path.join(self.data_dir, self.session_id)
            sync_file = os.path.join(session_dir, "sync_info.txt")
            with open(sync_file, "a") as f:
                f.write(f"录制结束时间: {datetime.datetime.now().isoformat()}\n")
                f.write(f"停止命令时间戳: {stop_time}\n")
                f.write(f"录制总时长: {stop_time - self.start_time}秒\n")
        
        # 释放资源
        if self.out:
            self.out.release()
            self.out = None
        
        # 更新UI
        self.prepare_btn.config(state=tk.NORMAL)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("录制已停止")
        
        messagebox.showinfo("完成", f"录制已完成，数据保存在: {os.path.join(self.data_dir, self.session_id)}")
    
    def send_udp_command(self, ip, command):
        """向指定IP发送UDP命令"""
        try:
            self.udp_socket.sendto(command.encode(), (ip, self.udp_port))
            print(f"已发送命令 '{command}' 到 {ip}:{self.udp_port}")
        except Exception as e:
            print(f"发送命令到 {ip} 失败: {str(e)}")
    
    def cleanup(self):
        """清理资源"""
        self.stop_preview()
        self.stop_experiment()
        if self.udp_socket:
            self.udp_socket.close()

# 程序入口
if __name__ == "__main__":
    root = tk.Tk()
    app = DataCollectionSystem(root)
    
    # 设置窗口关闭事件
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    
    root.mainloop()