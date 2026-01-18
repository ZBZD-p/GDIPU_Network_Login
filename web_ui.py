
import sys
import os
# Prioritize local 'libs' directory for dependencies
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs'))

from flask import Flask, render_template_string, request, jsonify, send_from_directory
import threading
import os
import json
import logging
import subprocess
import sys
import ctypes
import time
import requests
import socket
import base64
from GdipuSrunLogin.LoginManager import LoginManager

# Hide console window if packaged or running as script
def hide_console():
    if sys.platform == 'win32':
        try:
            kernel32 = ctypes.WinDLL('kernel32')
            user32 = ctypes.WinDLL('user32')
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0) # 0 = SW_HIDE
        except:
            pass

# Try importing pystray and Pillow for system tray
try:
    import pystray
    from PIL import Image
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    print("Warning: pystray or Pillow not installed. System tray icon will be disabled.")

# Silence Flask/Werkzeug logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
cli = sys.modules['flask.cli']
cli.show_server_banner = lambda *x: None

app = Flask(__name__)

CONFIG_FILE = "config.json"
STATE = {
    "log": [],
    "online": False,
    "config": {
        "username": "",
        "password": "",
        "auto_open_web": True,
        "auto_close_after_login": False,
        "auto_reconnect": True,
        "port": 56789
    }
}

def encrypt_pwd(s):
    if not s: return ""
    try:
        return "ENC_" + base64.b64encode(s.encode()).decode()
    except:
        return s

def decrypt_pwd(s):
    if not s: return ""
    if s.startswith("ENC_"):
        try:
            return base64.b64decode(s[4:].encode()).decode()
        except:
            return s
    return s

class LoggerWriter:
    def __init__(self, writer):
        self.writer = writer

    def write(self, message):
        self.writer.write(message)
        if message.strip():
            STATE["log"].append(message.strip())
            if len(STATE["log"]) > 100:
                 STATE["log"] = STATE["log"][-100:]

    def flush(self):
        self.writer.flush()

sys.stdout = LoggerWriter(sys.stdout)
sys.stderr = LoggerWriter(sys.stderr)

# ... (HTML_TEMPLATE omitted) ... 

def save_config_file():
    try:
        # Create a copy to encrypt password for storage
        cfg_to_save = STATE["config"].copy()
        if cfg_to_save["password"]:
            cfg_to_save["password"] = encrypt_pwd(cfg_to_save["password"])
            
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"config": cfg_to_save}, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存配置失败: {e}")

