#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Update-Free v1.6.0
Ứng dụng quét toàn diện Combos & Mô hình AI Miễn phí từ 9router / OmniRouter
và đồng bộ đa tầng an toàn vào cấu hình OpenCode (opencode.json, opencode.jsonc & auth.json).

Nâng cấp trọng tâm v1.6.0:
1. Khắc phục triệt để lỗi OpenCode Desktop (v1.19.x / v2.x) & OpenCode CLI không nhận model/provider mới:
   - Đồng bộ đồng thời vào CẢ 2 file cấu hình '~/.config/opencode/opencode.json' VÀ 'opencode.jsonc'
     (loại bỏ hoàn toàn lỗi opencode.json ghi đè hoặc che khuất opencode.jsonc).
   - Tự động đăng ký thông tin xác thực API Key của '9router' và 'omnirouter' vào file
     '~/.local/share/opencode/auth.json' (giúp cả 9router và OmniRouter xuất hiện ngay trong mục
     "Nhà cung cấp được kết nối" của OpenCode Desktop v1.19.3).
   - Tự động nhận diện Provider ID đã tồn tại của 9router/OmniRouter (theo ID, tên hoặc endpoint URL)
     và dọn sạch các khóa chặn 'whitelist'/'blacklist'/'disabled_providers'.
   - Bổ sung đầy đủ schema model chuẩn OpenCode ('id', 'name', 'tool_call': True, 'temperature': True)
     và khai báo song song cả 'api' lẫn 'options.baseURL'.
   - Parser JSONC Lexer theo từng ký tự (State-machine): Không bao giờ làm hỏng chuỗi chứa '//' hoặc '/*'.
2. Thiết kế lại toàn bộ Hộp thoại Xác nhận, Thêm mô hình & Thông báo bằng CustomTkinter (CTkToplevel):
   - Thay thế hoàn toàn tkinter.messagebox cổ điển (vốn bị hẹp ngang 220px và lệch tông giao diện)
     bằng các hộp thoại phẳng, hiện đại, rộng rãi, có bảng thống kê chi tiết và danh sách xem trước.
3. Sửa triệt để lỗi cỡ chữ to cắt tên model trên màn hình HiDPI X11 & Khôi phục 100% Tiếng Việt có dấu:
   - Sử dụng kích thước pixel âm (-12, -10) cho tk.Label trong danh sách giúp hiển thị trọn vẹn tên model dài.
   - Bố cục lại thanh điều khiển và thanh công cụ lọc 2 cột để không bao giờ bị tràn hay cắt chữ.
