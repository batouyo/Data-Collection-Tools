import time
import hid
import csv
import socket
import threading
import os
import datetime
import argparse

'''
This program is used to extract data information from the Contec CMS50E, 
including PPG signals, Heart rate signals, and SPO2 signals.
This version is designed to be controlled remotely via UDP commands from a master computer.
Commands supported:
- PREPARE: Prepare for data collection
- START,timestamp: Start collecting data (with master timestamp for synchronization)
- STOP,timestamp: Stop collecting data (with master timestamp for synchronization)
'''

class OximeterDataCollector:
    def __init__(self, vendor_id, product_id, port=5000):
        # 设备参数
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device = None
        
        # 数据采集状态
        self.is_collecting = False
        self.is_prepared = False
        self.should_stop = False
        self.collect_thread = None
        
        # 数据存储
        self.data_dir = os.path.join(os.getcwd(), "oximeter_data")
        self.session_id = None
        self.csv_file_path = None
        
        # 时间同步
        self.master_start_time = None  # 主机发送的开始时间戳
        self.local_start_time = None   # 本地实际开始时间戳
        self.time_offset = 0           # 主机与从机时间偏差
        
        # UDP通信
        self.udp_port = port
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('0.0.0.0', self.udp_port))
        print(f"UDP监听已启动在端口 {port}")
        
        # 确保数据目录存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def start_udp_listener(self):
        """启动UDP命令监听线程"""
        threading.Thread(target=self._listen_for_commands, daemon=True).start()
    
    def _listen_for_commands(self):
        """监听来自主机的UDP命令"""
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                command = data.decode().strip()
                print(f"收到来自 {addr} 的命令: {command}")
                
                self._process_command(command, addr)
            except Exception as e:
                print(f"处理命令时出错: {str(e)}")
    
    def _process_command(self, command, sender_addr):
        """处理接收到的命令"""
        if command.startswith("PREPARE"):
            self._prepare_collection()
            
        elif command.startswith("START"):
            # 解析主机时间戳
            parts = command.split(',')
            if len(parts) > 1:
                try:
                    self.master_start_time = float(parts[1])
                    self._start_collection()
                except ValueError:
                    print("无效的开始时间戳")
            else:
                print("开始命令缺少时间戳")
                
        elif command.startswith("STOP"):
            # 解析主机停止时间戳
            parts = command.split(',')
            if len(parts) > 1:
                try:
                    stop_timestamp = float(parts[1])
                    self._stop_collection(stop_timestamp)
                except ValueError:
                    print("无效的停止时间戳")
            else:
                self._stop_collection(None)
    
    def _prepare_collection(self):
        """准备数据采集"""
        if self.is_prepared:
            return
            
        try:
            # 打开设备
            self.device = hid.device()
            self.device.open(self.vendor_id, self.product_id)
            print("设备已打开")
            
            # 创建新会话
            self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join(self.data_dir, self.session_id)
            os.makedirs(session_dir, exist_ok=True)
            
            self.csv_file_path = os.path.join(session_dir, "oximeter_data.csv")
            
            self.is_prepared = True
            print("数据采集已准备就绪")
            
        except Exception as e:
            print(f"准备数据采集时出错: {str(e)}")
    
    def _start_collection(self):
        """开始数据采集"""
        if not self.is_prepared:
            print("设备尚未准备就绪")
            return
            
        if self.is_collecting:
            print("数据采集已经在进行中")
            return
        
        self.should_stop = False
        self.local_start_time = time.time()
        self.time_offset = self.local_start_time - self.master_start_time
        print(f"本地时间与主机时间偏差: {self.time_offset:.6f}秒")
        
        # 记录同步信息
        sync_file = os.path.join(os.path.dirname(self.csv_file_path), "sync_info.txt")
        with open(sync_file, "w") as f:
            f.write(f"主机开始时间戳: {self.master_start_time}\n")
            f.write(f"本地开始时间戳: {self.local_start_time}\n")
            f.write(f"时间偏差: {self.time_offset}\n")
            f.write(f"同步后校准时间: {datetime.datetime.now().isoformat()}\n")
        
        # 初始化CSV文件
        with open(self.csv_file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['数据点', '采集时间戳', '相对时间(秒)', '校准后时间(秒)', 'PPG', 'HR', 'SPO2'])
        
        # 启动数据采集线程
        self.is_collecting = True
        self.collect_thread = threading.Thread(target=self._collect_data_thread)
        self.collect_thread.daemon = True
        self.collect_thread.start()
        
        print("数据采集已开始")
    
    def _stop_collection(self, master_stop_time):
        """停止数据采集"""
        if not self.is_collecting:
            return
            
        self.should_stop = True
        local_stop_time = time.time()
        
        # 等待采集线程结束
        if self.collect_thread:
            self.collect_thread.join(timeout=5)
        
        # 记录同步信息
        if master_stop_time:
            sync_file = os.path.join(os.path.dirname(self.csv_file_path), "sync_info.txt")
            with open(sync_file, "a") as f:
                f.write(f"主机停止时间戳: {master_stop_time}\n")
                f.write(f"本地停止时间戳: {local_stop_time}\n")
                f.write(f"采集总时长: {local_stop_time - self.local_start_time:.2f}秒\n")
        
        self.is_collecting = False
        self.is_prepared = False
        
        print("数据采集已停止")
    
    def _collect_data_thread(self):
        """数据采集线程函数"""
        # 初始化数据
        check_bit = 0
        data_update_bit = 0
        status_bit = 0
        PPG_bit = 0
        HR_bit = 0
        SPO2_bit = 0
        data_count = 0
        
        while not self.should_stop:
            try:
                data = self.device.read(18)
                
                # 获取当前时间
                current_time = time.time()
                relative_time = current_time - self.local_start_time
                calibrated_time = current_time - self.master_start_time
                
                # 处理数据
                for i in range(3):
                    try:
                        check_bit = data[0 + 6*i]
                        data_update_bit = data[1 + 6*i]
                        status_bit = data[2 + 6*i]

                        # 更新数据位
                        if data_update_bit == 0:
                            PPG_bit = data[3 + 6*i]
                        elif data_update_bit == 1:
                            HR_bit = data[3 + 6 * i]
                            SPO2_bit = data[4 + 6 * i]

                        # 保存数据到CSV
                        with open(self.csv_file_path, 'a', newline='') as file:
                            writer = csv.writer(file)
                            writer.writerow([
                                str(data_count), 
                                str(current_time), 
                                f"{relative_time:.6f}", 
                                f"{calibrated_time:.6f}",
                                str(PPG_bit), 
                                str(HR_bit), 
                                str(SPO2_bit)
                            ])
                        data_count += 1
                    except IndexError:
                        # 忽略不完整的数据帧
                        pass
                
            except Exception as e:
                print(f"采集数据时出错: {str(e)}")
                time.sleep(0.1)
        
        if self.device:
            try:
                self.device.close()
                print("设备已关闭")
            except:
                pass

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='血氧仪数据采集程序')
    parser.add_argument('--vendor-id', type=lambda x: int(x, 0), default=0x28E9,
                        help='设备供应商ID (十六进制)')
    parser.add_argument('--product-id', type=lambda x: int(x, 0), default=0x028A,
                        help='设备产品ID (十六进制)')
    parser.add_argument('--port', type=int, default=5000,
                        help='UDP监听端口')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='数据保存目录')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()
    
    collector = OximeterDataCollector(
        vendor_id=args.vendor_id,
        product_id=args.product_id,
        port=args.port
    )
    
    if args.data_dir:
        collector.data_dir = args.data_dir
    
    # 启动UDP监听
    collector.start_udp_listener()
    
    # 保持程序运行
    try:
        print("血氧仪数据采集程序已启动，等待主机命令...")
        print(f"监听端口: {args.port}")
        print(f"数据将保存到: {collector.data_dir}")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("程序已手动停止")