def save_config(username, password):
    STATE["config"]["username"] = username
    STATE["config"]["password"] = password
    save_config_file()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>广轻校园网自动认证系统</title>
    <style>
        :root {
            --primary: #4F46E5;
            --primary-hover: #4338CA;
            --danger: #EF4444;
            --danger-hover: #DC2626;
            --success: #10B981;
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            --glass-bg: rgba(255, 255, 255, 0.95);
            --glass-border: rgba(255, 255, 255, 0.2);
            --text-main: #1F2937;
            --text-sub: #6B7280;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg-gradient);
            min-height: 100vh;
            /* Allow scrolling */
            display: block;
            overflow-y: auto;
            color: var(--text-main);
            padding: 40px 20px;
        }

        #canvas-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
        }

        .container {
            z-index: 1;
            position: relative;
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            width: 100%;
            max-width: 600px; /* Increased width */
            padding: 40px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
            margin: 0 auto; /* Center horizontally */
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        header {
            text-align: center;
            margin-bottom: 32px;
            position: relative;
        }

        .status-dot {
            position: absolute;
            top: 10px;
            right: 10px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background-color: #9CA3AF;
            border: 2px solid white;
            box-shadow: 0 0 0 2px rgba(255,255,255,0.5);
            transition: all 0.3s;
        }

        .status-dot.online { background-color: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-dot.offline { background-color: var(--danger); box-shadow: 0 0 8px var(--danger); }
        
        .logo {
            width: 100%;
            max-width: 300px;
            height: auto;
            object-fit: contain;
            margin-bottom: 20px;
        }

        h1 {
            font-size: 22px; 
            font-weight: 800;
            color: #111827;
            margin-bottom: 8px;
            letter-spacing: -0.025em;
        }

        .subtitle {
            color: var(--text-sub);
            font-size: 14px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 600;
            color: #374151;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .input-wrapper {
            position: relative;
        }

        input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #E5E7EB;
            border-radius: 12px;
            font-size: 15px;
            transition: all 0.2s;
            outline: none;
            background: #F9FAFB;
        }

        input:focus {
            border-color: var(--primary);
            background: #fff;
            box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.1);
        }

        .main-actions {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
        }

        .btn {
            width: 100%;
            padding: 14px 20px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            position: relative;
            overflow: hidden;
        }

        /* 强烈的点击反馈 */
        .btn:active {
            transform: scale(0.96) translateY(1px);
            box-shadow: none !important;
            filter: brightness(0.9);
        }

        .btn-primary {
            background: var(--primary);
            color: white;
            box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.3), 0 2px 4px -1px rgba(79, 70, 229, 0.15);
        }

        .btn-primary:hover {
            background: var(--primary-hover);
            box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.4), 0 4px 6px -2px rgba(79, 70, 229, 0.2);
            transform: translateY(-1px);
        }
        
        .btn-primary:active {
            transform: scale(0.96) translateY(1px);
        }

        .btn-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 24px;
            border-top: 1px solid #E5E7EB;
            padding-top: 24px;
        }

        .btn-small {
            padding: 12px;
            font-size: 14px;
            /* Default / Inactive State (Gray) */
            background: #F9FAFB;
            color: #6B7280;
            border: 1px solid #E5E7EB;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: all 0.2s;
        }

        .btn-small:hover {
            background: #F3F4F6;
            color: #374151;
            transform: translateY(-1px);
        }
        
        /* Active / Selected State (Indigo Highlignt) */
        .btn-small.active-state {
            background: #EFF6FF;
            color: #4338CA;
            border-color: #818CF8;
            box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.2);
            font-weight: 700;
        }
        
        .btn-small.active-state:hover {
            background: #E0E7FF;
        }

        /* Toggle Switch CSS */
        .setting-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 24px;
            padding: 16px;
            background: rgba(255,255,255,0.6);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.3);
        }
        .setting-item span {
            font-size: 14px;
            color: #4B5563;
            font-weight: 500;
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 24px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 18px; width: 18px;
            left: 3px; bottom: 3px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider { background-color: #4F46E5; }
        input:checked + .slider:before { transform: translateX(20px); }

        /* 震动动画 */
        @keyframes shake {
            0% { transform: translateX(0); }
            25% { transform: translateX(-2px) rotate(-1deg); }
            50% { transform: translateX(2px) rotate(1deg); }
            75% { transform: translateX(-2px) rotate(-1deg); }
            100% { transform: translateX(0); }
        }
        
        .btn.shake-active {
            animation: shake 0.2s ease-in-out;
        }

        /* 粒子元素 */
        .particle-effect {
            position: absolute;
            pointer-events: none;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.8);
            transform: translate(-50%, -50%);
            animation: particle-anim 0.6s ease-out forwards;
        }

        @keyframes particle-anim {
            0% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
            100% { transform: translate(var(--tx), var(--ty)) scale(0); opacity: 0; }
        }

        .log-container {
            margin-top: 24px;
            background: #111827;
            border-radius: 12px;
            padding: 16px;
            height: 200px;
            overflow-y: auto;
            color: #E5E7EB;
            font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
            font-size: 12px;
            line-height: 1.6;
            border: 1px solid rgba(255,255,255,0.1);
        }

        .log-entry { margin-bottom: 4px; display: flex; gap: 8px; animation: fadeIn 0.3s ease-out; word-break: break-all; }
        @keyframes fadeIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
        .log-time { color: #6B7280; min-width: 65px; flex-shrink: 0; }
        
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #4B5563; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #6B7280; }

        .toast {
            position: fixed; top: 24px; left: 50%; transform: translateX(-50%) translateY(-100px);
            background: #1F2937; color: white; padding: 12px 24px; border-radius: 50px; font-size: 14px;
            font-weight: 500; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 100;
        }
        .toast.show { transform: translateX(-50%) translateY(0); }
        /* Toggle Button */
        .toggle-settings-btn {
            display: block;
            margin: 20px auto;
            background: none;
            border: none;
            color: #6B7280;
            cursor: pointer;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .toggle-settings-btn:hover { color: var(--primary); }

        #settings-panel {
            display: none;
            background: rgba(255,255,255,0.5);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 24px;
            border: 1px solid rgba(255,255,255,0.4);
            animation: slideDown 0.3s ease-out;
        }

        @keyframes slideDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <canvas id="canvas-bg"></canvas>
    <div id="toast" class="toast">操作成功</div>

    <div class="container">
        <header>
            <div id="status-dot" class="status-dot" title="Checking network..."></div>
            <a href="https://www.gdqy.edu.cn" target="_blank" title="访问学校官网">
                <img src="/logo.png" alt="Logo" class="logo" style="cursor: pointer; transition: transform 0.2s;">
            </a>
            <h1>广轻校园网自动认证系统</h1>
            <div class="subtitle" style="margin-top: 8px; font-size: 13px; color: #6B7280; font-weight: normal;">
                首次使用请输入账号密码，登录成功后会自动保存
            </div>
        </header>
        
        <div class="form-group">
            <label>学号 Account</label>
            <div class="input-wrapper">
                <input type="text" id="username" placeholder="请输入你的学号" value="{{ config.username }}">
            </div>
        </div>
        
        <div class="form-group">
            <label>密码 Password</label>
            <div class="input-wrapper">
                <input type="password" id="password" placeholder="请输入你的密码" value="{{ config.password }}">
            </div>
        </div>
        
        <button class="btn btn-primary" onclick="doLogin()">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            立即登录 (Login Now)
        </button>

        <!-- Startup Settings (Promoted) -->
        <div style="margin-top: 24px; padding: 16px; background: rgba(255,255,255,0.4); border-radius: 12px; border: 1px solid rgba(255,255,255,0.3);">
            <div style="font-size: 14px; font-weight: 600; color: #374151; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="color: #4F46E5;">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                开机自动启动认证校园网
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <button id="btn-startup-on" class="btn btn-small" onclick="enableStartup()" style="justify-content: center; font-size: 14px; padding: 10px;">
                    开启 (Enable)
                </button>
                <button id="btn-startup-off" class="btn btn-small" onclick="disableStartup()" style="justify-content: center; font-size: 14px; padding: 10px;">
                    关闭 (Disable)
                </button>
            </div>
        </div>

        <!-- Prioritize Logs visibility -->
        <h3 style="margin: 24px 0 8px 0; font-size: 14px; color: #374151; font-weight: 700;">运行日志 (Logs)</h3>
        <div class="log-container" id="log-box"></div>
        
        <!-- Toggle Button for Advanced Settings -->
        <button class="toggle-settings-btn" onclick="toggleSettings()">
            <svg id="settings-icon" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span>显示/隐藏 高级设置</span>
        </button>

        <!-- Collapsible Settings Panel -->
        <div id="settings-panel">
            <h4 style="margin: 0 0 16px 0; font-size: 13px; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em;">高级功能</h4>
            
            <div class="setting-item">
                <span>启动时自动显示网页</span>
                <label class="switch">
                    <input type="checkbox" id="auto-open-toggle" onchange="toggleAutoOpen()" {% if config.get('auto_open_web', True) %}checked{% endif %}>
                    <span class="slider round"></span>
                </label>
            </div>

            <div class="setting-item">
                <span>断网自动重连</span>
                <label class="switch">
                    <input type="checkbox" id="auto-reconnect-toggle" onchange="toggleAutoReconnect()" {% if config.get('auto_reconnect', True) %}checked{% endif %}>
                    <span class="slider round"></span>
                </label>
            </div>

            <div class="setting-item">
                <div style="display:flex; flex-direction:column;">
                    <span>认证成功后自动退出程序</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="auto-close-toggle" onchange="toggleAutoClose()" {% if config.get('auto_close_after_login', False) %}checked{% endif %}>
                    <span class="slider round"></span>
                </label>
            </div>

            <div class="setting-item" style="margin-top: 12px;">
                <span>服务端口 (重启生效)</span>
                <input type="number" id="port-input" value="{{ config.get('port', 56789) }}" onchange="updatePort()" style="width: 80px; padding: 4px; border-radius: 4px; border: 1px solid #ccc; text-align: center;">
            </div>

            <div class="setting-item" style="margin-top: 12px; background: rgba(255, 69, 58, 0.1); border: 1px solid rgba(255, 69, 58, 0.2);">
                <span style="color: #c0392b;">重置所有设置</span>
                <button class="btn-small" onclick="resetSettings()" style="background: #ef4444; color: white; padding: 4px 12px; font-size: 12px;">重置</button>
            </div>
        </div>
    </div>

    <div style="position: fixed; bottom: 8px; right: 12px; font-size: 11px; font-family: sans-serif; z-index: 50;">
        <a href="https://github.com/ZBZD-p" target="_blank" style="color: rgba(107, 114, 128, 0.5); text-decoration: none; transition: color 0.3s;" onmouseover="this.style.color='rgba(79, 70, 229, 0.8)'" onmouseout="this.style.color='rgba(107, 114, 128, 0.5)'">
            Powered by ZBZD
        </a>
    </div>
    <script>
        // Particle Animation
        const canvas = document.getElementById('canvas-bg');
        const ctx = canvas.getContext('2d');
        let particlesArray;
        function resizeCanvas() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
        window.addEventListener('resize', () => { resizeCanvas(); init(); });
        resizeCanvas();
        class Particle {
            constructor(x, y, dX, dY, size, color) { this.x=x;this.y=y;this.dX=dX;this.dY=dY;this.size=size;this.color=color; }
            draw() { ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI*2, false); ctx.fillStyle=this.color; ctx.fill(); }
            update() {
                if(this.x>canvas.width||this.x<0) this.dX=-this.dX;
                if(this.y>canvas.height||this.y<0) this.dY=-this.dY;
                this.x+=this.dX; this.y+=this.dY; this.draw();
            }
        }
        function init() {
            particlesArray = []; let n = (canvas.height*canvas.width)/9000;
            for(let i=0;i<n;i++){
                let s=(Math.random()*2)+1;
                let x=(Math.random()*((innerWidth-s*2)-(s*2))+s*2);
                let y=(Math.random()*((innerHeight-s*2)-(s*2))+s*2);
                particlesArray.push(new Particle(x, y, (Math.random())-0.5, (Math.random())-0.5, s, 'rgba(255,255,255,0.4)'));
            }
        }
        function connect() {
            for(let a=0;a<particlesArray.length;a++){
                for(let b=a;b<particlesArray.length;b++){
                    let d = ((particlesArray[a].x-particlesArray[b].x)**2)+((particlesArray[a].y-particlesArray[b].y)**2);
                    if(d<(canvas.width/7)*(canvas.height/7)){
                        ctx.strokeStyle = 'rgba(255,255,255,'+(1-(d/20000))*0.2+')';
                        ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(particlesArray[a].x, particlesArray[a].y);
                        ctx.lineTo(particlesArray[b].x, particlesArray[b].y); ctx.stroke();
                    }
                }
            }
        }
        function animate() { requestAnimationFrame(animate); ctx.clearRect(0,0,innerWidth,innerHeight); particlesArray.forEach(p=>p.update()); connect(); }
        init(); animate();

        // Button Ripple & Shake Effect
        function createParticles(e) {
            const btn = e.currentTarget;
            
            // 1. Shake Effect
            btn.classList.remove('shake-active');
            void btn.offsetWidth; // trigger reflow
            btn.classList.add('shake-active');

            // 2. Particle Explosion
            const rect = btn.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const color = btn.classList.contains('btn-primary') ? ['#ffffff', '#818cf8', '#c7d2fe'] : ['#4f46e5', '#818cf8', '#6366f1'];

            for(let i=0; i<12; i++) {
                const p = document.createElement('div');
                p.classList.add('particle-effect');
                p.style.left = x + 'px';
                p.style.top = y + 'px';
                p.style.background = color[Math.floor(Math.random()*color.length)];
                
                // Random destination
                const tx = (Math.random() - 0.5) * 100 + 'px';
                const ty = (Math.random() - 0.5) * 100 + 'px';
                p.style.setProperty('--tx', tx);
                p.style.setProperty('--ty', ty);
                
                btn.appendChild(p);
                setTimeout(() => p.remove(), 600);
            }
        }

        document.querySelectorAll('.btn').forEach(btn => {
            btn.addEventListener('click', createParticles);
        });

        // UI Logic
        function showToast(msg, isError = false) {
            const toast = document.getElementById('toast');
            toast.innerText = msg; toast.style.background = isError ? '#EF4444' : '#1F2937';
            toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3000);
        }
        // Initialize log state
        let processedLogCount = 0;

        function log(msg) {
            const box = document.getElementById('log-box');
            const time = new Date().toLocaleTimeString('en-US', {hour12: false});
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `<span class="log-time">[${time}]</span><span>${msg}</span>`;
            box.appendChild(entry); 
            // Don't auto-scroll here anymore
        }

        setInterval(() => {
            fetch('/api/logs').then(r => r.json()).then(data => {
                const logs = data.logs || [];
                // Only process new logs
                if (logs.length > processedLogCount) {
                    const box = document.getElementById('log-box');
                    // Smart Scrolling Check: Check before appending
                    // Tolerance of 50px
                    const isAtBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 50;

                    const newLogs = logs.slice(processedLogCount);
                    newLogs.forEach(msg => log(msg));
                    
                    processedLogCount = logs.length;

                    // Only scroll if user was already at bottom or it's the first load
                    if (isAtBottom || processedLogCount === newLogs.length) {
                         box.scrollTop = box.scrollHeight;
                    }
                }
            });
            fetch('/api/status').then(r => r.json()).then(data => {
                const dot = document.getElementById('status-dot');
                if (data.online) {
                    dot.className = 'status-dot online'; dot.title = 'Online';
                } else {
                    dot.className = 'status-dot offline'; dot.title = 'Offline';
                }
            });
            checkStartupStatus();
        }, 2000);

        function checkStartupStatus() {
            fetch('/api/startup/status').then(r => r.json()).then(data => {
                const btnOn = document.getElementById('btn-startup-on');
                const btnOff = document.getElementById('btn-startup-off');
                if (data.enabled) {
                    btnOn.classList.add('active-state');
                    btnOff.classList.remove('active-state');
                } else {
                    btnOn.classList.remove('active-state');
                    btnOff.classList.add('active-state');
                }
            });
        }
        checkStartupStatus(); // Initial run

        function doLogin() {
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            if(!u || !p) return showToast("请填写完整的账号和密码", true);
            log("正在发起登录...");
            fetch('/api/login', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username:u, password:p})
            }).then(r => r.json()).then(data => showToast(data.msg));
        }



        function enableStartup() {
            log("正在执行：开启开机自启...");
            fetch('/api/startup/enable', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    showToast(data.msg);
                    checkStartupStatus();
                });
        }
        function disableStartup() {
            log("正在执行：关闭开机自启...");
            fetch('/api/startup/disable', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    showToast(data.msg);
                    checkStartupStatus();
                });
        }
        
        function toggleSettings() {
            const panel = document.getElementById('settings-panel');
            if (panel.style.display === 'block') {
                panel.style.display = 'none';
            } else {
                panel.style.display = 'block';
            }
        }

        function toggleAutoOpen() {
            const isChecked = document.getElementById('auto-open-toggle').checked;
            fetch('/api/settings/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({auto_open_web: isChecked})
            }).then(r => r.json()).then(data => showToast(data.msg));
        }

        function toggleAutoClose() {
            const isChecked = document.getElementById('auto-close-toggle').checked;
            
            // Linkage: If Auto-Close ON -> Auto-Reconnect OFF
            if (isChecked) {
                document.getElementById('auto-reconnect-toggle').checked = false;
                fetch('/api/settings/update', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ auto_close_after_login: true, auto_reconnect: false })
                }).then(r => r.json()).then(data => showToast("已开启自动退出 (自动重连已关闭)"));
            } else {
                // Just toggle off
                fetch('/api/settings/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ auto_close_after_login: false })
                }).then(r => r.json()).then(data => showToast(data.msg));
            }
        }

        function toggleAutoReconnect() {
            const isChecked = document.getElementById('auto-reconnect-toggle').checked;

            // Linkage: If Auto-Reconnect ON -> Auto-Close OFF
            if (isChecked) {
                document.getElementById('auto-close-toggle').checked = false;
                fetch('/api/settings/update', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ auto_reconnect: true, auto_close_after_login: false })
                }).then(r => r.json()).then(data => showToast("已开启自动重连 (自动退出已关闭)"));
            } else {
                 // Just toggle off
                fetch('/api/settings/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ auto_reconnect: false })
                }).then(r => r.json()).then(data => showToast(data.msg));
            }
        }

        function updatePort() {
            const port = document.getElementById('port-input').value;
            fetch('/api/settings/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({port: parseInt(port)})
            }).then(r => r.json()).then(data => showToast("端口已保存，请重启程序"));
        }

        function resetSettings() {
            if(confirm("确定要重置所有设置吗？这将清除保存的密码和自启配置。")) {
                fetch('/api/settings/reset', {method: 'POST'})
                .then(r => r.json()).then(data => {
                    showToast(data.msg);
                });
            }
        }
    </script>