"""

import json
import os
import sys
import socket
import signal
import subprocess
import threading
import time
import queue
import re
from collections import defaultdict, deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple, Set, Callable

import requests
import customtkinter as ctk
import tkinter as tk

# ==================== CẤU HÌNH GIAO DIỆN & MÔI TRƯỜNG ====================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_NAME = "Auto-Update-Free"
APP_VERSION = "1.6.0"
CONFIG_DIR = Path.home() / ".config" / "auto-update-free"
CONFIG_FILE = CONFIG_DIR / "config.json"
IPC_PORT = 20129  # Cổng giao tiếp đơn phiên nội bộ (127.0.0.1)


# ==================== QUẢN LÝ ĐƠN PHIÊN (SINGLE INSTANCE IPC) ====================
class SingleInstanceController:
    """Đảm bảo chỉ có duy nhất 1 cửa sổ ứng dụng hoạt động và kích hoạt cửa sổ khi mở lần 2."""
    def __init__(self, on_activate_callback=None):
        self.on_activate = on_activate_callback
        self.server_sock = None
        self.running = False

    def check_and_notify_running(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.8)
            s.connect(('127.0.0.1', IPC_PORT))
            s.sendall(b'ACTIVATE\n')
            s.close()
            return True
        except Exception:
            return False

    def start_listener(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(('127.0.0.1', IPC_PORT))
            self.server_sock.listen(5)
            self.running = True

            thread = threading.Thread(target=self._listen_loop, daemon=True)
            thread.start()
        except Exception as e:
            print(f"Không thể khởi động IPC Listener: {e}")

    def _listen_loop(self):
        while self.running:
            try:
                conn, _ = self.server_sock.accept()
                data = conn.recv(1024).decode('utf-8', errors='ignore').strip()
                if data == 'ACTIVATE' and self.on_activate:
                    self.on_activate()
                conn.close()
            except Exception:
                break

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass


# ==================== QUẢN LÝ CẤU HÌNH ROUTER ====================
class ConfigManager:
    OLD_OMNI_KEYS = {
        "sk-c8231f142e2df954-6df89e-431c37d5",
        ""
    }

    DEFAULT_CONFIG = {
        "9router": {
            "name": "9router (Local)",
            "endpoint": "http://localhost:20128/v1",
            "api_key": "sk-921042c36766f489-qjn67j-65503176"
        },
        "omnirouter": {
            "name": "OmniRouter (NAS)",
            "endpoint": "http://son-server.tail8cd54f.ts.net:20128/v1",
            "api_key": "sk-c8231f142e2df954-7a548c-a6588128"
        },
        "opencode_path": "",
        "deep_scan_providers": True,
        "include_auto_combos": False,
        "replace_router_models": True
    }

    @staticmethod
    def sanitize_endpoint(ep: str) -> str:
        """Làm sạch lỗi dính chữ ở endpoint (ví dụ '.../v1api' -> '.../v1')."""
        ep = ep.strip().rstrip('/')
        ep = re.sub(r'/v1api.*$', '/v1', ep, flags=re.IGNORECASE)
        if ep and not ep.endswith('/v1'):
            if re.match(r'^https?://[^/]+$', ep):
                ep = ep + '/v1'
        return ep

    @classmethod
    def load(cls) -> Dict:
        merged = json.loads(json.dumps(cls.DEFAULT_CONFIG))
        need_resave = False

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                        merged[k] = {**merged[k], **v}
                    else:
                        merged[k] = v

                # Tự động nâng cấp API key cũ của OmniRouter sang API key mới
                omni_key = merged.get("omnirouter", {}).get("api_key", "").strip()
                if omni_key in cls.OLD_OMNI_KEYS:
                    merged["omnirouter"]["api_key"] = cls.DEFAULT_CONFIG["omnirouter"]["api_key"]
                    need_resave = True

                # Làm sạch endpoint của cả 2 router
                for r_key in ("9router", "omnirouter"):
                    raw_ep = merged.get(r_key, {}).get("endpoint", "")
                    clean_ep = cls.sanitize_endpoint(raw_ep)
                    if clean_ep != raw_ep:
                        merged[r_key]["endpoint"] = clean_ep
                        need_resave = True

            except Exception as e:
                print(f"Lỗi đọc config.json: {e}")

        if need_resave or not CONFIG_FILE.exists():
            cls.save(merged)

        return merged

    @classmethod
    def save(cls, config: Dict) -> bool:
        try:
            for r_key in ("9router", "omnirouter"):
                if r_key in config and isinstance(config[r_key], dict):
                    config[r_key]["endpoint"] = cls.sanitize_endpoint(config[r_key].get("endpoint", ""))
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Lỗi lưu config.json: {e}")
            return False


# ==================== API CLIENT ĐA TẦNG SIÊU TỐC ====================
class APIClient:
    NO_ACCOUNT_KEYWORDS = (
        "no active account",
        "all accounts unavailable",
        "no account",
        "no credentials",
        "provider not configured",
        "not configured",
        "no available account",
        "no healthy account",
        "account not found",
        "unauthorized",
        "invalid api key"
    )

    def __init__(self, endpoint: str, api_key: str, timeout: int = 12):
        self.endpoint = ConfigManager.sanitize_endpoint(endpoint)
        self.base_root = re.sub(r'/v1/?$', '', self.endpoint)
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=40, pool_maxsize=40)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        if self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })
        else:
            self.session.headers.update({"Content-Type": "application/json"})

    def fetch_models_and_verify(self) -> Tuple[bool, List[Dict], str]:
        if not self.endpoint:
            return False, [], "Chưa cấu hình Endpoint"

        try:
            resp = self.session.get(f"{self.endpoint}/models", timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                models = []
                if isinstance(data, dict):
                    models = data.get('data', data.get('models', []))
                elif isinstance(data, list):
                    models = data
                return True, models, f"OK ({len(models)} models)"
            elif resp.status_code in (401, 403):
                return False, [], f"Sai API Key hoặc không có quyền (HTTP {resp.status_code})"
            else:
                return False, [], f"HTTP {resp.status_code}: {resp.text[:80]}"
        except requests.exceptions.Timeout:
            return False, [], "Quá thời gian chờ tải models (>25s)"
        except requests.exceptions.ConnectionError:
            return False, [], f"Không thể kết nối tới {self.endpoint}"
        except Exception as e:
            return False, [], f"Lỗi: {str(e)[:80]}"

    def fetch_combos_endpoint(self) -> Tuple[List[Dict], Set[str]]:
        combos_list = []
        member_ids: Set[str] = set()
        for path in ("/v1/combos", "/api/combos"):
            url = f"{self.base_root}{path}"
            try:
                resp = self.session.get(url, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = []
                    if isinstance(data, list):
                        raw_items = data
                    elif isinstance(data, dict):
                        raw_items = data.get("combos", data.get("data", []))

                    if isinstance(raw_items, list):
                        for item in raw_items:
                            if not isinstance(item, dict):
                                continue
                            c_name = str(item.get("name") or item.get("id") or "").strip()
                            if c_name:
                                combos_list.append({
                                    "id": c_name,
                                    "name": c_name,
                                    "owned_by": "combo"
                                })
                            members = item.get("models", [])
                            if isinstance(members, list):
                                for mem in members:
                                    if isinstance(mem, str) and mem.strip():
                                        clean_mem = mem.strip().split()[0]
                                        member_ids.add(clean_mem)
                                    elif isinstance(mem, dict):
                                        m_str = str(mem.get("model") or mem.get("id") or "").strip()
                                        if m_str:
                                            member_ids.add(m_str.split()[0])
                    if combos_list:
                        break
            except Exception:
                pass
        return combos_list, member_ids

    def test_model_ping(self, model_id: str, timeout: float = 10.0) -> Tuple[bool, int, str]:
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 6,
            "stream": False
        }

        for attempt in range(2):
            start_time = time.time()
            try:
                resp = self.session.post(
                    f"{self.endpoint}/chat/completions",
                    json=payload,
                    timeout=(4.0, timeout)
                )
                elapsed_ms = int((time.time() - start_time) * 1000)

                if resp.status_code == 200:
                    try:
                        body = resp.json()
                        if isinstance(body, dict) and "error" in body and not body.get("choices"):
                            err_msg = str(body["error"])[:50]
                            err_lower = err_msg.lower()
                            if any(k in err_lower for k in self.NO_ACCOUNT_KEYWORDS):
                                return False, elapsed_ms, "NO_ACCOUNT: API Error"
                            return False, elapsed_ms, f"API Error: {err_msg[:35]}"
                    except Exception:
                        pass
                    return True, elapsed_ms, f"{elapsed_ms}ms"

                elif resp.status_code == 429 and attempt == 0:
                    time.sleep(0.8)
                    continue
                elif resp.status_code == 429:
                    return False, elapsed_ms, "Rate limited (429)"
                else:
                    err_text = ""
                    try:
                        err_text = resp.text[:160].lower()
                    except Exception:
                        pass
                    if resp.status_code in (401, 403, 503) or any(k in err_text for k in self.NO_ACCOUNT_KEYWORDS):
                        if any(k in err_text for k in self.NO_ACCOUNT_KEYWORDS) or resp.status_code == 503:
                            return False, elapsed_ms, f"NO_ACCOUNT (HTTP {resp.status_code})"
                    return False, elapsed_ms, f"HTTP {resp.status_code}"

            except requests.exceptions.Timeout:
                elapsed_ms = int((time.time() - start_time) * 1000)
                return False, elapsed_ms, f"Timeout (>{int(timeout)}s)"
            except Exception:
                elapsed_ms = int((time.time() - start_time) * 1000)
                return False, elapsed_ms, "Lỗi kết nối"

        return False, 0, "Thất bại"


# ==================== BỘ PHÂN LOẠI COMBOS & FREE MODELS THÔNG MINH ====================
class ModelAnalyzer:
    FREE_PATTERN = re.compile(
        r'(:free\b|-free\b|/free\b|\(free\)|\[free\]|_free\b|\bfree\b|\bfreemium\b|\bgratis\b|\bno-cost\b|zero-cost)',
        re.IGNORECASE
    )

    COMBO_KEYWORD_PATTERN = re.compile(
        r'(\bcombo\b|\bcombos\b|\bloadbalance\b|\bauto-route\b|\brouting-group\b|\ball-in-one\b|^combo[-_/])',
        re.IGNORECASE
    )

    CORE_FREE_PROVIDER_PREFIXES = {
        'oc', 'opencode',               # OpenCode Free (100% Free)
        'ag', 'agy', 'antigravity',     # Antigravity (Google OAuth Free)
        'kc', 'kilo', 'kilocode',       # Kilo-Code Free
        'kgw', 'kilogateway',           # Kilo-Gateway Free
        'bzl', 'bazaarlink',            # BazaarLink Free
        'gc', 'gemini-cli',             # Gemini-CLI OAuth
        'ollama', 'ollama-cloud',       # Ollama Cloud Free
        'ollama-local',                 # Ollama Local (Self-hosted)
        'ps', 'poolside',               # Poolside Free
        'kr', 'kiro',                   # Kiro AI Free tier
        'pollinations', 'pl',           # Pollinations Free
        'llm7',                         # LLM7 Free tier
        'publicai',                     # PublicAI Free tier
        'longcat',                      # LongCat Free tier
        'inclusionai',                  # InclusionAI Free tier
        'uncloseai',                    # UncloseAI Free
        'duckduckgo-web', 'ddg',        # Duck.ai Free
        'felo',                         # Felo Free
        'puter',                        # Puter Free
        'hackclub',                     # HackClub Free
    }

    FREE_PROVIDER_PREFIXES = CORE_FREE_PROVIDER_PREFIXES | {
        'gemini',                       # Google AI Studio Free tier
        'nvidia', 'nim',                # NVIDIA NIM Free tier
        'groq',                         # Groq Free tier
        'cerebras',                     # Cerebras Free tier
        'sambanova',                    # SambaNova Free tier
        'cloudflare-ai', 'cf',          # Cloudflare Workers AI Free
        'huggingface', 'hf',            # HuggingFace Free
        'huggingchat',                  # HuggingChat Free
        'arcee-ai', 'arcee',            # Arcee Free
        'cohere',                       # Cohere Free Trial
        'mistral',                      # Mistral Free Experiment tier
        'siliconflow',                  # SiliconFlow Free
        'sparkdesk', 'iflytek',         # Spark Lite Free
        'tencent',                      # Hunyuan Lite Free
        'baidu',                        # ERNIE Speed/Lite Free
        'github', 'github-models',      # GitHub Models Free
        'if', 'iflow',                  # iFlow
        'qw', 'qwen',                   # Qwen
    }

    @classmethod
    def is_combo(
        cls,
        model: Dict,
        known_combo_ids: Optional[Set[str]] = None,
        include_auto_combos: bool = False
    ) -> bool:
        mid = str(model.get('id', '')).strip()
        if not mid:
            return False

        if known_combo_ids and mid in known_combo_ids:
            return True

        if mid.lower().startswith('auto/'):
            return bool(include_auto_combos)

        owned_by = str(model.get('owned_by', '')).strip().lower()
        m_type = str(model.get('type', '')).strip().lower()
        m_obj = str(model.get('object', '')).strip().lower()

        if owned_by == 'combo' or m_type == 'combo' or m_obj == 'combo' or model.get('isCombo') is True:
            return True

        if '/' not in mid:
            return True

        if cls.COMBO_KEYWORD_PATTERN.search(mid):
            return True

        return False

    @classmethod
    def is_explicit_free(cls, model: Dict, combo_member_ids: Optional[Set[str]] = None) -> bool:
        mid = str(model.get('id', '')).strip()
        mname = str(model.get('name', '') or mid).strip()
        if not mid:
            return False

        if combo_member_ids and mid in combo_member_ids:
            return True

        if cls.FREE_PATTERN.search(f"{mid} {mname}"):
            return True

        if model.get('free') is True or model.get('isFree') is True or str(model.get('tier', '')).lower() == 'free':
            return True

        pricing = model.get('pricing')
        if isinstance(pricing, dict):
            prompt_cost = pricing.get('prompt', pricing.get('input'))
            if prompt_cost is not None:
                try:
                    if float(prompt_cost) == 0.0:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    @classmethod
    def is_free_model(
        cls,
        model: Dict,
        combo_member_ids: Optional[Set[str]] = None,
        deep_scan_providers: bool = True
    ) -> bool:
        mid = str(model.get('id', '')).strip()
        if not mid or mid.lower().startswith('auto/'):
            return False

        if cls.is_explicit_free(model, combo_member_ids):
            return True

        if deep_scan_providers and '/' in mid:
            prefix = mid.split('/', 1)[0].lower()
            if prefix in cls.FREE_PROVIDER_PREFIXES:
                return True

        return False

    @classmethod
    def categorize_models(
        cls,
        models: List[Dict],
        api_combos: Optional[List[Dict]] = None,
        combo_member_ids: Optional[Set[str]] = None,
        deep_scan_providers: bool = True,
        include_auto_combos: bool = False
    ) -> Dict[str, List[Dict]]:
        known_combo_ids: Set[str] = set()
        if api_combos:
            for c in api_combos:
                cid = str(c.get('id', '')).strip()
                if cid:
                    known_combo_ids.add(cid)

        combos_dict: Dict[str, Dict] = {}
        free_models: List[Dict] = []
        paid_models: List[Dict] = []

        for m in models:
            mid = str(m.get('id', '')).strip()
            if not mid:
                continue

            if cls.is_combo(m, known_combo_ids, include_auto_combos=include_auto_combos):
                combos_dict[mid] = m
            elif cls.is_free_model(m, combo_member_ids, deep_scan_providers):
                m_copy = m.copy()
                prefix = mid.split('/', 1)[0].lower() if '/' in mid else ''
                is_exp = cls.is_explicit_free(m, combo_member_ids)
                m_copy['_is_explicit_free'] = is_exp
                m_copy['_priority_tier'] = 1 if (is_exp or prefix in cls.CORE_FREE_PROVIDER_PREFIXES) else 2
                free_models.append(m_copy)
            else:
                paid_models.append(m)

        if api_combos:
            for c in api_combos:
                cid = str(c.get('id', '')).strip()
                if cid and cid not in combos_dict:
                    combos_dict[cid] = c

        return {
            'combos': list(combos_dict.values()),
            'free_models': free_models,
            'paid_models': paid_models
        }

    @staticmethod
    def interleave_by_provider(models: List[Dict]) -> List[Dict]:
        tier1 = [m for m in models if m.get('_priority_tier', 1) == 1]
        tier2 = [m for m in models if m.get('_priority_tier', 1) != 1]

        def _round_robin(items: List[Dict]) -> List[Dict]:
            buckets = defaultdict(deque)
            for m in items:
                mid = str(m.get('id', ''))
                prefix = mid.split('/', 1)[0].lower() if '/' in mid else 'default'
                buckets[prefix].append(m)

            res = []
            keys = list(buckets.keys())
            while keys:
                next_keys = []
                for k in keys:
                    if buckets[k]:
                        res.append(buckets[k].popleft())
                    if buckets[k]:
                        next_keys.append(k)
                keys = next_keys
            return res

        if not tier2:
            return _round_robin(models)
        return _round_robin(tier1) + _round_robin(tier2)


# ==================== QUẢN LÝ & ĐỒNG BỘ ĐA TẦNG CẤU HÌNH OPENCODE (v1.6.0) ====================
class OpenCodeConfigManager:
    """
    Hệ thống Đồng bộ Đa tầng vào OpenCode (v1.6.0):
    1. Lexer JSONC an toàn tuyệt đối (không cắt nhầm '//' hoặc '/*' bên trong chuỗi JSON).
    2. Đồng bộ đồng thời vào CẢ 'opencode.json' VÀ 'opencode.jsonc' (cùng 'config.json' hoặc file override nếu có)
       để tránh hiện tượng 'opencode.json' ghi đè lên 'opencode.jsonc'.
    3. Tự động đăng ký thông tin xác thực API Key vào '~/.local/share/opencode/auth.json'
       giúp cả 9router và OmniRouter hiển thị ngay trong mục "Nhà cung cấp được kết nối" trên OpenCode Desktop.
    4. Tự động nhận diện các Provider ID sẵn có của 9router/OmniRouter (tránh tạo bản sao rời rạc),
       xóa bỏ 'whitelist'/'blacklist' chặn model mới và bổ sung đầy đủ trường chuẩn ('id', 'name', 'tool_call').
    """
    @classmethod
    def get_opencode_dir(cls) -> Path:
        xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
        base = Path(xdg) if xdg else (Path.home() / ".config")
        return base / "opencode"

    @classmethod
    def get_auth_files(cls) -> List[Path]:
        """Trả về danh sách các file auth.json của OpenCode (mặc định ~/.local/share/opencode/auth.json)."""
        paths: List[Path] = []
        xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
        data_base = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
        primary_auth = data_base / "opencode" / "auth.json"
        paths.append(primary_auth)

        cfg_auth = cls.get_opencode_dir() / "auth.json"
        if cfg_auth != primary_auth and cfg_auth.exists():
            paths.append(cfg_auth)
        return paths

    @classmethod
    def find_config_file(cls, custom_path: str = "") -> Path:
        if custom_path and Path(custom_path).expanduser().exists():
            return Path(custom_path).expanduser()
        dir_opencode = cls.get_opencode_dir()
        file_json = dir_opencode / "opencode.json"
        file_jsonc = dir_opencode / "opencode.jsonc"
        if file_json.exists():
            return file_json
        if file_jsonc.exists():
            return file_jsonc
        return file_json

    @classmethod
    def discover_target_config_files(cls, custom_path: str = "") -> List[Path]:
        """
        Tìm toàn bộ các file cấu hình OpenCode cần được đồng bộ để đảm bảo không có file nào
        ghi đè bằng dữ liệu cũ (bao gồm cả opencode.json và opencode.jsonc trong ~/.config/opencode/).
        """
        targets: List[Path] = []
        if custom_path and custom_path.strip():
            cp = Path(custom_path.strip()).expanduser()
            targets.append(cp)

        dir_opencode = cls.get_opencode_dir()
        file_jsonc = dir_opencode / "opencode.jsonc"
        file_json = dir_opencode / "opencode.json"
        file_cfg = dir_opencode / "config.json"

        # Luôn đồng bộ vào opencode.json (chuẩn mặc định của OpenCode Desktop GUI)
        # và opencode.jsonc (nếu đã tồn tại hoặc đang dùng)
        if file_jsonc.exists() and file_jsonc not in targets:
            targets.append(file_jsonc)
        if file_json not in targets:
            targets.append(file_json)
        if file_cfg.exists() and file_cfg not in targets:
            targets.append(file_cfg)

        # Kiểm tra các file cấu hình ở thư mục Home có thể ghi đè lên ~/.config/opencode/ (Issue #3407)
        for extra in (
            Path.home() / "opencode.json",
            Path.home() / "opencode.jsonc",
            Path.home() / ".opencode" / "opencode.json",
            Path.home() / ".opencode" / "opencode.jsonc",
        ):
            try:
                if extra.exists() and extra not in targets:
                    targets.append(extra)
            except Exception:
                pass

        return targets

    @classmethod
    def strip_jsonc_comments(cls, content: str) -> str:
        """
        Bộ phân tích từ vựng (State-Machine Lexer) tách bỏ comment // và /* */ chuẩn xác 100%,
        tuyệt đối không chạm vào '//' hay '/*' nằm bên trong chuỗi JSON.
        """
        out: List[str] = []
        i = 0
        n = len(content)
        in_str = False
        escape = False

        while i < n:
            ch = content[i]
            if in_str:
                out.append(ch)
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_str = False
                i += 1
            else:
                if ch == '"':
                    in_str = True
                    out.append(ch)
                    i += 1
                elif ch == '/' and i + 1 < n and content[i + 1] == '/':
                    # Bỏ qua comment dòng cho đến hết dòng
                    i += 2
                    while i < n and content[i] not in ('\n', '\r'):
                        i += 1
                elif ch == '/' and i + 1 < n and content[i + 1] == '*':
                    # Bỏ qua comment khối /* ... */
                    i += 2
                    while i + 1 < n and not (content[i] == '*' and content[i + 1] == '/'):
                        if content[i] in ('\n', '\r'):
                            out.append(content[i])
                        i += 1
                    i += 2
                else:
                    out.append(ch)
                    i += 1

        clean_text = ''.join(out)
        # Loại bỏ dấu phẩy thừa trước } hoặc ] (ngoài chuỗi)
        clean_text = re.sub(r',(\s*[}\]])', r'\1', clean_text)
        return clean_text

    @classmethod
    def _deep_merge_dicts(cls, base: Dict, override: Dict) -> Dict:
        res = json.loads(json.dumps(base))
        for k, v in override.items():
            if k in res and isinstance(res[k], dict) and isinstance(v, dict):
                res[k] = cls._deep_merge_dicts(res[k], v)
            else:
                res[k] = json.loads(json.dumps(v))
        return res

    @classmethod
    def load(cls, custom_path: str = "") -> Tuple[Dict, Path]:
        """
        Đọc và hợp nhất cấu hình từ các file cấu hình OpenCode hiện có (theo đúng thứ tự ưu tiên
        opencode.jsonc -> opencode.json) để bảo toàn 100% cài đặt của người dùng.
        """
        target_file = cls.find_config_file(custom_path)
        all_files = cls.discover_target_config_files(custom_path)
        existing_files = [f for f in all_files if f.exists()]

        if not existing_files:
            return {"$schema": "https://opencode.ai/config.json", "provider": {}}, target_file

        merged_data: Dict[str, Any] = {}
        for fpath in existing_files:
            try:
                raw = fpath.read_text(encoding='utf-8-sig')
                if not raw.strip():
                    continue
                clean = cls.strip_jsonc_comments(raw)
                data = json.loads(clean) if clean.strip() else {}
                if isinstance(data, dict):
                    merged_data = cls._deep_merge_dicts(merged_data, data)
            except Exception as e:
                print(f"Cảnh báo đọc file {fpath}: {e}")

        if not merged_data:
            merged_data = {"$schema": "https://opencode.ai/config.json", "provider": {}}
        merged_data.setdefault("$schema", "https://opencode.ai/config.json")
        if "provider" not in merged_data or not isinstance(merged_data["provider"], dict):
            merged_data["provider"] = {}

        return merged_data, target_file

    @classmethod
    def _find_matching_provider_keys(cls, provider_dict: Dict, r_name: str, endpoint: str) -> List[str]:
        """
        Tìm tất cả các key trong config['provider'] đang đại diện cho router này
        (ví dụ người dùng từng đặt key là '9router', '9router-local', hoặc trùng baseURL).
        """
        matched: List[str] = []
        clean_ep = ConfigManager.sanitize_endpoint(endpoint).lower()
        # Parse host:port properly for exact matching
        ep_host_port = re.sub(r'^https?://', '', clean_ep).split('/')[0]

        def extract_host_port(url: str) -> str:
            """Extract host:port from URL for exact comparison."""
            try:
                u = re.sub(r'^https?://', '', url).split('/')[0]
                return u
            except Exception:
                return ""

        for k, v in provider_dict.items():
            if not isinstance(v, dict):
                continue
            k_lower = k.lower()
            v_name = str(v.get("name", "")).lower()
            opts = v.get("options", {}) if isinstance(v.get("options"), dict) else {}
            v_url = ConfigManager.sanitize_endpoint(
                str(opts.get("baseURL") or v.get("api") or "")
            ).lower()
            v_host_port = extract_host_port(v_url)

            if k_lower == r_name.lower():
                matched.append(k)
            elif r_name.lower() in k_lower or r_name.lower() in v_name:
                matched.append(k)
            elif clean_ep and v_url and clean_ep == v_url:
                matched.append(k)
            elif r_name == "9router" and ("localhost:20128" in v_host_port or "127.0.0.1:20128" in v_host_port):
                matched.append(k)
            elif r_name == "omnirouter" and ep_host_port and ep_host_port == v_host_port:
                matched.append(k)

        if r_name not in matched:
            matched.append(r_name)
        return matched

    @classmethod
    def merge_routers(
        cls,
        current_config: Dict,
        router_updates: Dict,
        replace_router_models: bool = False
    ) -> Dict:
        """
        Gộp an toàn cấu hình của '9router' và 'omnirouter' vào opencode.json / opencode.jsonc:
        - Bảo toàn tuyệt đối 100% các provider khác, mcp, agent, plugin, keybinds...
        - Bổ sung đầy đủ schema model chuẩn OpenCode Desktop ('id', 'name', 'tool_call', 'temperature').
        - Khai báo cả 'api' và 'options.baseURL' + 'options.apiKey'.
        - Xóa bỏ 'whitelist'/'blacklist' cũ trên 9router/omnirouter để không chặn model mới.
        """
        new_config = json.loads(json.dumps(current_config))
        new_config.setdefault("$schema", "https://opencode.ai/config.json")
        if "provider" not in new_config or not isinstance(new_config["provider"], dict):
            new_config["provider"] = {}

        all_updated_keys: Set[str] = set()

        for r_name, r_data in router_updates.items():
            raw_models = r_data.get("models", {})
            if not raw_models:
                continue

            # Chuẩn hóa từng model entry với đầy đủ trường cho OpenCode CLI & Desktop
            normalized_models: Dict[str, Dict] = {}
            for mid, m_info in raw_models.items():
                if isinstance(m_info, dict):
                    m_entry = m_info.copy()
                else:
                    m_entry = {"name": str(m_info)}
                m_entry.setdefault("id", mid)
                m_entry.setdefault("name", mid)
                m_entry.setdefault("tool_call", True)
                m_entry.setdefault("temperature", True)
                normalized_models[mid] = m_entry

            endpoint = ConfigManager.sanitize_endpoint(r_data.get("endpoint", ""))
            api_key = str(r_data.get("api_key", "")).strip()
            display_name = r_data.get("name", r_name)

            target_keys = cls._find_matching_provider_keys(new_config["provider"], r_name, endpoint)

            for p_key in target_keys:
                all_updated_keys.add(p_key)
                if p_key in new_config["provider"] and isinstance(new_config["provider"][p_key], dict):
                    prov = new_config["provider"][p_key]
                    prov["npm"] = "@ai-sdk/openai-compatible"
                    prov["name"] = prov.get("name") or display_name
                    prov["api"] = endpoint
                    if "options" not in prov or not isinstance(prov["options"], dict):
                        prov["options"] = {}
                    prov["options"]["baseURL"] = endpoint
                    if api_key:
                        prov["options"]["apiKey"] = api_key

                    # Xóa whitelist / blacklist cũ nếu có để tránh ẩn mất các model mới
                    prov.pop("whitelist", None)
                    prov.pop("blacklist", None)

                    if replace_router_models or "models" not in prov or not isinstance(prov["models"], dict):
                        prov["models"] = json.loads(json.dumps(normalized_models))
                    else:
                        prov["models"].update(json.loads(json.dumps(normalized_models)))
                else:
                    opts = {"baseURL": endpoint}
                    if api_key:
                        opts["apiKey"] = api_key
                    new_config["provider"][p_key] = {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": display_name,
                        "api": endpoint,
                        "options": opts,
                        "models": json.loads(json.dumps(normalized_models))
                    }

        # Đảm bảo disabled_providers / enabled_providers ở cấp root không chặn 9router & omnirouter
        if isinstance(new_config.get("disabled_providers"), list):
            new_config["disabled_providers"] = [
                p for p in new_config["disabled_providers"] if p not in all_updated_keys
            ]
        if isinstance(new_config.get("enabled_providers"), list) and new_config["enabled_providers"]:
            for pk in all_updated_keys:
                if pk not in new_config["enabled_providers"]:
                    new_config["enabled_providers"].append(pk)

        return new_config

    @classmethod
    def sync_auth_json(cls, router_updates: Dict, provider_dict: Optional[Dict] = None) -> List[Path]:
        """
        Đồng bộ thông tin xác thực API Key của 9router & omnirouter vào ~/.local/share/opencode/auth.json
        để OpenCode Desktop v1.19.3 hiển thị cả 2 router trong mục "Nhà cung cấp được kết nối".
        """
        synced_auth_paths: List[Path] = []
        for auth_file in cls.get_auth_files():
            try:
                auth_data: Dict[str, Any] = {}
                if auth_file.exists():
                    try:
                        raw = auth_file.read_text(encoding='utf-8-sig')
                        if raw.strip():
                            loaded = json.loads(cls.strip_jsonc_comments(raw))
                            if isinstance(loaded, dict):
                                auth_data = loaded
                        # Tạo bản sao lưu auth.json
                        ts = time.strftime('%Y%m%d_%H%M%S')
                        bak = auth_file.parent / f"{auth_file.name}.bak_{ts}"
                        bak.write_text(raw, encoding='utf-8')
                    except Exception:
                        pass

                for r_name, r_data in router_updates.items():
                    models = r_data.get("models", {})
                    api_key = str(r_data.get("api_key", "")).strip()
                    endpoint = r_data.get("endpoint", "")
                    if not models or not api_key:
                        continue

                    keys_to_auth = [r_name]
                    if provider_dict:
                        keys_to_auth = cls._find_matching_provider_keys(provider_dict, r_name, endpoint)

                    for pk in keys_to_auth:
                        auth_data[pk] = {
                            "type": "api",
                            "key": api_key
                        }

                auth_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_auth = auth_file.parent / f"{auth_file.name}.tmp"
                with open(tmp_auth, 'w', encoding='utf-8') as f:
                    json.dump(auth_data, f, indent=2, ensure_ascii=False)
                    f.write('\n')
                os.replace(tmp_auth, auth_file)
                synced_auth_paths.append(auth_file)
            except Exception as e:
                print(f"Cảnh báo đồng bộ auth.json ({auth_file}): {e}")
        return synced_auth_paths

    @classmethod
    def save_safely(cls, config: Dict, target_file: Path) -> Tuple[bool, str]:
        """Ghi nguyên tử 1 file cấu hình kèm bản sao lưu tự động."""
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if target_file.exists():
                ts = time.strftime('%Y%m%d_%H%M%S')
                backup_path = target_file.parent / f"{target_file.name}.bak_{ts}"
                backup_path.write_text(target_file.read_text(encoding='utf-8'), encoding='utf-8')

            tmp_path = target_file.parent / f"{target_file.name}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.write('\n')

            with open(tmp_path, 'r', encoding='utf-8') as f:
                json.load(f)

            os.replace(tmp_path, target_file)
            return True, f"Đã lưu thành công vào {target_file}"
        except Exception as e:
            return False, f"Lỗi khi lưu OpenCode config ({target_file}): {e}"

    @classmethod
    def sync_all_opencode(
        cls,
        router_updates: Dict,
        custom_path: str = "",
        replace_router_models: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Thực hiện đồng bộ trọn gói Đa tầng:
        1. Đọc & hợp nhất cấu hình từ mọi file hiện có.
        2. Merge 9router & omnirouter (kèm chuẩn hóa schema model).
        3. Ghi nguyên tử vào CẢ opencode.json VÀ opencode.jsonc (cùng các file liên quan).
        4. Đồng bộ thông tin xác thực vào ~/.local/share/opencode/auth.json.
        """
        current_cfg, primary_file = cls.load(custom_path)
        new_cfg = cls.merge_routers(current_cfg, router_updates, replace_router_models=replace_router_models)

        target_files = cls.discover_target_config_files(custom_path)
        saved_files: List[Path] = []
        errors: List[str] = []

        for tf in target_files:
            ok, msg = cls.save_safely(new_cfg, tf)
            if ok:
                saved_files.append(tf)
            else:
                errors.append(msg)

        auth_files = cls.sync_auth_json(router_updates, provider_dict=new_cfg.get("provider", {}))

        total_9r = len(new_cfg.get("provider", {}).get("9router", {}).get("models", {}))
        total_om = len(new_cfg.get("provider", {}).get("omnirouter", {}).get("models", {}))

        report = {
            "primary_file": primary_file,
            "saved_config_files": saved_files,
            "saved_auth_files": auth_files,
            "errors": errors,
            "total_9router_models": total_9r,
            "total_omnirouter_models": total_om,
            "provider_keys": list(new_cfg.get("provider", {}).keys())
        }
        return (len(saved_files) > 0), report


