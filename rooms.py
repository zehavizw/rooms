import streamlit as st
import requests
from datetime import datetime
import time
import threading

# חיבור לכספת
URL = f"{st.secrets['SUPABASE_URL']}/rest/v1/bookings"
HEADERS = {
    "apikey": st.secrets["SUPABASE_KEY"],
    "Content-Type": "application/json"
}

# --- פונקציות עזר ---

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
        try: requests.get(url)
        except: pass

def schedule_msg(msg, delay_minutes):
    def wait_and_send():
        time.sleep(delay_minutes * 60)
        send_telegram(msg)
    threading.Thread(target=wait_and_send).start()

def calculate_price_logic(total_people, paying_people, elapsed_minutes):
    # מחירון לפי כמות אנשים (1, 2-4, 5-9, 10+)
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]

    # לוגיקה: חלק משעה מחושב לפי התעריף של השעה שלפני
    if elapsed_minutes <= 120: # שעתיים ראשונות
        price_per_person = (elapsed_minutes / 60) * rates[0]
    elif elapsed_minutes <= 180: # שעה שלישית
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    else: # שעה רביעית ואילך
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    price_per_paying = total_bill / paying_people if paying_people > 0 else 0
    return total_bill, price_per_paying

# --- ממשק האפליקציה ---

st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - קריוקי")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון ידני"])

with tab1:
    if st.button("🔄 סנכרן מהאתר"):
        try:
            # ניסיון סנכרון עם המפתח הקבוע (שלא פג תוקף!)
            res = requests.get(f"{URL}?select=*,room:rooms(*)", headers=HEADERS)
            if res.status_code == 200:
                st.session_state.web_bookings = res.json()
                st.success("הנתונים נמשכו בהצלחה!")
            else:
                st.error(f"שגיאה {res.status_code}: האתר דורש זיהוי אישי. נצטרך את המעקף של גוגל.")
        except Exception as e:
            st.error(f"שגיאה טכנית: {e}")

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            with st.expander(f"{b.get('customer_name', 'לקוח')} | {b.get('start_time', '')}"):
                p_count = st.number_input("כמה אנשים?", 1, 50, 2, key=f"p_{b['id']}")
                duration = st.number_input("זמן מוזמן (דקות)", 15, 300, 60, key=f"d_{b['id']}")
                if st.button("🚀 כניסה (צ'ק-אין)", key=f"btn_{b['id']}"):
                    if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
                    st.session_state.rooms_active[b['id']] = {
                        "name": b.get('customer_name', 'לקוח'),
                        "start": datetime.now(),
                        "total_people": p_count,
                        "paying_people": p_count,
                        "booked_duration": duration
                    }
                    send_telegram(f"✅ {b.get('customer_name')} נכנסו! התראה תישלח בעוד {duration} דקות.")
                    schedule_msg(f"⏰ זמן נגמר! {b.get('customer_name')} היו אמורים לצאת.", duration)
                    st.rerun()

with tab2:
    if 'rooms_active' in st.session_state and st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            elapsed = (datetime.now() - data['start']).total_seconds() // 60
            st.subheader(f"בחדר: {data['name']}")
            
            data['paying_people'] = st.number_input("כמה משלמים?", 1, 50, data['paying_people'], key=f"pay_{rid}")
            total_bill, per_person = calculate_price_logic(data['total_people'], data['paying_people'], elapsed)
            
            c1, c2 = st.columns(2)
            c1.metric("סה\"כ לתשלום", f"₪{total_bill:.2f}")
            c2.metric("לאדם משלם", f"₪{per_person:.2f}")
            
            if st.button("💰 סיום ותשלום", key=f"end_{rid}", use_container_width=True):
                send_telegram(f"💸 סשן הסתיים: {data['name']}. נגבה סה\"כ: ₪{total_bill:.2f}")
                del st.session_state.rooms_active[rid]
                st.rerun()
            st.divider()
    else:
        st.info("אין חדרים פעילים.")

with tab3:
    st.subheader("🧮 מחשבון מהיר")
    calc_total = st.number_input("סה\"כ אנשים (לתעריף)", 1, 50, 4)
    calc_paying = st.number_input("כמה משלמים?", 1, 50, 4)
    calc_minutes = st.number_input("כמה דקות?", 1, 600, 60)
    
    total_res, per_res = calculate_price_logic(calc_total, calc_paying, calc_minutes)
    st.markdown(f"### סה\"כ: ₪{total_res:.2f} | לאדם: ₪{per_res:.2f}")
