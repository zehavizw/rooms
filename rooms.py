import streamlit as st
import requests
from datetime import datetime
import time

# הגדרות בסיס
BASE_URL = st.secrets['SUPABASE_URL']
BOOKINGS_URL = f"{BASE_URL}/rest/v1/bookings"
AUTH_URL = f"{BASE_URL}/auth/v1/token?grant_type=refresh_token"

# --- פונקציות עזר ---

def get_fresh_token():
    payload = {"refresh_token": st.secrets["REFRESH_TOKEN"]}
    headers = {"apikey": st.secrets["SUPABASE_KEY"], "Content-Type": "application/json"}
    try:
        res = requests.post(AUTH_URL, json=payload, headers=headers)
        return res.json().get("access_token") if res.status_code == 200 else None
    except: return None

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg})
        except: pass

def calculate_price_logic(total_people, paying_people, elapsed_minutes):
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]

    if elapsed_minutes <= 120:
        price_per_person = (elapsed_minutes / 60) * rates[0]
    elif elapsed_minutes <= 180:
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    else:
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    per_paying = total_bill / paying_people if paying_people > 0 else 0
    return total_bill, per_paying

# --- אתחול משתנים ---
if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
if 'finished_bookings' not in st.session_state: st.session_state.finished_bookings = set()

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - קריוקי")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if st.button("🔄 סנכרן מהאתר"):
        token = get_fresh_token()
        if token:
            today = datetime.now().strftime("%Y-%m-%d")
            headers = {"apikey": st.secrets["SUPABASE_KEY"], "Authorization": f"Bearer {token}"}
            params = [("select", "*,room:rooms(*)"), ("booking_date", f"eq.{today}"), ("status", "neq.cancelled")]
            res = requests.get(BOOKINGS_URL, headers=headers, params=params)
            if res.status_code == 200:
                st.session_state.web_bookings = res.json()
                st.success("הזמנות עודכנו!")

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            name = b.get('customer_name', 'לקוח')
            bid = str(b['id'])
            status = "🏁 נגמר" if bid in st.session_state.finished_bookings else ("🔵 בפנים" if bid in st.session_state.rooms_active else "")
            
            with st.expander(f"{status} {name} | {b.get('start_time')}"):
                if bid not in st.session_state.rooms_active and bid not in st.session_state.finished_bookings:
                    p_count = st.number_input("אנשים", 1, 50, 2, key=f"p_{bid}")
                    if st.button("🚀 כניסה", key=f"btn_{bid}"):
                        st.session_state.rooms_active[bid] = {
                            "name": name, "start": datetime.now(), "total_people": p_count, "paying_people": p_count
                        }
                        st.rerun()

with tab2:
    if st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            diff = datetime.now() - data['start']
            elapsed_min = diff.total_seconds() / 60
            mins, secs = divmod(int(diff.total_seconds()), 60)
            
            st.subheader(f"בחדר: {data['name']}")
            data['paying_people'] = st.number_input("משלמים", 1, 50, data['paying_people'], key=f"pay_{rid}")
            
            total_p, per_p = calculate_price_logic(data['total_people'], data['paying_people'], elapsed_min)
            
            c1, c2 = st.columns(2)
            c1.metric("⏱️ זמן", f"{mins:02d}:{secs:02d}")
            c2.metric("💰 סה\"כ", f"₪{total_p:.2f}")
            
            if st.button("💰 סיום ותשלום", key=f"end_{rid}"):
                send_telegram(f"💸 {data['name']} סיימו. נגבה: ₪{total_p:.2f}")
                st.session_state.finished_bookings.add(rid)
                del st.session_state.rooms_active[rid]
                st.rerun()
            st.divider()
        
        # הטריק של הטיימר: מרענן את הדף כל 10 שניות כדי לעדכן שעון ומחיר
        time.sleep(10)
        st.rerun()
    else:
        st.info("אין חדרים פעילים.")