# ==================== ĐA LUỒNG SONG SONG 2 PHA SIÊU TỐC ====================
class FastScanWorker(threading.Thread):
    MAX_WORKERS = 32

    def __init__(self, app, config: Dict, deep_scan: bool = True):
        super().__init__(daemon=True)
        self.app = app
        self.config = config
        self.deep_scan = deep_scan
        self.include_auto_combos = bool(config.get("include_auto_combos", False))
        self.cancelled = False
        self.executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()

        self._cb_success: Dict[Tuple[str, str], int] = defaultdict(int)
        self._cb_consec_fail: Dict[Tuple[str, str], int] = defaultdict(int)
        self._cb_no_account: Dict[Tuple[str, str], int] = defaultdict(int)
        self._cb_tripped: Set[Tuple[str, str]] = set()

    def cancel(self):
        self.cancelled = True
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    def run(self):
        try:
            self.execute()
        except Exception as e:
            self.app.post_log(f"✗ Lỗi ngoài ý muốn: {e}")
        finally:
            self.app.after(0, self.on_complete)

    def _discover_single_router(self, r_name: str) -> Tuple[str, Optional[APIClient], List[Dict], List[Dict]]:
        r_cfg = self.config.get(r_name, {})
        endpoint = r_cfg.get("endpoint", "")
        api_key = r_cfg.get("api_key", "")

        self.app.post_log(f"▸ [{r_name.upper()}] Đang kết nối tới {endpoint}...")
        client = APIClient(endpoint, api_key)

        ok, raw_models, msg = client.fetch_models_and_verify()
        if not ok:
            self.app.post_log(f"✗ [{r_name.upper()}] Kết nối thất bại: {msg}")
            return r_name, None, [], []

        api_combos, combo_member_ids = client.fetch_combos_endpoint()

        categorized = ModelAnalyzer.categorize_models(
            raw_models,
            api_combos=api_combos,
            combo_member_ids=combo_member_ids,
            deep_scan_providers=self.deep_scan,
            include_auto_combos=self.include_auto_combos
        )
        combos = categorized['combos']
        free_models = categorized['free_models']
        paid_count = len(categorized['paid_models'])

        self.app.all_models[r_name] = raw_models
        self.app.detected_combos[r_name] = combos

        self.app.post_log(
            f"✓ [{r_name.upper()}] Tải thành công {len(raw_models)} mục: "
            f"{len(combos)} Combos | {len(free_models)} Free Candidates | {paid_count} Paid"
        )

        self.app.after(0, lambda r=r_name, c=combos: self.app.render_combos_list(r, c))
        return r_name, client, combos, free_models

    def _should_skip_by_circuit_breaker(self, r_name: str, model: Dict) -> bool:
        if r_name == "9router" or model.get('_priority_tier', 1) == 1 or model.get('_is_explicit_free'):
            return False

        mid = str(model.get('id', ''))
        prefix = mid.split('/', 1)[0].lower() if '/' in mid else 'default'
        key = (r_name, prefix)
        with self._lock:
            return key in self._cb_tripped

    def _record_ping_outcome(self, r_name: str, model: Dict, passed: bool, status_txt: str):
        mid = str(model.get('id', ''))
        prefix = mid.split('/', 1)[0].lower() if '/' in mid else 'default'
        key = (r_name, prefix)
        with self._lock:
            if passed:
                self._cb_success[key] += 1
                self._cb_consec_fail[key] = 0
                self._cb_tripped.discard(key)
            else:
                self._cb_consec_fail[key] += 1
                if "NO_ACCOUNT" in status_txt or "503" in status_txt or "401" in status_txt or "403" in status_txt:
                    self._cb_no_account[key] += 1

                if self._cb_success[key] == 0:
                    if self._cb_no_account[key] >= 2 or self._cb_consec_fail[key] >= 4:
                        if key not in self._cb_tripped and r_name != "9router" and prefix not in ModelAnalyzer.CORE_FREE_PROVIDER_PREFIXES:
                            self._cb_tripped.add(key)
                            self.app.post_log(
                                f"   ⚡ [NGẮT NHANH] [{r_name.upper()}] Bỏ qua các model catalog còn lại của '{prefix}/' (Provider không có account)"
                            )

    def _ping_task_wrapper(self, r_name: str, client: APIClient, model: Dict) -> Tuple[str, Dict, bool, int, str, bool]:
        if self.cancelled:
            return r_name, model, False, 0, "Đã hủy", True

        if self._should_skip_by_circuit_breaker(r_name, model):
            return r_name, model, False, 0, "Bỏ qua nhanh (Provider 503/No Account)", True

        mid = str(model.get('id', ''))
        passed, latency_ms, status_txt = client.test_model_ping(mid, timeout=10.0)
        self._record_ping_outcome(r_name, model, passed, status_txt)
        return r_name, model, passed, latency_ms, status_txt, False

    def execute(self):
        self.app.post_log(f"━━━ BẮT ĐẦU QUÉT ĐỒNG THỜI TRÊN CẢ 9ROUTER & OMNIROUTER (v{APP_VERSION}) ━━━")
        self.app.post_status("Pha 1/2: Đang quét danh sách Combos & Models từ 9router và OmniRouter...", "blue")
        self.app.post_progress(0.05)

        routers = ["9router", "omnirouter"]
        router_clients: Dict[str, APIClient] = {}
        router_free_candidates: Dict[str, List[Dict]] = {}

        with ThreadPoolExecutor(max_workers=2) as discovery_pool:
            futures = [discovery_pool.submit(self._discover_single_router, r) for r in routers]
            for fut in as_completed(futures):
                if self.cancelled:
                    break
                r_name, client, combos, free_models = fut.result()
                if client is not None:
                    router_clients[r_name] = client
                    router_free_candidates[r_name] = ModelAnalyzer.interleave_by_provider(free_models)

        self.app.mark_all_models_dirty()
        self.app.post_progress(0.15)

        if self.cancelled:
            self.app.post_log("⏹ Đã dừng tiến trình theo yêu cầu.")
            return

        total_combos_found = sum(len(self.app.detected_combos.get(r, [])) for r in routers)
        self.app.post_log(
            f"\n▸ KẾT QUẢ PHA 1 (COMBOS): Đã hiển thị tức thì {total_combos_found} Combos "
            f"(9router: {len(self.app.detected_combos.get('9router', []))} | "
            f"OmniRouter: {len(self.app.detected_combos.get('omnirouter', []))})"
        )

        tier1_tasks: List[Tuple[str, APIClient, Dict]] = []
        tier2_tasks: List[Tuple[str, APIClient, Dict]] = []

        max_len = max((len(v) for v in router_free_candidates.values()), default=0)
        for i in range(max_len):
            for r_name in routers:
                cands = router_free_candidates.get(r_name, [])
                if i < len(cands):
                    m = cands[i]
                    if m.get('_priority_tier', 1) == 1 or r_name == "9router":
                        tier1_tasks.append((r_name, router_clients[r_name], m))
                    else:
                        tier2_tasks.append((r_name, router_clients[r_name], m))

        test_tasks = tier1_tasks + tier2_tasks
        total_to_test = len(test_tasks)
        if total_to_test == 0:
            self.app.post_progress(1.0)
            self.app.post_log("ℹ Không có mô hình miễn phí nào cần kiểm tra thêm.")
            self.app.post_status(f"Hoàn tất! Tìm thấy {total_combos_found} Combos.", "green")
            return

        self.app.post_log(
            f"\n▸ PHA 2: Kiểm tra tốc độ cao {total_to_test} ứng viên "
            f"({len(tier1_tasks)} ưu tiên cao + {len(tier2_tasks)} mở rộng | {self.MAX_WORKERS} luồng song song + Cầu chì chống nghẽn)..."
        )

        tested_count = 0
        skipped_count = 0
        pass_counts = {"9router": 0, "omnirouter": 0}

        self.executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)
        future_list = [
            self.executor.submit(self._ping_task_wrapper, r_name, client, m)
            for (r_name, client, m) in test_tasks
        ]

        try:
            for future in as_completed(future_list):
                if self.cancelled:
                    self.app.post_log("⏹ Đã dừng kiểm tra theo yêu cầu.")
                    break

                try:
                    r_name, m, passed, latency_ms, status_txt, was_skipped = future.result(timeout=12)
                except Exception:
                    continue

                mid = m.get('id', '')
                tested_count += 1
                if was_skipped:
                    skipped_count += 1

                p_val = 0.15 + (tested_count / total_to_test) * 0.85
                self.app.post_progress(p_val)

                if passed:
                    pass_counts[r_name] += 1
                    m_copy = m.copy()
                    m_copy["latency_ms"] = latency_ms
                    m_copy["status_txt"] = status_txt
                    self.app.working_free_models[r_name].append(m_copy)
                    self.app.post_log(f"   ✓ [HOẠT ĐỘNG] [{r_name.upper()}] {mid} ({latency_ms}ms)")
                    self.app.queue_working_free_row(r_name, m_copy)
                elif not was_skipped:
                    self.app.post_log(f"   ✗ [FAIL] [{r_name.upper()}] {mid} ({status_txt})")

                total_pass = sum(pass_counts.values())
                self.app.post_status(
                    f"Pha 2/2: Đã xử lý {tested_count}/{total_to_test} models "
                    f"(Hoạt động: {total_pass} | Combos: {total_combos_found}) — [{r_name}] {mid[:40]}",
                    "blue"
                )
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)

        self.app.post_progress(1.0)
        total_working = sum(pass_counts.values())
        self.app.post_log(
            f"\n━━━ HOÀN TẤT TOÀN BỘ TIẾN TRÌNH! ━━━\n"
            f"   • Tổng Combos: {total_combos_found} (9router: {len(self.app.detected_combos.get('9router', []))} | "
            f"OmniRouter: {len(self.app.detected_combos.get('omnirouter', []))})\n"
            f"   • Tổng Free Models hoạt động: {total_working} (9router: {pass_counts['9router']} | "
            f"OmniRouter: {pass_counts['omnirouter']})\n"
            f"   • Đã bỏ qua nhanh (Circuit Breaker): {skipped_count} model từ các provider không có account"
        )
        self.app.post_status(
            f"Hoàn tất! {total_combos_found} Combos & {total_working} Free Models đang hoạt động.",
            "green"
        )

    def on_complete(self):
        self.app.flush_ui_queues()
        self.app.is_running = False
        self.app.btn_scan.configure(text="Quét & Kiểm tra", state="normal")
        self.app.btn_update.configure(state="normal")
        self.app.update_summary_counts()
        if self.app.tabview.get() == "Toàn bộ Models & Router":
            self.app.refresh_all_models_view()


