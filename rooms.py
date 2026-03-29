import streamlit as st
import requests
from datetime import datetime
import time
import threading

# הגדרות חיבור
URL = f"{st.secrets['SUPABASE_URL']}/rest/v1/bookings"
HEADERS = {
    "apikey": st.secrets["SUPABASE_KEY"],
    "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}",
    "Content-Type": "application/json"
}

# --- פונקציות עזר ---

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg})
        except: pass

def schedule_msg(msg, delay_minutes):
    def wait_and_send():
        time.sleep(max(0, delay_minutes * 60))
        send_telegram(msg)
    threading.Thread(target=wait_and_send).start()

def calculate_price_logic(total_people, paying_people, elapsed_minutes):
    # מחירון לפי כמות אנשים (שעה 1, שעה 2, שעה 3+)
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]

    # לוגיקה: חלק משעה מחושב לפי המחיר של השעה שלפני (0-120 דקות לפי תעריף שעה 1)
    if elapsed_minutes <= 120:
        price_per_person = (elapsed_minutes / 60) * rates[0]
    elif elapsed_minutes <= 180:
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    else:
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    per_paying = total_bill / paying_people if paying_people > 0 else 0
    return total_bill, per_paying

# --- ממשק האפליקציה ---

st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 מרכז בקרה - קריוקי")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון ידני"])

with tab1:
    if st.button("🔄 סנכרן מהאתר"):
        today = datetime.now().strftime("%Y-%m-%d")
        
        # שימוש ברשימה כדי לאפשר מפתחות כפולים עבור התאריך
        params = [
            ("select", "*,room:rooms(*)"),
            ("booking_date", f"gte.{today}"),
            ("booking_date", f"lte.{today}"),
            ("status", "neq.cancelled"), # מביא הכל חוץ ממה שבוטל
            ("order", "start_time.asc")
        ]
        
        try:
            res = requests.get(URL, headers=HEADERS, params=params)
            if res.status_code == 200:
                st.session_state.web_bookings = res.json()
                if len(st.session_state.web_bookings) == 0:
                    st.warning(f"המערכת מחוברת, אך לא נמצאו הזמנות לתאריך {today}")
                else:
                    st.success(f"נמצאו {len(st.session_state.web_bookings)} הזמנות להיום!")
            else:
                st.error(f"שגיאה {res.status_code}. ייתכן והאתר דורש התחברות מחדש.")
        except Exception as e:
            st.error(f"שגיאה בתקשורת: {e}")

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            name = b.get('customer_name', 'לקוח')
            time_str = b.get('start_time', '--:--')
            with st.expander(f"{name} | {time_str}"):
                p_count = st.number_input("כמות אנשים", 1, 50, 2, key=f"p_{b['id']}")
                duration = st.number_input("זמן מוזמן (דקות)", 15, 300, 60, key=f"d_{b['id']}")
                if st.button("🚀 כניסה (צ'ק-אין)", key=f"btn_{b['id']}"):
                    if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
                    st.session_state.rooms_active[b['id']] = {
                        "name": name,
                        "start": datetime.now(),
                        "total_people": p_count,
                        "paying_people": p_count,
                        "booked_duration": duration
                    }
                    send_telegram(f"✅ {name} נכנסו. הודעת סיום תישלח בעוד {duration} דקות.")
                    schedule_msg(f"⏰ זמן נגמר ל-{name}! (חלפו {duration} דקות)", duration)
                    st.rerun()

with tab2:
    if 'rooms_active' in st.session_state and st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            elapsed = (datetime.now() - data['start']).total_seconds() // 60
            st.subheader(f"בחדר: {data['name']}")
            
            data['paying_people'] = st.number_input("כמה משלמים בפועל?", 1, 50, data['paying_people'], key=f"pay_{rid}")
            total_bill, per_person = calculate_price_logic(data['total_people'], data['paying_people'], elapsed)
            
            c1, c2 = st.columns(2)
            c1.metric("סה\"כ לתשלום", f"₪{total_bill:.2f}")
            c2.metric("לאדם משלם", f"₪{per_person:.2f}")
            st.write(f"⏱️ זמן בחדר: {int(elapsed)} דקות")
            
            if st.button("💰 סיום ותשלום", key=f"end_{rid}", use_container_width=True):
                send_telegram(f"💸 סשן הסתיים: {data['name']}. נגבה סה\"כ: ₪{total_bill:.2f}")
                del st.session_state.rooms_active[rid]
                st.rerun()
            st.divider()
    else:
        st.info("אין חדרים בפעילות.")

with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_total = st.number_input("סה\"כ אנשים (לתעריף)", 1, 50, 4)
    calc_paying = st.number_input("כמה משלמים?", 1, 50, 4)
    calc_minutes = st.number_input("כמה דקות?", 1, 600, 60)
    
    total_res, per_res = calculate_price_logic(calc_total, calc_paying, calc_minutes)
    st.divider()
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("סה\"כ לכולם", f"₪{total_res:.2f}")
    res_c2.metric("מחיר לאדם", f"₪{per_res:.2f}")
