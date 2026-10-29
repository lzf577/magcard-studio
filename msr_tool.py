#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超市会员卡 磁条卡读写管理工具
适配设备: DEFTUN MSR-X6 / MSR-X6BT / MSR605 / MSR606 等兼容 MSR206 指令集的设备
功能特性:
  1. 自动扫描识别设备端口 (/dev/ttyUSB*, /dev/ttyACM*, /dev/rfcomm* 或 COM*)
  2. 读取会员卡 (支持 Track 1/2/3 解析，自动提取会员卡号)
  3. 写入会员卡 (支持单张写入、批量连号制卡)
  4. 快速克隆/复制会员卡 (先刷原卡读取，再刷空白卡写入)
  5. 内置 Web 可视化管理界面 (可在浏览器中点击操作)
"""

import sys
import os
import glob
import time
import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

try:
    import serial
except ImportError:
    print("[错误] 未安装 pyserial 模块，请执行: pip install pyserial 或 apt-get install python3-serial")
    sys.exit(1)

# MSR206 / MSR605 控制字节
ESC = b'\x1b'
FS = b'\x1c'
RESET = b'\x61'
READ = b'\x72'
WRITE = b'\x77'
COMM_TEST = b'\x65'
ERASE = b'\x63'

def scan_ports():
    """扫描系统所有可能的串口设备"""
    found = []
    if sys.platform.startswith('linux'):
        patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/rfcomm*']
        for p in patterns:
            found.extend(glob.glob(p))
    elif sys.platform.startswith('darwin'):
        found.extend(glob.glob('/dev/tty.usb*'))
    elif sys.platform.startswith('win'):
        for i in range(1, 33):
            found.append(f'COM{i}')
    return sorted(found)

class MSRDevice:
    def __init__(self, port, baudrate=9600, timeout=10):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(
                self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            # 清空缓存
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            return True
        except Exception as e:
            return False, str(e)

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.reset()
            except Exception:
                pass
            self.ser.close()

    def reset(self):
        """发送复位命令"""
        if not self.ser or not self.ser.is_open:
            return
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(ESC + RESET)
        self.ser.flush()
        time.sleep(0.1)

    def test_comm(self):
        """通信自检测试"""
        self.reset()
        self.ser.write(ESC + COMM_TEST)
        self.ser.flush()
        resp = self.ser.read(2)
        return resp == (ESC + b'y')

    def read_card(self):
        """
        读取磁条卡
        返回: dict: {'status': 'ok'/'error', 't1': str, 't2': str, 't3': str, 'card_no': str}
        """
        self.reset()
        # 发送读卡指令
        self.ser.write(ESC + READ)
        self.ser.flush()

        # 等待刷卡返回，格式通常为: ESC + 's' + ESC + 0x01 + T1 + ESC + 0x02 + T2 + ESC + 0x03 + T3 + '?' + FS + ESC + status
        data = bytearray()
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting > 0:
                data.extend(self.ser.read(self.ser.in_waiting))
                if b'\x1c' in data or len(data) > 300:
                    break
            time.sleep(0.05)

        if not data:
            return {'status': 'timeout', 'msg': '等待刷卡超时 (未检测到刷卡)'}

        # 解析数据
        t1, t2, t3 = '', '', ''
        try:
            # 查找起始标志 ESC + 's'
            s_idx = data.find(b'\x1bs')
            if s_idx == -1:
                return {'status': 'error', 'msg': f'返回数据异常: {data.hex()}'}
            
            payload = data[s_idx + 2:]
            # 分割磁道
            # 磁道1: \x1b\x01
            # 磁道2: \x1b\x02
            # 磁道3: \x1b\x03
            p1 = payload.find(b'\x1b\x01')
            p2 = payload.find(b'\x1b\x02')
            p3 = payload.find(b'\x1b\x03')
            pend = payload.find(b'?\x1c')
            if pend == -1:
                pend = payload.find(b'\x1c')
            if pend == -1:
                pend = len(payload)

            if p1 != -1:
                end1 = p2 if p2 != -1 else (p3 if p3 != -1 else pend)
                t1 = payload[p1+2:end1].decode('latin1', errors='ignore').strip('?%')
            if p2 != -1:
                end2 = p3 if p3 != -1 else pend
                t2 = payload[p2+2:end2].decode('latin1', errors='ignore').strip('?;')
            if p3 != -1:
                t3 = payload[p3+2:pend].decode('latin1', errors='ignore').strip('?;+')

            # 超市会员卡通常直接使用 Track 2（纯数字卡号或带等号校验位）
            card_no = t2.split('=')[0] if t2 else (t1 if t1 else t3)

            return {
                'status': 'ok',
                't1': t1,
                't2': t2,
                't3': t3,
                'card_no': card_no,
                'raw': data.hex()
            }
        except Exception as e:
            return {'status': 'error', 'msg': f'解析失败: {str(e)}', 'raw': data.hex()}

    def write_card(self, t1="", t2="", t3=""):
        """
        写入磁条卡
        t1, t2, t3 为待写入的字符串数据
        """
        self.reset()
        # 构建写入数据包
        # ESC + 's' + ESC + 0x01 + T1 + ESC + 0x02 + T2 + ESC + 0x03 + T3 + '?' + FS
        packet = bytearray(ESC + b's')
        packet.extend(ESC + b'\x01' + t1.encode('latin1'))
        packet.extend(ESC + b'\x02' + t2.encode('latin1'))
        packet.extend(ESC + b'\x03' + t3.encode('latin1'))
        packet.extend(b'?' + FS)

        # 发送写入指令 ESC + 'w' + packet
        self.ser.write(ESC + WRITE + packet)
        self.ser.flush()

        # 等待刷卡完成写入
        resp = bytearray()
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.ser.in_waiting > 0:
                resp.extend(self.ser.read(self.ser.in_waiting))
                if len(resp) >= 2:
                    break
            time.sleep(0.05)

        if not resp:
            return {'status': 'timeout', 'msg': '写卡超时 (未在规定时间内平稳刷卡)'}

        # 检查响应 (成功通常返回 ESC + '0' (0x30))
        if b'\x1b0' in resp:
            return {'status': 'ok', 'msg': '写卡成功！'}
        elif b'\x1b' in resp:
            return {'status': 'error', 'msg': f'写卡失败 (响应状态码: {resp.hex()})'}
        else:
            return {'status': 'done', 'msg': f'已执行写入: {resp.hex()}'}


# ==============================
# Web 界面服务器 (免安装GUI，浏览器即可用)
# ==============================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>超市会员卡 磁条卡读写管理系统</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
  .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
  h1 { font-size: 22px; margin-top: 0; color: #1a1a1a; display: flex; align-items: center; gap: 8px; }
  .badge { background: #0070f3; color: #fff; font-size: 12px; padding: 2px 8px; border-radius: 4px; }
  .section { margin-bottom: 24px; padding: 16px; border: 1px solid #e1e4e8; border-radius: 8px; }
  .section-title { font-weight: bold; margin-bottom: 12px; color: #333; font-size: 16px; }
  label { display: block; margin-bottom: 6px; font-weight: 500; font-size: 14px; }
  input[type="text"], select { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; margin-bottom: 12px; }
  .btn { background: #0070f3; color: white; border: none; padding: 10px 18px; border-radius: 6px; font-size: 14px; cursor: pointer; transition: 0.2s; font-weight: 500; }
  .btn:hover { background: #0051a8; }
  .btn-secondary { background: #6b7280; }
  .btn-secondary:hover { background: #4b5563; }
  .btn-success { background: #10b981; }
  .btn-success:hover { background: #059669; }
  .btn-danger { background: #ef4444; }
  .btn-danger:hover { background: #dc2626; }
  .btn-group { display: flex; gap: 10px; margin-top: 8px; }
  .status-box { padding: 12px; border-radius: 6px; background: #f9fafb; border: 1px solid #e5e7eb; font-family: monospace; font-size: 13px; min-height: 48px; white-space: pre-wrap; word-break: break-all; margin-top: 10px; }
  .card-result { background: #ecfdf5; border: 1px solid #a7f3d0; padding: 12px; border-radius: 6px; margin-top: 10px; display: none; }
  .tips { font-size: 13px; color: #6b7280; line-height: 1.6; margin-top: 8px; }
</style>
</head>
<body>
<div class="container">
  <h1><span>💳 超市会员卡管理系统</span> <span class="badge">DEFTUN MSR-X6</span></h1>

  <div class="section">
    <div class="section-title">1. 设备连接</div>
    <label>检测到的串口 / 蓝牙设备：</label>
    <div style="display: flex; gap: 10px;">
      <select id="portSelect"></select>
      <button class="btn btn-secondary" onclick="refreshPorts()">刷新端口</button>
      <button class="btn" onclick="testConnection()">测试通信</button>
    </div>
    <div id="connStatus" class="tips">请选择端口并测试连接</div>
  </div>

  <div class="section">
    <div class="section-title">2. 读取会员卡</div>
    <div class="tips">点击【开始读卡】后，机器指示灯常亮，请在 10 秒内平稳划过卡槽。</div>
    <div class="btn-group">
      <button class="btn btn-success" onclick="readCard()">▶ 开始读卡 (请刷卡)</button>
    </div>
    <div id="readResult" class="card-result">
      <div style="font-weight:bold; color:#065f46; margin-bottom:6px;">读取成功！</div>
      <div><strong>会员卡号：</strong><span id="resCardNo" style="font-size:18px; color:#047857; font-weight:bold;"></span></div>
      <div style="font-size:12px; color:#374151; margin-top:6px;">
        <div>Track 1: <span id="resT1"></span></div>
        <div>Track 2: <span id="resT2"></span></div>
        <div>Track 3: <span id="resT3"></span></div>
      </div>
      <div style="margin-top: 10px;">
        <button class="btn btn-secondary" style="font-size:12px; padding:4px 8px;" onclick="copyToWriter()">复制到写卡输入框</button>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">3. 制作 / 写入会员卡</div>
    <div class="tips">输入超市会员卡卡号（超市系统通常默认写在 Track 2，纯数字）：</div>
    <label>会员卡号 (Track 2)：</label>
    <input type="text" id="writeCardNo" placeholder="例如：88880001 或 690123456789">
    
    <details style="margin-bottom: 12px; font-size: 13px; color: #4b5563;">
      <summary style="cursor: pointer;">高级磁道选项 (可选)</summary>
      <div style="margin-top: 8px;">
        <label>Track 1 (一般包含字母姓名或留空):</label>
        <input type="text" id="writeT1" placeholder="例如: VIP/NAME">
        <label>Track 3 (可选扩展信息):</label>
        <input type="text" id="writeT3" placeholder="可选，一般留空">
      </div>
    </details>

    <div class="btn-group">
      <button class="btn btn-danger" onclick="writeCard()">✍ 写入会员卡 (请准备刷空白卡)</button>
    </div>
  </div>

  <div class="section">
    <div class="section-title">系统日志 / 提示</div>
    <div id="logBox" class="status-box">系统就绪，等待操作...</div>
  </div>
</div>

<script>
function log(msg) {
  const box = document.getElementById('logBox');
  box.innerText = "[" + new Date().toLocaleTimeString() + "] " + msg;
}

function refreshPorts() {
  fetch('/api/ports')
    .then(r => r.json())
    .then(data => {
      const sel = document.getElementById('portSelect');
      sel.innerHTML = '';
      if (data.ports.length === 0) {
        sel.innerHTML = '<option value="">未检测到串口设备 (请插上机器或配对蓝牙)</option>';
        log("未找到可用串口设备，请确认 USB 已插紧或已开机配对蓝牙。");
      } else {
        data.ports.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p;
          opt.innerText = p;
          sel.appendChild(opt);
        });
        log("已找到端口: " + data.ports.join(", "));
      }
    });
}

function getSelectedPort() {
  return document.getElementById('portSelect').value;
}

function testConnection() {
  const port = getSelectedPort();
  if (!port) { alert("请先选择端口！"); return; }
  log("正在测试连接: " + port + " ...");
  fetch('/api/test?port=' + encodeURIComponent(port))
    .then(r => r.json())
    .then(res => {
      if (res.status === 'ok') {
        document.getElementById('connStatus').innerText = "✅ 连接成功！设备响应正常。";
        log("设备通信正常！");
      } else {
        document.getElementById('connStatus').innerText = "❌ 连接失败: " + (res.msg || '无响应');
        log("连接失败: " + (res.msg || '无响应'));
      }
    });
}

function readCard() {
  const port = getSelectedPort();
  if (!port) { alert("请先选择端口！"); return; }
  log("正在等待刷卡，请在 10 秒内平稳划过卡片...");
  document.getElementById('readResult').style.display = 'none';

  fetch('/api/read?port=' + encodeURIComponent(port))
    .then(r => r.json())
    .then(res => {
      if (res.status === 'ok') {
        log("刷卡成功！会员卡号: " + (res.card_no || '空'));
        document.getElementById('resCardNo').innerText = res.card_no || '(无卡号)';
        document.getElementById('resT1').innerText = res.t1 || '(无)';
        document.getElementById('resT2').innerText = res.t2 || '(无)';
        document.getElementById('resT3').innerText = res.t3 || '(无)';
        document.getElementById('readResult').style.display = 'block';
      } else {
        log("读卡失败: " + (res.msg || '未知错误'));
      }
    }).catch(e => {
      log("请求出错: " + e);
    });
}

function copyToWriter() {
  const cardNo = document.getElementById('resCardNo').innerText;
  if (cardNo && cardNo !== '(无卡号)') {
    document.getElementById('writeCardNo').value = cardNo;
    document.getElementById('writeT1').value = document.getElementById('resT1').innerText;
    document.getElementById('writeT3').value = document.getElementById('resT3').innerText;
    log("已复制卡片数据到写卡输入框！");
  }
}

function writeCard() {
  const port = getSelectedPort();
  if (!port) { alert("请先选择端口！"); return; }
  const cardNo = document.getElementById('writeCardNo').value.trim();
  if (!cardNo) { alert("请输入要写入的会员卡号！"); return; }

  const t1 = document.getElementById('writeT1').value.trim();
  const t2 = cardNo;
  const t3 = document.getElementById('writeT3').value.trim();

  log("请拿好空白卡，准备刷卡写入: " + cardNo + " ...");

  fetch('/api/write', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port: port, t1: t1, t2: t2, t3: t3 })
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === 'ok') {
      log("🎉 " + res.msg);
      alert("写入成功！卡号: " + cardNo);
    } else {
      log("写卡提示: " + (res.msg || '失败'));
      alert("写入结果: " + (res.msg || '失败'));
    }
  }).catch(e => {
    log("请求出错: " + e);
  });
}

window.onload = refreshPorts;
</script>
</body>
</html>
"""