</body>
</html>
"""

def add_log(msg):
    print(msg)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                # Keep compatibility with both structures if possible, or just standard "config" key
                if "config" in saved:
                    STATE["config"].update(saved["config"])
                else:
                    STATE["config"].update(saved)
                
                # Decrypt password
                if STATE["config"]["password"]:
                    STATE["config"]["password"] = decrypt_pwd(STATE["config"]["password"])
        except:
            pass



def login_thread(username, password):
    lm = LoginManager()
    try:
        print(">>> 正在初始化登录...")
        lm.login(username=username, password=password)
        print(">>> 登录流程结束")
        
        # Auto-Close Feature
        if STATE["config"].get("auto_close_after_login", False):
            def check_and_exit():
                print(">>> [自动关闭] 程序已就绪，将在20秒后开始验证网络并退出...")
                time.sleep(20)
                
                print(">>> [自动关闭] 正在验证互联网连接...")
                # Try pinging up to 5 times
                # Try pinging up to 5 times
                for i in range(5):
                    try:
                        # Verify using HTTP request (MIUI 204)
                        r = requests.get("http://connect.rom.miui.com/generate_204", timeout=5, headers={"User-Agent": "NetworkCheck"})
                        if r.status_code == 204:
                            print(">>> [自动关闭] 网络连接正常！程序将在10秒后退出...")
                            time.sleep(10.0)
                            os._exit(0)
                        else:
                            print(f">>> [检测] 连接测试失败 (状态码: {r.status_code})...")
                    except Exception as e:
                        print(f">>> [检测] 出错: {e}")
                    time.sleep(2)
                print(">>> [自动关闭] ⚠️ 网络验证失败 (无法连接外网)")
                print(">>> [自动关闭] 已取消自动退出，请检查网络设置。")
            
            threading.Thread(target=check_and_exit, daemon=True).start()
    except Exception as e:
        err_msg = str(e)
        if "NoneType" in err_msg and "group" in err_msg:
             print(">>> 登录失败：无法从页面获取IP。")
             print(">>> 可能原因：1. 你已经在线了 2. 网络未连接 3. 登录页改版")
        else:
             print(f">>> 登录出错: {err_msg}")

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    u = data.get("username", "")
    p = data.get("password", "")
    save_config(u, p)
    t = threading.Thread(target=login_thread, args=(u, p), daemon=True)
    t.start()
    return jsonify({"msg": "已触发后台登录"})

def network_monitor():
    # Silent startup
    while True:
        try:
            # Use HTTP request to detect captive portal or network failure
            # MIUI generate_204 is very stable in China
            r = requests.get("http://connect.rom.miui.com/generate_204", timeout=5, headers={"User-Agent": "NetworkCheck"})
            if r.status_code == 204:
                if not STATE["online"]:
                    print(">>> [监控] 网络已连接")
                STATE["online"] = True
            else:
                raise Exception(f"Captive portal detected (Status: {r.status_code})")
        except:
            if STATE["online"]:
                print(">>> [监控] 网络已断开")
            STATE["online"] = False
            
            # Auto-reconnect ONLY if configured
            if STATE["config"].get("auto_reconnect", True):
                u = STATE["config"]["username"]
                p = STATE["config"]["password"]
                if u and p:
                    print(">>> [监控] 尝试自动重连...")
                    threading.Thread(target=login_thread, args=(u, p), daemon=True).start()
                    time.sleep(10) # Wait a bit longer before next check
        time.sleep(5)

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, config=STATE["config"])

@app.route('/logo.png')
def serve_logo():
    return send_from_directory('.', 'logo.png')

@app.route('/api/logs')
def get_logs():
    # Return all logs, don't clear them on server side. 
    # Frontend will handle display.
    logs = STATE["log"][:]
    return jsonify({"logs": logs})

@app.route('/api/status')
def get_status():
    return jsonify({"online": STATE["online"]})

@app.route('/api/startup/status')
def get_startup_status():
    startup_path = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup', 'SrunAutoLogin.lnk')
    return jsonify({"enabled": os.path.exists(startup_path)})

@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    data = request.json
    for k, v in data.items():
        if k in STATE["config"]:
            # Type conversion for port
            if k == 'port':
                try: v = int(v)
                except: continue
            STATE["config"][k] = v
    save_config_file()
    return jsonify({"msg": "设置已保存"})

@app.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    STATE["config"] = {
        "username": "",
        "password": "",
        "auto_open_web": True,
        "port": 56789
    }
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
    except:
        pass
    return jsonify({"msg": "重置成功，请重启程序生效"})

@app.route('/api/startup/enable', methods=['POST'])
def enable_startup():
    try:
        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "启动校园网助手.bat")
        link_path = os.path.join(startup_dir, "SrunAutoLogin.lnk")
        working_dir = os.path.dirname(os.path.abspath(__file__))
        
        if not os.path.exists(script_path):
             return jsonify({"msg": "找不到启动脚本文件"})

        vbs_content = f"""
        Set oWS = WScript.CreateObject("WScript.Shell")
        sLinkFile = "{link_path}"
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = "{script_path}"
        oLink.WorkingDirectory = "{working_dir}"
        oLink.Description = "校园网自动登录助手"
        oLink.Save
        """
        vbs_path = os.path.join(os.environ["TEMP"], "create_shortcut.vbs")
        with open(vbs_path, "w", encoding="gbk") as f:
            f.write(vbs_content)
        subprocess.run(["cscript", "/nologo", vbs_path], check=True, shell=True)
        if os.path.exists(vbs_path): os.remove(vbs_path)
        add_log("已创建开机启动快捷方式")
        return jsonify({"msg": "设置成功！下次开机将自动启动"})
    except Exception as e:
        add_log(f"设置失败: {e}")
        return jsonify({"msg": f"设置失败: {str(e)}"})

@app.route('/api/startup/disable', methods=['POST'])
def disable_startup():
    try:
        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        link_path = os.path.join(startup_dir, "SrunAutoLogin.lnk")
        if os.path.exists(link_path):
            os.remove(link_path)
            add_log("已删除开机启动快捷方式")
            return jsonify({"msg": "已取消开机自启"})
        else:
            return jsonify({"msg": "未发现开机启动项"})
    except Exception as e:
        add_log(f"执行失败: {e}")
        return jsonify({"msg": f"执行失败: {str(e)}"})


def setup_tray(server_port):
    if not HAS_TRAY: return

    def open_web():
        subprocess.Popen(f"start http://127.0.0.1:{server_port}", shell=True)
    
    def on_exit(icon):
        icon.stop()
        os._exit(0)

    image = Image.open("tray_icon.png")
    menu = pystray.Menu(
        pystray.MenuItem("打开管理页面", open_web, default=True),
        pystray.MenuItem("退出", on_exit)
    )
    icon = pystray.Icon("SrunLogin", image, "广轻校园网认证", menu)
    icon.run()

if __name__ == '__main__':
    # Attempt to hide console immediately
    hide_console()

    # Load config FIRST to get customized port
    load_config()
    PORT = int(STATE["config"].get("port", 56789))
    
    # 1. Start Network Monitor
    threading.Thread(target=network_monitor, daemon=True).start()
    
    # 2. Auto-login ONCE on startup if config exists
    u = STATE["config"]["username"]
    p = STATE["config"]["password"]
    if u and p:
        print(f"Auto-login triggered for user: {u}")
        threading.Thread(target=login_thread, args=(u, p), daemon=True).start()
    
    print(f"启动 Web 界面: http://127.0.0.1:{PORT}")
    print("服务正在运行... (请查看系统托盘图标)")

    # 3. Start Flask in a background thread
    def run_flask():
        try:
            # Bind to 127.0.0.1 to avoid firewall popups and ensure local access
            app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
        except Exception as e:
            with open("flask_error.txt", "w", encoding="utf-8") as f:
                f.write(str(e))
                
    threading.Thread(target=run_flask, daemon=True).start()

    # 4. Auto Open Browser (Configurable)
    if STATE["config"].get("auto_open_web", True):
        # Use system 'start' command which is more reliable than webbrowser module in embedded environments
        def open_browser():
            if sys.platform == 'win32':
                os.system(f'start http://127.0.0.1:{PORT}')
            else:
                import webbrowser
                webbrowser.open(f'http://127.0.0.1:{PORT}')
                
        threading.Timer(2.0, open_browser).start()

    # 5. Start Tray Icon (Main Thread)
    if HAS_TRAY:
        try:
            setup_tray(PORT)
        except Exception as e:
            print(f"托盘图标启动失败: {e}")
            while True: time.sleep(1)
    else:
        while True: time.sleep(1)