# ==================== HỆ THỐNG HỘP THOẠI PHẲNG HIỆN ĐẠI (THAY THẾ TKINTER.MESSAGEBOX) ====================
class ModernAlertDialog(ctk.CTkToplevel):
    """Hộp thoại thông báo / cảnh báo phẳng hiện đại, đồng bộ hoàn toàn với giao diện chính."""
    def __init__(self, parent, title: str, message: str, alert_type: str = "info"):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry("540x290")
        self.minsize(480, 250)
        self.resizable(True, True)
        self.transient(parent)

        self._build_ui(title, message, alert_type)
        self._center_on_parent()
        self.after(50, self._safe_focus)

    def _safe_focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _center_on_parent(self):
        self.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")

    def _build_ui(self, title: str, message: str, alert_type: str):
        accent_map = {
            "info": ("#0284c7", "✓ THÔNG BÁO"),
            "warning": ("#d97706", "⚠ CẢNH BÁO"),
            "error": ("#dc2626", "✗ LỖI HỆ THỐNG")
        }
        accent_color, badge_txt = accent_map.get(alert_type, accent_map["info"])

        header = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=56, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text=badge_txt, fg_color=accent_color, text_color="white",
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=3
        ).pack(side="left", padx=(18, 10), pady=14)

        ctk.CTkLabel(
            header, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True, pady=14)

        bottom = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=58, corner_radius=0)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        ctk.CTkButton(
            bottom, text="Đóng (OK)", width=130, height=36,
            fg_color=accent_color, font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy
        ).pack(side="right", padx=18, pady=11)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        msg_box = ctk.CTkTextbox(
            body, font=ctk.CTkFont(size=13),
            fg_color=("gray95", "#202023"), text_color=("black", "#f4f4f5"),
            corner_radius=8, wrap="word"
        )
        msg_box.pack(fill="both", expand=True)
        msg_box.insert("1.0", message)
        msg_box.configure(state="disabled")