class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # 静默常规日志

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == '/' or parsed.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif parsed.path == '/api/ports':
            ports = scan_ports()
            self.send_json({'ports': ports})
        elif parsed.path == '/api/test':
            port = qs.get('port', [''])[0]
            dev = MSRDevice(port, timeout=3)
            conn = dev.connect()
            if conn is True:
                ok = dev.test_comm()
                dev.close()
                self.send_json({'status': 'ok' if ok else 'error', 'msg': '通信正常' if ok else '设备无响应'})
            else:
                self.send_json({'status': 'error', 'msg': conn[1] if isinstance(conn, tuple) else '打开端口失败'})
        elif parsed.path == '/api/read':
            port = qs.get('port', [''])[0]
            dev = MSRDevice(port, timeout=12)
            conn = dev.connect()
            if conn is True:
                res = dev.read_card()
                dev.close()
                self.send_json(res)
            else:
                self.send_json({'status': 'error', 'msg': conn[1] if isinstance(conn, tuple) else '打开端口失败'})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        if parsed.path == '/api/write':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode('utf-8'))
            except Exception:
                data = {}
            port = data.get('port', '')
            t1 = data.get('t1', '')
            t2 = data.get('t2', '')
            t3 = data.get('t3', '')
            dev = MSRDevice(port, timeout=12)
            conn = dev.connect()
            if conn is True:
                res = dev.write_card(t1=t1, t2=t2, t3=t3)
                dev.close()
                self.send_json(res)
            else:
                self.send_json({'status': 'error', 'msg': conn[1] if isinstance(conn, tuple) else '打开端口失败'})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


