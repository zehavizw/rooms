import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import threading

# הגדרות בסיס
BASE_URL = st.secrets['SUPABASE_URL']
BOOKINGS_URL = f"{BASE_URL}/rest/v1/bookings"
AUTH_URL = f"{BASE_URL}/auth/v1/token?grant_type=refresh_token"

# --- פונקציות ליבה ---

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

def schedule_exit_notification(name, duration_minutes):
    def wait_and_send():
        time.sleep(duration_minutes * 60)
        send_telegram(f"⏰ זמן נגמר! הקבוצה של {name} צריכה לצאת.")
    threading.Thread(target=wait_and_send).start()

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

# --- אתחול משתני זיכרון ---
if 'notified_entries' not in st.session_state: st.session_state.notified_entries = set()
if 'finished_bookings' not in st.session_state: st.session_state.finished_bookings = set()
if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 מרכז ניהול חכם - קריוקי")

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
        now_str = datetime.now().strftime("%H:%M")
        for b in st.session_state.web_bookings:
            name = b.get('customer_name', 'לקוח')
            scheduled_time = b.get('start_time', '--:--')
            bid = str(b['id'])
            
            # קביעת הסטטוס להצגה בכותרת
            status_tag = ""
            if bid in st.session_state.rooms_active: status_tag = "🔵 בפעילות"
            elif bid in st.session_state.finished_bookings: status_tag = "🏁 נגמר הזמן"

            with st.expander(f"{status_tag} {name} | {scheduled_time}"):
                if bid in st.session_state.finished_bookings:
                    st.success("✅ האירוח הסתיים והתשלום נגבה.")
                elif bid in st.session_state.rooms_active:
                    st.info("הקבוצה נמצאת כרגע בחדר. עברי ללשונית 'חדרים בפעילות'.")
                else:
                    p_count = st.number_input("כמה אנשים?", 1, 50, 2, key=f"p_{bid}")
                    duration = st.number_input("לכמה זמן? (דקות)", 15, 300, 60, key=f"d_{bid}")
                    if st.button("🚀 כניסה (צ'ק-אין)", key=f"btn_{bid}"):
                        st.session_state.rooms_active[bid] = {
                            "name": name, "actual_start": datetime.now(),
                            "total_people": p_count, "paying_people": p_count, "planned_duration": duration
                        }
                        send_telegram(f"✅ {name} נכנסו. הודעת יציאה בעוד {duration} דקות.")
                        schedule_exit_notification(name, duration)
                        st.rerun()

with tab2:
    if st.session_state.rooms_active:
        placeholder = st.empty()
        while st.session_state.rooms_active:
            with placeholder.container():
                for rid, data in list(st.session_state.rooms_active.items()):
                    diff = datetime.now() - data['actual_start']
                    elapsed_min = diff.total_seconds() / 60
                    mins, secs = divmod(int(diff.total_seconds()), 60)
                    
                    st.subheader(f"בחדר: {data['name']}")
                    total_p, per_p = calculate_price_logic(data['total_people'], data['paying_people'], elapsed_min)
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("⏱️ זמן", f"{mins:02d}:{secs:02d}")
                    c2.metric("💰 סה\"כ", f"₪{total_p:.2f}")
                    c3.metric("👤 לאדם", f"₪{per_p:.2f}")
                    
                    if st.button("💰 סיום ותשלום", key=f"end_{rid}"):
                        send_telegram(f"💸 {data['name']} סיימו. נגבה סה\"כ: ₪{total_p:.2f}")
                        # העברה לרשימת ה"הסתיימו" ומחיקה מהפעילים
                        st.session_state.finished_bookings.add(rid)
                        del st.session_state.rooms_active[rid]
                        st.rerun()
                    st.divider()
            time.sleep(1)
    else: st.info("אין חדרים פעילים כרגע.")

# ... לשונית המחשבון נשארת אותו דבר ...