class ConfirmUpdateDialog(ctk.CTkToplevel):
    """
    Hộp thoại Xác nhận & Xem trước danh sách mô hình sẽ thêm vào OpenCode (Thay thế messagebox.askyesno).
    Thiết kế phẳng, hiện đại, có thẻ thống kê từng Router, danh sách xem trước và tùy chọn làm sạch model cũ.
    """
    def __init__(
        self,
        parent,
        is_default_all: bool,
        stats: Dict[str, Dict[str, int]],
        router_updates: Dict[str, Dict],
        target_files: List[Path],
        auth_files: List[Path],
        default_replace: bool,
        on_confirm_callback: Callable[[bool], None]
    ):
        super().__init__(parent)
        self.parent = parent
        self.on_confirm_callback = on_confirm_callback
        self.replace_var = ctk.BooleanVar(value=default_replace)

        self.title("Xác nhận Đồng bộ Combos & Free Models vào OpenCode")
        self.geometry("720x580")
        self.minsize(640, 500)
        self.resizable(True, True)
        self.transient(parent)

        self._build_ui(is_default_all, stats, router_updates, target_files, auth_files)
        self._center_on_parent()
        self.after(50, self._safe_focus)

    def _safe_focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _center_on_parent(self):
        self.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")

    def _build_ui(
        self,
        is_default_all: bool,
        stats: Dict[str, Dict[str, int]],
        router_updates: Dict[str, Dict],
        target_files: List[Path],
        auth_files: List[Path]
    ):
        # 1. HEADER
        header = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=64, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        badge_mode = "MẶC ĐỊNH: TẤT CẢ" if is_default_all else "THEO MỤC ĐÃ CHỌN"
        badge_col = "#16a34a" if is_default_all else "#0284c7"

        ctk.CTkLabel(
            header, text=badge_mode, fg_color=badge_col, text_color="white",
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=4
        ).pack(side="left", padx=(20, 12), pady=16)

        ctk.CTkLabel(
            header, text="Xác nhận Cập nhật Cấu hình vào OpenCode",
            font=ctk.CTkFont(size=17, weight="bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True, pady=16)

        # 2. BOTTOM ACTION BAR
        bottom = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=64, corner_radius=0)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        ctk.CTkButton(
            bottom, text="Hủy bỏ", width=120, height=40,
            fg_color=("gray80", "#3f3f46"), hover_color=("gray70", "#52525b"),
            text_color=("black", "white"), font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy
        ).pack(side="right", padx=(8, 20), pady=12)

        ctk.CTkButton(
            bottom, text="✓ Xác nhận & Cập nhật ngay", width=230, height=40,
            fg_color=("#2e7d32", "#16a34a"), hover_color=("#1b5e20", "#15803d"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._confirm
        ).pack(side="right", padx=8, pady=12)

        # 3. MAIN CONTENT
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=14)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(2, weight=1)

        # 2 Thẻ thống kê Router song song
        c9 = stats["9router"]["combo"]
        f9 = stats["9router"]["free"]
        co = stats["omnirouter"]["combo"]
        fo = stats["omnirouter"]["free"]
        total_all = c9 + f9 + co + fo

        card_9r = ctk.CTkFrame(content, fg_color=("gray92", "#222226"), corner_radius=10, border_width=1, border_color=("#0284c7", "#0284c7"))
        card_9r.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 10))
        ctk.CTkLabel(
            card_9r, text="9ROUTER (LOCAL)", fg_color="#0284c7", text_color="white",
            corner_radius=5, font=ctk.CTkFont(size=10, weight="bold"), padx=8, pady=2
        ).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            card_9r, text=f"{c9} Combos  +  {f9} Free Models  =  {c9 + f9} mục",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(
            card_9r, text=f"Endpoint: {router_updates['9router']['endpoint']}",
            font=ctk.CTkFont(family="monospace", size=11), text_color=("gray45", "gray60"), anchor="w"
        ).pack(anchor="w", padx=14, pady=(0, 10))

        card_om = ctk.CTkFrame(content, fg_color=("gray92", "#222226"), corner_radius=10, border_width=1, border_color=("#9333ea", "#9333ea"))
        card_om.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 10))
        ctk.CTkLabel(
            card_om, text="OMNIROUTER (NAS)", fg_color="#9333ea", text_color="white",
            corner_radius=5, font=ctk.CTkFont(size=10, weight="bold"), padx=8, pady=2
        ).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            card_om, text=f"{co} Combos  +  {fo} Free Models  =  {co + fo} mục",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(
            card_om, text=f"Endpoint: {router_updates['omnirouter']['endpoint']}",
            font=ctk.CTkFont(family="monospace", size=11), text_color=("gray45", "gray60"), anchor="w"
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # Khung tùy chọn Làm sạch model cũ
        opt_box = ctk.CTkFrame(content, fg_color=("gray92", "#202024"), corner_radius=8)
        opt_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ctk.CTkCheckBox(
            opt_box,
            text="Làm mới danh sách model của 9router & OmniRouter (xóa model cũ không còn sống của 2 router này; giữ nguyên 100% các provider khác)",
            variable=self.replace_var,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=12, pady=10)

        # Khung Xem trước danh sách mô hình & các file sẽ đồng bộ
        preview_box = ctk.CTkTextbox(
            content, font=ctk.CTkFont(family="monospace", size=11),
            fg_color=("gray95", "#141417"), text_color=("black", "#e4e4e7"),
            corner_radius=8
        )
        preview_box.grid(row=2, column=0, columnspan=2, sticky="nsew")

        lines = [
            f"━━━ TỔNG CỘNG ĐỒNG BỘ: {total_all} MỤC ({c9 + co} Combos & {f9 + fo} Free Models đang hoạt động) ━━━",
            "",
            "1. CÁC FILE CẤU HÌNH & XÁC THỰC SẼ ĐƯỢC ĐỒNG BỘ ĐA TẦNG (KÈM SAO LƯU .bak):"
        ]
        for tf in target_files:
            lines.append(f"   • [Config] {tf}")
        for af in auth_files:
            lines.append(f"   • [Auth]   {af}  (Kích hoạt trạng thái 'Đã kết nối' trên OpenCode Desktop)")

        for r_key in ("9router", "omnirouter"):
            m_dict = router_updates.get(r_key, {}).get("models", {})
            lines.append(f"\n2. DANH SÁCH MÔ HÌNH ĐỒNG BỘ CHO [{r_key.upper()}] ({len(m_dict)} mục):")
            for idx, mid in enumerate(m_dict.keys(), 1):
                lines.append(f"   {idx:03d}. {mid}")

        preview_box.insert("1.0", "\n".join(lines))
        preview_box.configure(state="disabled")

    def _confirm(self):
        replace_flag = self.replace_var.get()
        self.destroy()
        self.on_confirm_callback(replace_flag)


class UpdateSuccessDialog(ctk.CTkToplevel):
    """
    Hộp thoại Báo cáo Kết quả Đồng bộ OpenCode (Thay thế messagebox.showinfo bị hẹp chữ).
    Hiển thị chi tiết các file đã ghi, số lượng model và nút hỗ trợ làm mới tiến trình nền OpenCode.
    """
    def __init__(self, parent, report: Dict[str, Any], stats: Dict[str, Dict[str, int]]):
        super().__init__(parent)
        self.parent = parent
        self.report = report
        self.title("Đồng bộ Cấu hình OpenCode Thành công")
        self.geometry("680x500")
        self.minsize(600, 440)
        self.resizable(True, True)
        self.transient(parent)

        self._build_ui(report, stats)
        self._center_on_parent()
        self.after(50, self._safe_focus)

    def _safe_focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _center_on_parent(self):
        self.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")

    def _build_ui(self, report: Dict[str, Any], stats: Dict[str, Dict[str, int]]):
        header = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=62, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="✓ THÀNH CÔNG", fg_color="#16a34a", text_color="white",
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=4
        ).pack(side="left", padx=(20, 12), pady=16)

        ctk.CTkLabel(
            header, text="Đã Đồng bộ Đa tầng vào OpenCode An toàn!",
            font=ctk.CTkFont(size=17, weight="bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True, pady=16)

        bottom = ctk.CTkFrame(self, fg_color=("gray90", "#18181b"), height=64, corner_radius=0)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        ctk.CTkButton(
            bottom, text="Hoàn tất (OK)", width=150, height=40,
            fg_color=("#2e7d32", "#16a34a"), hover_color=("#1b5e20", "#15803d"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy
        ).pack(side="right", padx=20, pady=12)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        detail_box = ctk.CTkTextbox(
            body, font=ctk.CTkFont(family="monospace", size=12),
            fg_color=("gray95", "#141417"), text_color=("black", "#e4e4e7"),
            corner_radius=8, wrap="word"
        )
        detail_box.pack(fill="both", expand=True)

        c9, f9 = stats["9router"]["combo"], stats["9router"]["free"]
        co, fo = stats["omnirouter"]["combo"], stats["omnirouter"]["free"]

        lines = [
            "━━━ KẾT QUẢ ĐỒNG BỘ CẤU HÌNH & XÁC THỰC OPENCODE ━━━",
            "",
            f"• 9router (Local):   {c9} Combos + {f9} Free Models (Tổng có trong file: {report.get('total_9router_models', 0)} mục)",
            f"• OmniRouter (NAS):  {co} Combos + {fo} Free Models (Tổng có trong file: {report.get('total_omnirouter_models', 0)} mục)",
            f"• Các nhà cung cấp trong OpenCode: {', '.join(report.get('provider_keys', []))}",
            "",
            "1. ĐÃ GHI ĐỒNG BỘ CÁC FILE CẤU HÌNH (Tránh xung đột ghi đè opencode.json / opencode.jsonc):"
        ]
        for cf in report.get("saved_config_files", []):
            lines.append(f"   ✓ {cf}")

        lines.append("\n2. ĐÃ ĐĂNG KÝ XÁC THỰC KẾT NỐI ROUTER (auth.json):")
        for af in report.get("saved_auth_files", []):
            lines.append(f"   ✓ {af}")

        lines.extend([
            "",
            "3. HƯỚNG DẪN ĐỂ OPENCODE DESKTOP NHẬN NGAY 100% MÔ HÌNH MỚI:",
            "   • Bước 1: Thoát hẳn ứng dụng OpenCode Desktop (kiểm tra cả khay hệ thống / System Tray góc màn hình) rồi mở lại.",
            "   • Bước 2: Vào mục 'Nhà cung cấp' (Providers) -> Bạn sẽ thấy cả '9router (Local)' và 'OmniRouter (NAS)' đều nằm trong mục 'Nhà cung cấp được kết nối'.",
            "   • Bước 3: Vào mục 'Mô hình' (Models) ở thanh bên trái để bật hiển thị hoặc gõ '/models' trong khung chat để chọn ngay các Combos & Free Models mới!"
        ])

        detail_box.insert("1.0", "\n".join(lines))
        detail_box.configure(state="disabled")


# ==================== GIAO DIỆN CHÍNH (ZERO-LAG X11 & FULLY RESPONSIVE) ====================
class AutoUpdateFreeApp(ctk.CTk):
    def __init__(self):
        super().__init__(className="Auto-Update-Free")

        self.title(f"{APP_NAME} v{APP_VERSION} — Đồng bộ Combos & Mô hình AI Miễn phí")
        self.geometry("1280x840")
        self.minsize(1060, 680)

        self._set_app_icon()

        self.config = ConfigManager.load()
        self.all_models: Dict[str, List[Dict]] = {"9router": [], "omnirouter": []}
        self.detected_combos: Dict[str, List[Dict]] = {"9router": [], "omnirouter": []}
        self.working_free_models: Dict[str, List[Dict]] = {"9router": [], "omnirouter": []}
        self.item_selections: Dict[str, Dict] = {}

        self.current_worker: Optional[FastScanWorker] = None
        self.is_running = False
        self._all_models_dirty = False

        self._ui_lock = threading.Lock()
        self._pending_logs: List[str] = []
        self._pending_free_rows: List[Tuple[str, Dict]] = []
        self._pending_status: Optional[Tuple[str, str]] = None
        self._pending_progress: Optional[float] = None

        self.combo_router_filter = "ALL"
        self.free_router_filter = "ALL"

        self.all_models_page = 1
        self.PAGE_SIZE = 60
        self.filtered_all_cache: List[Tuple[str, Dict, bool, bool]] = []

        self._build_responsive_ui()
        self._center_window()
        self._start_ui_flush_timer()

    def show_modern_alert(self, title: str, message: str, alert_type: str = "info"):
        ModernAlertDialog(self, title=title, message=message, alert_type=alert_type)

    def _get_row_colors(self) -> Dict[str, str]:
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        if is_dark:
            return {
                "row_bg": "#27272a",
                "row_border": "#3f3f46",
                "text_fg": "#f4f4f5",
                "sub_fg": "#a1a1aa",
                "select_bg": "#18181b",
                "latency_fg": "#4ade80",
                "9router_badge": "#0284c7",
                "omni_badge": "#9333ea"
            }
        return {
            "row_bg": "#e4e4e7",
            "row_border": "#d4d4d8",
            "text_fg": "#18181b",
            "sub_fg": "#52525b",
            "select_bg": "#ffffff",
            "latency_fg": "#15803d",
            "9router_badge": "#1976d2",
            "omni_badge": "#7b1fa2"
        }

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _set_app_icon(self):
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                self._app_icon_photo = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._app_icon_photo)
            except Exception:
                try:
                    self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
                except Exception:
                    pass

    def bring_to_front(self):
        self.deiconify()
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()

    def _build_responsive_ui(self):
        # 1. HEADER BAR (Gọn gàng, không bao giờ bị cắt chữ ngay cả khi HiDPI 150%)
        self.header_frame = ctk.CTkFrame(self, fg_color=("gray95", "#18181b"), height=64, corner_radius=0)
        self.header_frame.pack(fill="x", side="top")
        self.header_frame.pack_propagate(False)

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            title_box, text=f"{APP_NAME}",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")

        ver_badge = ctk.CTkLabel(
            title_box, text=f"v{APP_VERSION}",
            fg_color=("#1976d2", "#0284c7"), text_color="white",
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), padx=8, pady=2
        )
        ver_badge.pack(side="left", padx=(10, 12))

        ctk.CTkLabel(
            title_box, text="9router + OmniRouter ➔ OpenCode",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray45", "gray60")
        ).pack(side="left")

        header_actions = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_actions.pack(side="right", padx=20, pady=12)

        self.btn_settings = ctk.CTkButton(
            header_actions, text="⚙ Cài đặt Router & OpenCode",
            command=self.open_settings_dialog,
            width=210, height=36,
            fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"),
            text_color=("black", "white"), font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_settings.pack(side="left", padx=6)

        self.btn_theme = ctk.CTkButton(
            header_actions, text="Giao diện",
            command=self.toggle_theme,
            width=82, height=36,
            fg_color=("gray85", "#27272a"), hover_color=("gray75", "#3f3f46"),
            text_color=("black", "white"), font=ctk.CTkFont(size=12)
        )
        self.btn_theme.pack(side="left", padx=2)

        # 2. CONTROL & ACTION BAR (Bố cục thông thoáng, tách bạch nút điều khiển và nhãn tổng kết)
        self.control_frame = ctk.CTkFrame(self, fg_color=("gray90", "#202023"), corner_radius=12)
        self.control_frame.pack(fill="x", padx=20, pady=(10, 8))
        self.control_frame.grid_columnconfigure(1, weight=1)

        ctrl_left = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        ctrl_left.grid(row=0, column=0, padx=(14, 8), pady=(10, 6), sticky="w")

        self.btn_scan = ctk.CTkButton(
            ctrl_left, text="Quét & Kiểm tra",
            command=self.toggle_scan,
            width=155, height=40,
            fg_color=("#1976d2", "#2563eb"), hover_color=("#1565c0", "#1d4ed8"),
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_scan.pack(side="left", padx=(0, 8))

        self.btn_update = ctk.CTkButton(
            ctrl_left, text="Cập nhật vào OpenCode",
            command=self.update_opencode_action,
            width=210, height=40,
            fg_color=("#2e7d32", "#16a34a"), hover_color=("#1b5e20", "#15803d"),
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_update.pack(side="left", padx=(0, 12))

        self.deep_scan_var = ctk.BooleanVar(value=self.config.get("deep_scan_providers", True))
        self.chk_deep_scan = ctk.CTkCheckBox(
            ctrl_left,
            text="Quét sâu Provider (ag, oc, kc, gemini, ollama...)",
            variable=self.deep_scan_var,
            font=ctk.CTkFont(size=12)
        )
        self.chk_deep_scan.pack(side="left", padx=4)

        self.summary_label = ctk.CTkLabel(
            self.control_frame,
            text="Chưa quét dữ liệu. Nhấn 'Quét & Kiểm tra' để bắt đầu.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray30", "#38bdf8"),
            anchor="e"
        )
        self.summary_label.grid(row=0, column=1, padx=(8, 16), pady=(10, 6), sticky="ew")

        # 3. PROGRESS BAR & STATUS
        self.progress_container = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_container.pack(fill="x", padx=20, pady=(0, 6))

        progress_info = ctk.CTkFrame(self.progress_container, fg_color="transparent")
        progress_info.pack(fill="x", pady=(0, 3))

        self.status_label = ctk.CTkLabel(
            progress_info, text="● Sẵn sàng",
            font=ctk.CTkFont(size=12), text_color=("gray50", "gray40"),
            anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress_percent_label = ctk.CTkLabel(
            progress_info, text="0%",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray50", "gray40")
        )
        self.progress_percent_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self.progress_container, height=6, corner_radius=3)
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0.0)

        # 4. CONTENT TABS (CO GIÃN 100% + LAZY RENDER TAB 2)
        self.tabview = ctk.CTkTabview(self, corner_radius=12, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        self.tab_target = self.tabview.add("Sẵn sàng thêm vào OpenCode")
        self.tab_all = self.tabview.add("Toàn bộ Models & Router")
        self.tab_logs = self.tabview.add("Nhật ký tiến trình")

        self._build_tab_target()
        self._build_tab_all()
        self._build_tab_logs()

    def _on_tab_changed(self):
        if self.tabview.get() == "Toàn bộ Models & Router" and self._all_models_dirty:
            self.refresh_all_models_view()

    def mark_all_models_dirty(self):
        self._all_models_dirty = True
        if self.tabview.get() == "Toàn bộ Models & Router":
            self.after(0, self.refresh_all_models_view)

    # ---------- TAB 1: SẴN SÀNG CẬP NHẬT (COMBOS & FREE MODELS) ----------
    def _build_tab_target(self):
        tab = self.tab_target
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # === CỘT TRÁI: DANH SÁCH COMBOS ===
        combo_card = ctk.CTkFrame(tab, fg_color=("gray95", "#18181b"), corner_radius=10)
        combo_card.grid(row=0, column=0, sticky="nsew", padx=(4, 5), pady=4)
        combo_card.grid_columnconfigure(0, weight=1)
        combo_card.grid_rowconfigure(2, weight=1)

        combo_header = ctk.CTkFrame(combo_card, fg_color="transparent")
        combo_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))

        self.combo_title = ctk.CTkLabel(
            combo_header, text="Danh sách Combos (0)",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        )
        self.combo_title.pack(side="left", fill="x", expand=True)

        combo_filter_bar = ctk.CTkFrame(combo_card, fg_color="transparent")
        combo_filter_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))
        ctk.CTkLabel(
            combo_filter_bar, text="Lọc:", font=ctk.CTkFont(size=11), text_color=("gray50", "gray40")
        ).pack(side="left", padx=(0, 4))

        self.combo_seg = ctk.CTkSegmentedButton(
            combo_filter_bar,
            values=["Tất cả", "9router", "omnirouter"],
            command=self._on_combo_filter_change,
            height=26, font=ctk.CTkFont(size=11)
        )
        self.combo_seg.set("Tất cả")
        self.combo_seg.pack(side="left")

        btn_box1 = ctk.CTkFrame(combo_filter_bar, fg_color="transparent")
        btn_box1.pack(side="right")
        ctk.CTkButton(
            btn_box1, text="Chọn hết", width=68, height=25, font=ctk.CTkFont(size=11),
            command=lambda: self.set_group_selection("combo", True)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_box1, text="Bỏ chọn", width=62, height=25, font=ctk.CTkFont(size=11),
            fg_color=("gray80", "#3f3f46"), text_color=("black", "white"),
            command=lambda: self.set_group_selection("combo", False)
        ).pack(side="left", padx=2)

        self.scroll_combos = ctk.CTkScrollableFrame(combo_card, fg_color="transparent")
        self.scroll_combos.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # === CỘT PHẢI: MÔ HÌNH FREE ĐANG HOẠT ĐỘNG ===
        free_card = ctk.CTkFrame(tab, fg_color=("gray95", "#18181b"), corner_radius=10)
        free_card.grid(row=0, column=1, sticky="nsew", padx=(5, 4), pady=4)
        free_card.grid_columnconfigure(0, weight=1)
        free_card.grid_rowconfigure(2, weight=1)

        free_header = ctk.CTkFrame(free_card, fg_color="transparent")
        free_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))

        self.free_title = ctk.CTkLabel(
            free_header, text="Mô hình Free đang hoạt động (0)",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        )
        self.free_title.pack(side="left", fill="x", expand=True)

        free_filter_bar = ctk.CTkFrame(free_card, fg_color="transparent")
        free_filter_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))
        ctk.CTkLabel(
            free_filter_bar, text="Lọc:", font=ctk.CTkFont(size=11), text_color=("gray50", "gray40")
        ).pack(side="left", padx=(0, 4))

        self.free_seg = ctk.CTkSegmentedButton(
            free_filter_bar,
            values=["Tất cả", "9router", "omnirouter"],
            command=self._on_free_filter_change,
            height=26, font=ctk.CTkFont(size=11)
        )
        self.free_seg.set("Tất cả")
        self.free_seg.pack(side="left")

        btn_box2 = ctk.CTkFrame(free_filter_bar, fg_color="transparent")
        btn_box2.pack(side="right")
        ctk.CTkButton(
            btn_box2, text="Chọn hết", width=68, height=25, font=ctk.CTkFont(size=11),
            command=lambda: self.set_group_selection("free", True)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_box2, text="Bỏ chọn", width=62, height=25, font=ctk.CTkFont(size=11),
            fg_color=("gray80", "#3f3f46"), text_color=("black", "white"),
            command=lambda: self.set_group_selection("free", False)
        ).pack(side="left", padx=2)

        self.scroll_free = ctk.CTkScrollableFrame(free_card, fg_color="transparent")
        self.scroll_free.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _on_combo_filter_change(self, val: str):
        self.combo_router_filter = "ALL" if val == "Tất cả" else val
        self._apply_visibility_filter("combo", self.combo_router_filter)

    def _on_free_filter_change(self, val: str):
        self.free_router_filter = "ALL" if val == "Tất cả" else val
        self._apply_visibility_filter("free", self.free_router_filter)

    def _apply_visibility_filter(self, item_type: str, r_filter: str):
        for it in self.item_selections.values():
            if it["type"] == item_type and "widget" in it and it["widget"].winfo_exists():
                if r_filter == "ALL" or it["router"] == r_filter:
                    it["widget"].pack(fill="x", pady=2, padx=4)
                else:
                    it["widget"].pack_forget()

    # ---------- TAB 2: TOÀN BỘ MODELS ----------
    def _build_tab_all(self):
        tab = self.tab_all
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        self.search_entry = ctk.CTkEntry(
            toolbar, placeholder_text="Tìm kiếm theo ID hoặc tên model...",
            width=320, height=36
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self.on_search_change())

        self.filter_router_var = ctk.StringVar(value="Tất cả Router")
        self.router_filter = ctk.CTkOptionMenu(
            toolbar, values=["Tất cả Router", "9router", "omnirouter"],
            variable=self.filter_router_var, command=lambda v: self.on_search_change(),
            width=140, height=36
        )
        self.router_filter.pack(side="left", padx=5)

        self.filter_type_var = ctk.StringVar(value="Tất cả Loại")
        self.type_filter = ctk.CTkOptionMenu(
            toolbar, values=["Tất cả Loại", "Combos", "Free Candidates", "Paid Models"],
            variable=self.filter_type_var, command=lambda v: self.on_search_change(),
            width=150, height=36
        )
        self.type_filter.pack(side="left", padx=5)

        self.all_count_label = ctk.CTkLabel(toolbar, text="Tổng: 0 mô hình", font=ctk.CTkFont(size=12, weight="bold"))
        self.all_count_label.pack(side="right", padx=10)

        self.scroll_all = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.scroll_all.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))

        self.page_bar = ctk.CTkFrame(tab, fg_color="transparent")
        self.page_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_load_more = ctk.CTkButton(
            self.page_bar, text="Tải thêm mô hình...",
            command=self.load_next_page,
            width=220, height=32,
            fg_color=("gray85", "#27272a"), text_color=("black", "white")
        )
        self.btn_load_more.pack(side="left")

    def on_search_change(self):
        self.all_models_page = 1
        self.refresh_all_models_view()

    def refresh_all_models_view(self):
        self._all_models_dirty = False
        search = self.search_entry.get().strip().lower()
        r_filter = self.filter_router_var.get()
        t_filter = self.filter_type_var.get()
        deep = self.deep_scan_var.get()
        inc_auto = bool(self.config.get("include_auto_combos", False))

        filtered = []
        for r_name in ["9router", "omnirouter"]:
            if r_filter != "Tất cả Router" and r_filter != r_name:
                continue

            combo_ids = {str(c.get("id", "")).strip() for c in self.detected_combos.get(r_name, [])}
            models = self.all_models.get(r_name, [])
            for m in models:
                mid = str(m.get("id", "")).strip()
                mname = str(m.get("name", "") or mid).strip()

                if search and search not in mid.lower() and search not in mname.lower():
                    continue

                is_combo = ModelAnalyzer.is_combo(m, combo_ids, include_auto_combos=inc_auto)
                is_free = (not is_combo) and ModelAnalyzer.is_free_model(m, deep_scan_providers=deep)

                if t_filter == "Combos" and not is_combo:
                    continue
                if t_filter == "Free Candidates" and not is_free:
                    continue
                if t_filter == "Paid Models" and (is_combo or is_free):
                    continue

                filtered.append((r_name, m, is_combo, is_free))

        self.filtered_all_cache = filtered
        self.all_count_label.configure(text=f"Khớp: {len(filtered)} mô hình")

        for w in self.scroll_all.winfo_children():
            w.destroy()

        self._render_page_items(0, self.PAGE_SIZE)

    def load_next_page(self):
        start_idx = self.all_models_page * self.PAGE_SIZE
        end_idx = start_idx + self.PAGE_SIZE
        self.all_models_page += 1
        self._render_page_items(start_idx, end_idx)

    def _render_page_items(self, start: int, end: int):
        colors = self._get_row_colors()
        items_to_render = self.filtered_all_cache[start:end]
        for r_name, m, is_combo, is_free in items_to_render:
            mid = m.get("id", "")
            mname = m.get("name", "") or mid

            row = tk.Frame(
                self.scroll_all, bg=colors["row_bg"],
                highlightbackground=colors["row_border"], highlightthickness=1, bd=0
            )
            row.pack(fill="x", pady=2, padx=4)

            b_color = colors["9router_badge"] if r_name == "9router" else colors["omni_badge"]
            tk.Label(
                row, text=r_name.upper(), bg=b_color, fg="white",
                font=("DejaVu Sans", -10, "bold"), padx=6, pady=2
            ).pack(side="left", padx=8, pady=5)

            type_label = "Combo" if is_combo else ("Free" if is_free else "Paid")
            type_color = "#9333ea" if is_combo else ("#16a34a" if is_free else "#dc2626")
            tk.Label(
                row, text=type_label, bg=type_color, fg="white",
                font=("DejaVu Sans", -10, "bold"), padx=6, pady=2
            ).pack(side="right", padx=8, pady=5)

            display_txt = mid if mname == mid else f"{mid}  ({mname[:55]})"
            tk.Label(
                row, text=display_txt, bg=colors["row_bg"], fg=colors["text_fg"],
                font=("DejaVu Sans Mono", -12, "bold"), anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=4, pady=5)

        remaining = len(self.filtered_all_cache) - (start + len(items_to_render))
        if remaining > 0:
            self.btn_load_more.configure(text=f"Tải thêm mô hình... (còn {remaining})", state="normal")
        else:
            self.btn_load_more.configure(text="Đã hiển thị toàn bộ kết quả", state="disabled")

    # ---------- TAB 3: NHẬT KÝ TIẾN TRÌNH ----------
    def _build_tab_logs(self):
        tab = self.tab_logs
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(
            tab, font=ctk.CTkFont(family="monospace", size=11),
            fg_color=("gray95", "#121214"), text_color=("black", "#e4e4e7")
        )
        self.log_textbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

        log_bottom = ctk.CTkFrame(tab, fg_color="transparent")
        log_bottom.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            log_bottom, text="Xóa nhật ký", width=120, height=32,
            fg_color=("gray80", "#3f3f46"), text_color=("black", "white"),
            command=self.clear_logs
        ).pack(side="left")

        ctk.CTkButton(
            log_bottom, text="Lưu file nhật ký", width=140, height=32,
            command=self.export_logs
        ).pack(side="left", padx=10)

    # ==================== BỘ ĐIỀU PHỐI HÀNG ĐỢI UI CHỐNG NGHẼN (150ms BATCHING) ====================
    def _start_ui_flush_timer(self):
        self.flush_ui_queues()
        self.after(150, self._start_ui_flush_timer)

    def flush_ui_queues(self):
        with self._ui_lock:
            logs_batch = self._pending_logs[:]
            self._pending_logs.clear()
            free_batch = self._pending_free_rows[:]
            self._pending_free_rows.clear()
            status_item = self._pending_status
            self._pending_status = None
            prog_item = self._pending_progress
            self._pending_progress = None

        if prog_item is not None:
            self.update_progress(prog_item)

        if status_item is not None:
            self.set_status(status_item[0], status_item[1])

        if logs_batch:
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", "\n".join(logs_batch) + "\n")
            if self.tabview.get() == "Nhật ký tiến trình":
                self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")

        if free_batch:
            for r_name, m_item in free_batch:
                self._insert_working_free_row_Widget(r_name, m_item, update_counts=False)
            self._refresh_free_header_and_summary()

    def post_log(self, text: str):
        t_str = time.strftime('%H:%M:%S')
        with self._ui_lock:
            self._pending_logs.append(f"[{t_str}] {text}")

    def _append_log_direct(self, text: str):
        t_str = time.strftime('%H:%M:%S')
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{t_str}] {text}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def clear_logs(self):
        with self._ui_lock:
            self._pending_logs.clear()
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def export_logs(self):
        try:
            self.flush_ui_queues()
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            log_file = CONFIG_DIR / f"log_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            log_file.write_text(self.log_textbox.get("1.0", "end"), encoding='utf-8')
            self.show_modern_alert("Xuất nhật ký", f"Đã lưu nhật ký thành công tại:\n{log_file}", "info")
        except Exception as e:
            self.show_modern_alert("Lỗi", f"Không thể lưu nhật ký:\n{e}", "error")

    def post_status(self, text: str, color: str = "gray"):
        with self._ui_lock:
            self._pending_status = (text, color)

    def set_status(self, text: str, color: str = "gray"):
        color_map = {
            "gray": ("gray40", "gray50"),
            "green": ("#2e7d32", "#4ade80"),
            "red": ("#c62828", "#f87171"),
            "blue": ("#1565c0", "#38bdf8")
        }
        fg = color_map.get(color, color_map["gray"])
        self.status_label.configure(text=text, text_color=fg)

    def post_progress(self, val: float):
        with self._ui_lock:
            self._pending_progress = val

    def update_progress(self, val: float):
        clamped = max(0.0, min(1.0, val))
        self.progress_bar.set(clamped)
        self.progress_percent_label.configure(text=f"{int(clamped * 100)}%")

    # ==================== SIÊU TỐC NATIVE FLAT ROW RENDERING (HI-DPI PIXEL SAFE) ====================
    def _create_fast_native_row(
        self,
        parent_scroll,
        router_name: str,
        mid: str,
        sub_text: str,
        var: tk.BooleanVar,
        latency_ms: Optional[int] = None,
        visible: bool = True
    ) -> tk.Frame:
        """
        Tạo dòng giao diện bằng Native tk.Frame + tk.Checkbutton + tk.Label phẳng với kích thước font
        theo pixel âm (-12, -10) để không bị phóng to bất thường trên màn hình HiDPI X11,
        giúp hiển thị đầy đủ tên model dài mà vẫn vẽ 100 dòng trong < 0.04 giây!
        """
        colors = self._get_row_colors()
        row = tk.Frame(
            parent_scroll,
            bg=colors["row_bg"],
            highlightbackground=colors["row_border"],
            highlightthickness=1,
            bd=0
        )
        if visible:
            row.pack(fill="x", pady=2, padx=2)

        chk = tk.Checkbutton(
            row,
            variable=var,
            bg=colors["row_bg"],
            activebackground=colors["row_bg"],
            fg=colors["text_fg"],
            selectcolor=colors["select_bg"],
            highlightthickness=0,
            bd=0,
            command=self.update_summary_counts
        )
        chk.pack(side="left", padx=(6, 2), pady=5)

        right_box = tk.Frame(row, bg=colors["row_bg"], bd=0, highlightthickness=0)
        right_box.pack(side="right", padx=6, pady=4)

        badge_bg = colors["9router_badge"] if router_name == "9router" else colors["omni_badge"]
        badge_txt = "9ROUTER" if router_name == "9router" else "OMNI"
        tk.Label(
            right_box,
            text=badge_txt,
            bg=badge_bg,
            fg="white",
            font=("DejaVu Sans", -10, "bold"),
            padx=5,
            pady=1
        ).pack(side="right", padx=(5, 0))

        if latency_ms is not None:
            tk.Label(
                right_box,
                text=f"{latency_ms}ms",
                bg=colors["row_bg"],
                fg=colors["latency_fg"],
                font=("DejaVu Sans", -10, "bold")
            ).pack(side="right")

        mid_box = tk.Frame(row, bg=colors["row_bg"], bd=0, highlightthickness=0)
        mid_box.pack(side="left", fill="x", expand=True, padx=2, pady=3)

        lbl_main = tk.Label(
            mid_box,
            text=mid,
            bg=colors["row_bg"],
            fg=colors["text_fg"],
            font=("DejaVu Sans Mono", -12, "bold"),
            anchor="w",
            justify="left"
        )
        lbl_main.pack(fill="x", anchor="w")

        lbl_sub = tk.Label(
            mid_box,
            text=sub_text,
            bg=colors["row_bg"],
            fg=colors["sub_fg"],
            font=("DejaVu Sans", -10),
            anchor="w",
            justify="left"
        )
        lbl_sub.pack(fill="x", anchor="w")

        def _toggle_by_click(_event=None):
            var.set(not var.get())
            self.update_summary_counts()

        lbl_main.bind("<Button-1>", _toggle_by_click)
        lbl_sub.bind("<Button-1>", _toggle_by_click)

        return row

    def render_combos_list(self, router_name: str, combos: List[Dict]):
        for item_key, item in list(self.item_selections.items()):
            if item["type"] == "combo" and item["router"] == router_name:
                if "widget" in item and item["widget"].winfo_exists():
                    item["widget"].destroy()
                del self.item_selections[item_key]

        is_visible = self.combo_router_filter in ("ALL", router_name)
        for c in combos:
            mid = str(c.get("id", "")).strip()
            item_key = f"{router_name}::combo::{mid}"
            var = tk.BooleanVar(value=False)

            row = self._create_fast_native_row(
                self.scroll_combos,
                router_name=router_name,
                mid=mid,
                sub_text=f"Combo • {router_name}",
                var=var,
                latency_ms=None,
                visible=is_visible
            )

            self.item_selections[item_key] = {
                "var": var, "type": "combo", "router": router_name, "data": c, "widget": row
            }

        c_9r = sum(1 for it in self.item_selections.values() if it["type"] == "combo" and it["router"] == "9router")
        c_om = sum(1 for it in self.item_selections.values() if it["type"] == "combo" and it["router"] == "omnirouter")
        self.combo_title.configure(text=f"Danh sách Combos ({c_9r + c_om}) — [9R: {c_9r} | Omni: {c_om}]")
        self.update_summary_counts()

    def queue_working_free_row(self, router_name: str, model: Dict):
        with self._ui_lock:
            self._pending_free_rows.append((router_name, model))

    def _insert_working_free_row_Widget(self, router_name: str, model: Dict, update_counts: bool = True):
        mid = str(model.get("id", "")).strip()
        mname = str(model.get("name", "") or mid).strip()
        latency = model.get("latency_ms", 0)
        item_key = f"{router_name}::free::{mid}"

        if item_key in self.item_selections:
            return

        var = tk.BooleanVar(value=False)
        is_visible = self.free_router_filter in ("ALL", router_name)

        row = self._create_fast_native_row(
            self.scroll_free,
            router_name=router_name,
            mid=mid,
            sub_text=mname,
            var=var,
            latency_ms=latency,
            visible=is_visible
        )

        self.item_selections[item_key] = {
            "var": var, "type": "free", "router": router_name, "data": model, "widget": row
        }

        if update_counts:
            self._refresh_free_header_and_summary()

    def _refresh_free_header_and_summary(self):
        f_9r = sum(1 for it in self.item_selections.values() if it["type"] == "free" and it["router"] == "9router")
        f_om = sum(1 for it in self.item_selections.values() if it["type"] == "free" and it["router"] == "omnirouter")
        self.free_title.configure(text=f"Mô hình Free hoạt động ({f_9r + f_om}) — [9R: {f_9r} | Omni: {f_om}]")
        self.update_summary_counts()

    def add_working_free_row(self, router_name: str, model: Dict):
        self._insert_working_free_row_Widget(router_name, model, update_counts=True)

    def set_group_selection(self, group_type: str, selected: bool):
        r_filter = self.combo_router_filter if group_type == "combo" else self.free_router_filter
        for it in self.item_selections.values():
            if it["type"] == group_type:
                if r_filter == "ALL" or it["router"] == r_filter:
                    it["var"].set(selected)
        self.update_summary_counts()

    def update_summary_counts(self):
        sel_combos = sum(1 for it in self.item_selections.values() if it["type"] == "combo" and it["var"].get())
        sel_free = sum(1 for it in self.item_selections.values() if it["type"] == "free" and it["var"].get())
        total_combos = sum(1 for it in self.item_selections.values() if it["type"] == "combo")
        total_free = sum(1 for it in self.item_selections.values() if it["type"] == "free")
        total_sel = sel_combos + sel_free

        if total_sel > 0:
            self.summary_label.configure(
                text=f"Đang chọn: {sel_combos} Combos + {sel_free} Free Models"
            )
            self.btn_update.configure(text=f"Cập nhật ({total_sel} đã chọn)")
        else:
            if total_combos > 0 or total_free > 0:
                self.summary_label.configure(
                    text=f"Mặc định: Thêm TẤT CẢ ({total_combos} Combos & {total_free} Free)"
                )
                self.btn_update.configure(text=f"Cập nhật tất cả ({total_combos + total_free})")
            else:
                self.summary_label.configure(text="Chưa có dữ liệu. Nhấn 'Quét & Kiểm tra' để bắt đầu.")
                self.btn_update.configure(text="Cập nhật vào OpenCode")

    # ==================== ĐIỀU KHIỂN CHÍNH ====================
    def toggle_scan(self):
        if self.is_running:
            if self.current_worker:
                self.current_worker.cancel()
            self.set_status("Đang dừng tác vụ...", "red")
            self.btn_scan.configure(state="disabled")
            return

        self.config["deep_scan_providers"] = self.deep_scan_var.get()
        ConfigManager.save(self.config)

        self.is_running = True
        self.btn_scan.configure(text="Dừng quét")
        self.btn_update.configure(state="disabled")

        with self._ui_lock:
            self._pending_free_rows.clear()

        for it in self.item_selections.values():
            if "widget" in it and it["widget"].winfo_exists():
                it["widget"].destroy()
        self.item_selections.clear()
        self.all_models = {"9router": [], "omnirouter": []}
        self.detected_combos = {"9router": [], "omnirouter": []}
        self.working_free_models = {"9router": [], "omnirouter": []}

        self.combo_title.configure(text="Danh sách Combos (0)")
        self.free_title.configure(text="Mô hình Free hoạt động (0)")
        self.update_progress(0.0)
        self.update_summary_counts()

        worker = FastScanWorker(self, self.config, deep_scan=self.deep_scan_var.get())
        self.current_worker = worker
        worker.start()

    def update_opencode_action(self):
        sel_items = [it for it in self.item_selections.values() if it["var"].get()]
        is_default_all = False

        if not sel_items:
            sel_items = list(self.item_selections.values())
            is_default_all = True

        if not sel_items:
            self.show_modern_alert(
                "Chưa có dữ liệu",
                "Chưa có Combos hoặc Mô hình Miễn phí nào được tìm thấy.\nVui lòng bấm 'Quét & Kiểm tra' trước khi cập nhật vào OpenCode!",
                "warning"
            )
            return

        router_updates = {
            "9router": {
                "name": self.config.get("9router", {}).get("name", "9router (Local)"),
                "endpoint": self.config.get("9router", {}).get("endpoint", ""),
                "api_key": self.config.get("9router", {}).get("api_key", ""),
                "models": {}
            },
            "omnirouter": {
                "name": self.config.get("omnirouter", {}).get("name", "OmniRouter (NAS)"),
                "endpoint": self.config.get("omnirouter", {}).get("endpoint", ""),
                "api_key": self.config.get("omnirouter", {}).get("api_key", ""),
                "models": {}
            }
        }

        stats = {
            "9router": {"combo": 0, "free": 0},
            "omnirouter": {"combo": 0, "free": 0}
        }

        for it in sel_items:
            r = it["router"]
            d = it["data"]
            mid = str(d.get("id", "")).strip()
            mname = str(d.get("name", "") or mid).strip()
            if it["type"] == "combo":
                stats[r]["combo"] += 1
            else:
                stats[r]["free"] += 1
            if r in router_updates and mid:
                router_updates[r]["models"][mid] = {
                    "id": mid,
                    "name": mname,
                    "tool_call": True,
                    "temperature": True
                }

        custom_opencode_path = self.config.get("opencode_path", "")
        target_files = OpenCodeConfigManager.discover_target_config_files(custom_opencode_path)
        auth_files = OpenCodeConfigManager.get_auth_files()
        default_replace = bool(self.config.get("replace_router_models", True))

        def _do_execute_sync(replace_flag: bool):
            self.config["replace_router_models"] = replace_flag
            ConfigManager.save(self.config)

            success, report = OpenCodeConfigManager.sync_all_opencode(
                router_updates,
                custom_path=custom_opencode_path,
                replace_router_models=replace_flag
            )
            if success:
                saved_str = ", ".join(str(p) for p in report.get("saved_config_files", []))
                auth_str = ", ".join(str(p) for p in report.get("saved_auth_files", []))
                self.post_log(f"✓ ĐÃ ĐỒNG BỘ ĐA TẦNG VÀO OPENCODE THÀNH CÔNG!")
                self.post_log(f"   • Config files: {saved_str}")
                self.post_log(f"   • Auth files:   {auth_str}")
                self.post_log(
                    f"   • 9router: {stats['9router']['combo']} Combos + {stats['9router']['free']} Free Models\n"
                    f"   • OmniRouter: {stats['omnirouter']['combo']} Combos + {stats['omnirouter']['free']} Free Models"
                )
                self.flush_ui_queues()
                UpdateSuccessDialog(self, report=report, stats=stats)
            else:
                err_txt = "\n".join(report.get("errors", ["Lỗi không xác định"]))
                self.post_log(f"✗ ĐỒNG BỘ THẤT BẠI: {err_txt}")
                self.flush_ui_queues()
                self.show_modern_alert("Lỗi đồng bộ OpenCode", f"Không thể lưu cấu hình OpenCode:\n{err_txt}", "error")

        ConfirmUpdateDialog(
            self,
            is_default_all=is_default_all,
            stats=stats,
            router_updates=router_updates,
            target_files=target_files,
            auth_files=auth_files,
            default_replace=default_replace,
            on_confirm_callback=_do_execute_sync
        )

    def open_settings_dialog(self):
        SettingsDialog(self)

    def toggle_theme(self):
        current = ctk.get_appearance_mode()
        new_mode = "Light" if current == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)