# ==============================
# 命令行交互模式
# ==============================
def cli_main():
    parser = argparse.ArgumentParser(description="超市会员卡 磁条卡读写工具 (DEFTUN MSR-X6)")
    parser.add_argument('--web', action='store_true', help='启动 Web 可视化管理界面')
    parser.add_argument('--port', type=int, default=8080, help='Web 服务端口 (默认 8080)')
    parser.add_argument('--device', type=str, default='', help='指定串口设备 (如 /dev/ttyUSB0 或 COM3)')
    parser.add_argument('--read', action='store_true', help='读取会员卡')
    parser.add_argument('--write', type=str, default='', help='写入会员卡号到第2磁道')
    parser.add_argument('--scan', action='store_true', help='扫描可用端口')
    args = parser.parse_args()

    if args.scan:
        ports = scan_ports()
        print(f"找到可用端口: {ports}")
        return

    if args.web:
        server = HTTPServer(('0.0.0.0', args.port), WebHandler)
        print(f"==================================================")
        print(f" 🎉 超市会员卡管理系统已启动 Web 界面！")
        print(f" 浏览器访问地址: http://127.0.0.1:{args.port}")
        print(f" 局域网访问地址: http://<你的IP>:{args.port}")
        print(f" 按 Ctrl+C 退出程序")
        print(f"==================================================")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n正在停止服务...")
            server.server_close()
        return

    # CLI 模式
    ports = scan_ports()
    dev_port = args.device
    if not dev_port:
        if ports:
            dev_port = ports[0]
            print(f"[*] 自动选择端口: {dev_port}")
        else:
            print("[!] 未检测到可用串口设备，请确认 USB 已插紧或已开机并配对蓝牙。")
            print("    可用参数: python3 msr_tool.py --web 启动网页版，或 --device /dev/ttyUSB0 手动指定。")
            return

    dev = MSRDevice(dev_port)
    conn = dev.connect()
    if conn is not True:
        print(f"[错误] 打开端口 {dev_port} 失败: {conn}")
        return

    if args.read:
        print(f"[*] 设备已进入读卡等待状态，请在 10 秒内刷卡...")
        res = dev.read_card()
        dev.close()
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.write:
        print(f"[*] 准备写入卡号: {args.write}")
        print(f"[*] 请拿好空白磁条卡，准备刷卡...")
        res = dev.write_card(t2=args.write)
        dev.close()
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        # 默认无参数时，启动网页模式
        print("未指定参数，默认启动 Web 管理界面...")
        server = HTTPServer(('0.0.0.0', args.port), WebHandler)
        print(f"浏览器访问: http://127.0.0.1:{args.port}")
        server.serve_forever()

if __name__ == '__main__':
    cli_main()
