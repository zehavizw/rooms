import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import threading

# טעינת נתונים מהכספת (Secrets)
URL = f"{st.secrets.get('SUPABASE_URL', '')}/rest/v1/bookings"
HEADERS = {
    "apikey": st.secrets.get("SUPABASE_KEY", ""),
    "Authorization": st.secrets.get("SUPABASE_AUTH", ""),
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
    # מחירון לפי כמות אנשים כוללת (בשביל לקבוע את התעריף)
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15] # 10+ אנשים

    # לוגיקת החישוב שלך: חלק משעה מחושב לפי השעה שלפני
    # 0-120 דקות (שעתיים ראשונות) מחושבות לפי תעריף שעה 1
    if elapsed_minutes <= 120:
        price_per_person = (elapsed_minutes / 60) * rates[0]
    # 121-180 דקות (השעה השלישית) מחושבות לפי תעריף שעה 2
    elif elapsed_minutes <= 180:
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    # 181+ דקות (מהשעה הרביעית) מחושבות לפי תעריף שעה 3
    else:
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    price_per_paying = total_bill / paying_people if paying_people > 0 else 0
    
    return total_bill, price_per_paying

# --- ממשק האפליקציה ---

st.set_page_config(page_title="קריוקי - ניהול חכם", layout="centered")
st.title("🎤 מרכז בקרה - חדרי קריוקי")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון ידני"])

with tab1:
    if st.button("🔄 סנכרן מהאתר"):
        try:
            res = requests.get(f"{URL}?select=*,room:rooms(*)", headers=HEADERS)
            if res.status_code == 200:
                st.session_state.web_bookings = res.json()
                st.success("הנתונים נמשכו בהצלחה!")
            else: st.error("שגיאה בחיבור לשרת")
        except: st.error("וודאי שה-Secrets מוגדרים נכון")

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
                        "paying_people": p_count, # ברירת מחדל: כולם משלמים
                        "booked_duration": duration
                    }
                    send_telegram(f"✅ {b.get('customer_name')} נכנסו! התראת יציאה תישלח בעוד {duration} דקות.")
                    schedule_msg(f"⏰ זמן נגמר! {b.get('customer_name')} היו אמורים לצאת.", duration)
                    st.rerun()

with tab2:
    if 'rooms_active' in st.session_state and st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            elapsed = (datetime.now() - data['start']).total_seconds() // 60
            
            st.subheader(f"חדר פעיל: {data['name']}")
            col1, col2 = st.columns(2)
            with col1:
                data['paying_people'] = st.number_input("כמה משלמים?", 1, 50, data['paying_people'], key=f"pay_{rid}")
            with col2:
                st.write(f"⏱️ דקות בחדר: {int(elapsed)}")
            
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
        st.info("אין חדרים בפעילות כרגע. עברי ללוח ההזמנות כדי להכניס קבוצה.")

with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_total = st.number_input("סה\"כ אנשים בחדר (לקביעת תעריף)", 1, 50, 4)
    calc_paying = st.number_input("כמה אנשים משלמים בפועל?", 1, 50, 4)
    calc_minutes = st.number_input("כמה דקות שהו בחדר?", 1, 600, 60)
    
    total_res, per_res = calculate_price_logic(calc_total, calc_paying, calc_minutes)
    
    st.divider()
    res_col1, res_col2 = st.columns(2)
    res_col1.markdown(f"### סה\"כ לכולם:\n# ₪{total_res:.2f}")
    res_col2.markdown(f"### מחיר לאדם:\n# ₪{per_res:.2f}")
    
    if st.button("שלחי סיכום מחיר לטלגרם"):
        send_telegram(f"📊 חישוב מחיר: {calc_total} אנשים, {calc_minutes} דקות. סה\"כ: ₪{total_res:.2f} ({per_res:.2f} ₪ לאדם).")
        st.success("החישוב נשלח לבוט!")
