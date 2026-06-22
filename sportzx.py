import requests
import json
import base64
import os
from datetime import datetime, timedelta
from Crypto.Cipher import AES

# 🔐 Load from GitHub Secrets
APP_PASSWORD = os.getenv("APP_PASSWORD")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_FID = os.getenv("FIREBASE_FID")
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID")
PROJECT_NUMBER = os.getenv("PROJECT_NUMBER")
PACKAGE_NAME = os.getenv("PACKAGE_NAME")
AES_SECRET = os.getenv("AES_SECRET").encode()

REPLACE_STREAM = "https://video.twimg.com/amplify_video/1919602814160125952/pl/t5p2RHLI21i-hXga.m3u8?variant_version=1&tag=14"
NEW_STREAM = "https://fallback-video.ivan-flux.workers.dev/video/index.m3u8"


class SportzxClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Dalvik/2.1.0 (Linux; Android 13)",
            "Accept-Encoding": "gzip"
        })

    def _generate_aes_key_iv(self, s: str):
        CHARSET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+!@#$%&="
        u32 = lambda x: x & 0xFFFFFFFF
        data = s.encode("utf-8"); n = len(data); u = 0x811c9dc5
        for b in data: u = u32((u ^ b) * 0x1000193)
        key = bytearray(16)
        for i in range(16):
            b = data[i % n]; u = u32(u * 0x1f + (i ^ b)); key[i] = CHARSET[u % len(CHARSET)]
        u = 0x811c832a
        for b in data: u = u32((u ^ b) * 0x1000193)
        iv = bytearray(16); idx = 0; acc = 0
        while idx != 0x30:
            b = data[idx % n]; u = u32(u * 0x1d + (acc ^ b)); iv[idx // 3] = CHARSET[u % len(CHARSET)]
            idx += 3; acc = u32(acc + 7)
        return bytes(key), bytes(iv)

    def _decrypt_data(self, b64_data: str):
        try:
            ct = base64.b64decode(b64_data)
            key, iv = self._generate_aes_key_iv(APP_PASSWORD)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            pt = cipher.decrypt(ct); pad = pt[-1]
            if 1 <= pad <= 16: pt = pt[:-pad]
            return pt.decode("utf-8", errors="replace")
        except: return ""

    def _fetch_and_decrypt(self, url: str):
        try:
            r = self.session.get(url, timeout=self.timeout)
            decrypted = self._decrypt_data(r.json().get("data", ""))
            return json.loads(decrypted) if decrypted else {}
        except: return {}

    def _get_api_url(self):
        try:
            r = self.session.post(f"https://firebaseinstallations.googleapis.com/v1/projects/{PROJECT_NUMBER}/installations", json={"fid": FIREBASE_FID, "appId": FIREBASE_APP_ID, "authVersion": "FIS_v2", "sdkVersion": "a:18.0.0"}, headers={"x-goog-api-key": FIREBASE_API_KEY})
            auth_token = r.json()["authToken"]["token"]
            r2 = self.session.post(f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT_NUMBER}/namespaces/firebase:fetch", json={"appVersion": "2.1", "appInstanceId": FIREBASE_FID, "appId": FIREBASE_APP_ID, "packageName": PACKAGE_NAME}, headers={"X-Goog-Api-Key": FIREBASE_API_KEY, "X-Goog-Firebase-Installations-Auth": auth_token})
            return r2.json().get("entries", {}).get("api_url")
        except: return None

    def _apply_rules(self, data):
        # 🛠️ ফাইনাল ম্যাপিং টেবিল (৭টি সলিড কারেকশন রুল)
        correction_map = {
            'J': 'a', 
            '$': '5', 
            'l': '2', 
            'Q': 'b', 
            'W': 'f', 
            ')': '2', 
            'Z': 'a'
        }

        for event in data:
            if "formats" in event: del event["formats"]
            if "title" in event:
                event["title"] = event["title"].replace("Sportzx", "SPORTIFy").replace("SportzX", "SPORTIFy")

            for channel in event.get("channels_data", []):
                title = channel.get("title", "")
                title = title.replace("Sportzx", "SPORTIFy").replace("SportzX", "SPORTIFy").replace("SPX", "SPY")
                channel["title"] = title

                # --- 🎯 API Key (Token) ডিকোডিং ও মেরামতের ফাইনাল লজিক ---
                api_val = channel.get("api", "")
                if api_val:
                    # ১. যদি Base64 থাকে তবে ডিকোড করা
                    try:
                        if len(api_val) > 20:
                            decoded = base64.b64decode(api_val).decode('utf-8')
                            if ":" in decoded: api_val = decoded
                    except: pass
                    
                    # ২. সমস্ত ভুল ক্যারেক্টার সঠিক হেক্স কোডে রূপান্তর করা
                    for wrong, right in correction_map.items():
                        api_val = api_val.replace(wrong, right)
                    
                    channel["api"] = api_val

                link = channel.get("link", "")
                if link == REPLACE_STREAM: link = NEW_STREAM
                channel["link"] = link
        return data

    def get_json_data(self):
        api_url = self._get_api_url()
        if not api_url: return []
        raw_events = self._fetch_and_decrypt(f"{api_url.rstrip('/')}/events.json")
        if not isinstance(raw_events, list): return []

        manual_file = "manual_data.json"
        manual = {}
        id_mapping = {}
        if os.path.exists(manual_file):
            try:
                with open(manual_file, "r") as f:
                    manual = json.load(f)
                    id_mapping = manual.get("id_mapping", {})
            except: pass

        for event in raw_events:
            eid = str(event.get("id"))
            fetch_id = id_mapping.get(eid, eid)
            if fetch_id:
                event["channels_data"] = self._fetch_and_decrypt(f"{api_url.rstrip('/')}/channels/{fetch_id}.json")

        if manual:
            try:
                manual_events = manual.get("manual_events", [])
                now_utc = datetime.utcnow()
                cleaned_manual = []
                for m_ev in manual_events:
                    end_time_str = m_ev.get("eventInfo", {}).get("endTime", "")
                    try:
                        end_time_dt = datetime.strptime(end_time_str, "%Y/%m/%d %H:%M:%S +0000")
                        if now_utc < end_time_dt: cleaned_manual.append(m_ev)
                    except: cleaned_manual.append(m_ev)

                live_ids = [str(ev.get("id")) for ev in raw_events]
                for m_ev in cleaned_manual:
                    m_id = str(m_ev.get("id"))
                    if m_id in live_ids:
                        for i, ev in enumerate(raw_events):
                            if str(ev.get("id")) == m_id: raw_events[i] = m_ev
                    else:
                        raw_events.append(m_ev)

                delete_ids = [str(d) for d in manual.get("delete", [])]
                raw_events = [ev for ev in raw_events if str(ev.get("id")) not in delete_ids]

                manual["manual_events"] = cleaned_manual
                manual["id_mapping"] = {k: v for k, v in id_mapping.items() if k in live_ids}
                with open(manual_file, "w") as f: json.dump(manual, f, indent=4)
            except: pass

        return self._apply_rules(raw_events)


def encrypt_json(data):
    ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%I:%M:%S %p %d-%m-%Y")
    wrapped_data = {"AUTHOR": "iVan_FLUx", "TELEGRAM": "https://t.me/iVan_flux", "Last update time": ist_now, "events": data}
    key = AES_SECRET[:32]; cipher = AES.new(key, AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(json.dumps(wrapped_data).encode())
    return base64.b64encode(cipher.nonce + tag + ciphertext).decode()

if __name__ == "__main__":
    client = SportzxClient()
    data = client.get_json_data()
    if data:
        with open("Sportzx.json", "w", encoding="utf-8") as f:
            json.dump({"data": encrypt_json(data)}, f, indent=4)
        print("Final Deployment: All Key & Mismatch Faults Fixed Perfectly!")