# ==================== POPUP DIALOG CÀI ĐẶT RỘNG RÃI & CO GIÃN ====================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent: AutoUpdateFreeApp):
        super().__init__(parent)
        self.parent = parent
        self.title("Cấu hình Router & OpenCode")

        self.geometry("820x740")
        self.minsize(720, 580)
        self.resizable(True, True)
        self.transient(parent)

        self._build_settings_ui()
        self._center_on_parent()

    def _center_on_parent(self):
        self.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + max(0, (pw - w)//2)}+{py + max(0, (ph - h)//2)}")

    def _build_settings_ui(self):
        bottom_bar = ctk.CTkFrame(self, fg_color=("gray95", "#18181b"), height=64, corner_radius=0)
        bottom_bar.pack(side="bottom", fill="x")
        bottom_bar.pack_propagate(False)

        ctk.CTkButton(
            bottom_bar, text="Lưu toàn bộ cấu hình",
            command=self.save_all, width=190, height=40,
            fg_color=("#2e7d32", "#16a34a"), hover_color=("#1b5e20", "#15803d"),
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=20, pady=12)

        ctk.CTkButton(
            bottom_bar, text="Đóng",
            command=self.destroy, width=100, height=40,
            fg_color=("gray80", "#3f3f46"), text_color=("black", "white"),
            font=ctk.CTkFont(size=13)
        ).pack(side="right", padx=20, pady=12)

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=(15, 10))

        ctk.CTkLabel(
            container, text="Cài đặt Endpoint & API Key Router",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(0, 15))

        self._create_router_card(container, "9router", "9router (Local)", self.parent.config.get("9router", {}))
        self._create_router_card(container, "omnirouter", "OmniRouter (NAS)", self.parent.config.get("omnirouter", {}))

        op_card = ctk.CTkFrame(container, fg_color=("gray90", "#27272a"), corner_radius=10)
        op_card.pack(fill="x", pady=10)

        ctk.CTkLabel(
            op_card, text="Đồng bộ Cấu hình OpenCode (opencode.json + opencode.jsonc + auth.json)",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=14, pady=(10, 4))

        detected_files = OpenCodeConfigManager.discover_target_config_files(self.parent.config.get("opencode_path", ""))
        detected_str = " & ".join(str(p) for p in detected_files[:2])
        self.op_path_entry = ctk.CTkEntry(
            op_card, font=ctk.CTkFont(family="monospace", size=12),
            placeholder_text=str(detected_files[0]), height=36
        )
        self.op_path_entry.pack(fill="x", padx=14, pady=4)
        if self.parent.config.get("opencode_path"):
            self.op_path_entry.insert(0, self.parent.config.get("opencode_path"))

        ctk.CTkLabel(
            op_card, text=f"Tự động đồng bộ vào: {detected_str}",
            font=ctk.CTkFont(size=11), text_color=("gray50", "gray40")
        ).pack(anchor="w", padx=14, pady=(0, 6))

        self.inc_auto_var = ctk.BooleanVar(value=bool(self.parent.config.get("include_auto_combos", False)))
        ctk.CTkCheckBox(
            op_card,
            text="Bao gồm cả 38 mẫu định tuyến ảo built-in 'auto/*' của OmniRouter vào danh sách Combos",
            variable=self.inc_auto_var,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=14, pady=(4, 12))

    def _create_router_card(self, parent, r_key: str, r_title: str, r_cfg: Dict):
        card = ctk.CTkFrame(parent, fg_color=("gray90", "#27272a"), corner_radius=10)
        card.pack(fill="x", pady=8)

        h = ctk.CTkFrame(card, fg_color="transparent")
        h.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(h, text=r_title, font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        status_lbl = ctk.CTkLabel(h, text="● Chưa kiểm tra", font=ctk.CTkFont(size=12), text_color=("gray50", "gray40"))
        status_lbl.pack(side="right")
        setattr(self, f"{r_key}_status_lbl", status_lbl)

        ctk.CTkLabel(card, text="Endpoint URL:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(4, 0))
        ep_entry = ctk.CTkEntry(card, font=ctk.CTkFont(family="monospace", size=12), height=36)
        ep_entry.pack(fill="x", padx=14, pady=4)
        ep_entry.insert(0, r_cfg.get("endpoint", ""))
        setattr(self, f"{r_key}_endpoint_entry", ep_entry)

        ctk.CTkLabel(card, text="API Key:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=14, pady=(6, 0))
        k_frame = ctk.CTkFrame(card, fg_color="transparent")
        k_frame.pack(fill="x", padx=14, pady=4)

        key_entry = ctk.CTkEntry(k_frame, font=ctk.CTkFont(family="monospace", size=12), show="•", height=36)
        key_entry.pack(side="left", fill="x", expand=True)
        key_entry.insert(0, r_cfg.get("api_key", ""))
        setattr(self, f"{r_key}_key_entry", key_entry)

        show_var = ctk.BooleanVar(value=False)
        def toggle_key():
            key_entry.configure(show="" if show_var.get() else "•")
        chk = ctk.CTkCheckBox(k_frame, text="Hiện key", variable=show_var, command=toggle_key, width=80)
        chk.pack(side="right", padx=(10, 0))

        t_btn = ctk.CTkButton(
            card, text="Kiểm tra kết nối", width=150, height=32,
            font=ctk.CTkFont(size=12),
            command=lambda k=r_key: self.test_single_router(k)
        )
        t_btn.pack(anchor="w", padx=14, pady=(8, 12))
        setattr(self, f"{r_key}_test_btn", t_btn)

    def test_single_router(self, r_key: str):
        raw_ep = getattr(self, f"{r_key}_endpoint_entry").get().strip()
        ep = ConfigManager.sanitize_endpoint(raw_ep)
        key = getattr(self, f"{r_key}_key_entry").get().strip()
        lbl = getattr(self, f"{r_key}_status_lbl")
        btn = getattr(self, f"{r_key}_test_btn")

        if not ep:
            lbl.configure(text="● Thiếu endpoint", text_color="#dc2626")
            return

        lbl.configure(text="● Đang kiểm tra...", text_color="#f59e0b")
        btn.configure(state="disabled")

        def run_test():
            client = APIClient(ep, key)
            ok, models, msg = client.fetch_models_and_verify()
            if ok:
                api_combos, _ = client.fetch_combos_endpoint()
                cat = ModelAnalyzer.categorize_models(
                    models,
                    api_combos=api_combos,
                    include_auto_combos=self.inc_auto_var.get()
                )
                c_count = len(cat['combos'])
                self.parent.config[r_key]["endpoint"] = ep
                self.parent.config[r_key]["api_key"] = key
                ConfigManager.save(self.parent.config)
                self.after(0, lambda: lbl.configure(
                    text=f"● OK ({len(models)} models, {c_count} combos) — Đã lưu",
                    text_color=("#16a34a", "#4ade80")
                ))
            else:
                self.after(0, lambda: lbl.configure(
                    text=f"● Lỗi: {msg[:35]}", text_color=("#dc2626", "#f87171")
                ))
            self.after(0, lambda: btn.configure(state="normal"))

        threading.Thread(target=run_test, daemon=True).start()

    def save_all(self):
        self.parent.config["9router"]["endpoint"] = ConfigManager.sanitize_endpoint(
            getattr(self, "9router_endpoint_entry").get().strip()
        )
        self.parent.config["9router"]["api_key"] = getattr(self, "9router_key_entry").get().strip()
        self.parent.config["omnirouter"]["endpoint"] = ConfigManager.sanitize_endpoint(
            getattr(self, "omnirouter_endpoint_entry").get().strip()
        )
        self.parent.config["omnirouter"]["api_key"] = getattr(self, "omnirouter_key_entry").get().strip()
        self.parent.config["opencode_path"] = self.op_path_entry.get().strip()
        self.parent.config["include_auto_combos"] = self.inc_auto_var.get()

        if ConfigManager.save(self.parent.config):
            self.destroy()
            self.parent.show_modern_alert("Cài đặt", "Đã lưu toàn bộ cấu hình Router & OpenCode thành công!", "info")
        else:
            self.parent.show_modern_alert("Lỗi", "Không thể lưu file cấu hình.", "error")


# ==================== MAIN ENTRY POINT ====================
def main():
    controller = SingleInstanceController()
    if controller.check_and_notify_running():
        sys.exit(0)

    app = AutoUpdateFreeApp()

    controller.on_activate = lambda: app.after(0, app.bring_to_front)
    controller.start_listener()

    def on_closing():
        controller.stop()
        if app.current_worker:
            app.current_worker.cancel()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()