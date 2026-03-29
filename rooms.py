import streamlit as st
import requests
from datetime import datetime
import time
import threading

# הגדרות בסיס
URL = f"{st.secrets['SUPABASE_URL']}/rest/v1/bookings"
AUTH_URL = f"{st.secrets['SUPABASE_URL']}/auth/v1/token?grant_type=refresh_token"

# --- פונקציות חכמות ---

def get_fresh_token():
    """פונקציה שמשתמשת ב-Refresh Token כדי לקבל Access Token טרי"""
    payload = {"refresh_token": st.secrets["REFRESH_TOKEN"]}
    headers = {"apikey": st.secrets["SUPABASE_KEY"], "Content-Type": "application/json"}
    try:
        res = requests.post(AUTH_URL, json=payload, headers=headers)
        if res.status_code == 200:
            return res.json().get("access_token")
    except:
        return None
    return None

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
    if total_people == 1: rates = [50, 40, 30]
    elif 2 <= total_people <= 4: rates = [45, 35, 25]
    elif 5 <= total_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]

    # לוגיקת המחיר שלך: חלק משעה נחשב כמו השעה שלפני
    if elapsed_minutes <= 120:
        price_per_person = (elapsed_minutes / 60) * rates[0]
    elif elapsed_minutes <= 180:
        price_per_person = (120/60 * rates[0]) + ((elapsed_minutes - 120) / 60 * rates[1])
    else:
        price_per_person = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_minutes - 180) / 60 * rates[2])
    
    total_bill = price_per_person * total_people
    per_paying = total_bill / paying_people if paying_people > 0 else 0
    return total_bill, per_paying

# --- ממשק המשתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 מרכז בקרה חכם - קריוקי")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון ידני"])

with tab1:
    if st.button("🔄 סנכרן מהאתר (אוטומטי)"):
        token = get_fresh_token()
        if not token:
            st.error("לא הצלחתי לחדש את המפתח. ודאי שה-Refresh Token ב-Secrets נכון.")
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            headers = {
                "apikey": st.secrets["SUPABASE_KEY"],
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            params = [
                ("select", "*,room:rooms(*)"),
                ("booking_date", f"gte.{today}"),
                ("booking_date", f"lte.{today}"),
                ("status", "neq.cancelled"),
                ("order", "start_time.asc")
            ]
            try:
                res = requests.get(URL, headers=headers, params=params)
                if res.status_code == 200:
                    st.session_state.web_bookings = res.json()
                    st.success(f"סנכרון הצליח! נמצאו {len(st.session_state.web_bookings)} הזמנות להיום.")
                else:
                    st.error(f"שגיאה {res.status_code} במשיכת נתונים.")
            except Exception as e:
                st.error(f"שגיאה בתקשורת: {e}")

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            name = b.get('customer_name', 'לקוח')
            time_str = b.get('start_time', '--:--')
            with st.expander(f"{name} | {time_str}"):
                p_count = st.number_input("כמות אנשים", 1, 50, 2, key=f"p_{b['id']}")
                duration = st.number_input("דקות מוזמנות", 15, 300, 60, key=f"d_{b['id']}")
                if st.button("🚀 כניסה (צ'ק-אין)", key=f"btn_{b['id']}"):
                    if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
                    st.session_state.rooms_active[b['id']] = {
                        "name": name, "start": datetime.now(),
                        "total_people": p_count, "paying_people": p_count,
                        "booked_duration": duration
                    }
                    send_telegram(f"✅ {name} נכנסו. הודעת סיום תישלח בעוד {duration} דקות.")
                    schedule_msg(f"⏰ זמן נגמר ל-{name}! (חלפו {duration} דקות)", duration)
                    st.rerun()

with tab2:
    if 'rooms_active' in st.session_state and st.session_state.rooms_active:
        # יצירת מקום ריק בתוך הלשונית שיתעדכן בלייב
        placeholder = st.empty()
        
        # לולאה שרצה ומעדכנת את השעון והמחיר
        while len(st.session_state.rooms_active) > 0:
            with placeholder.container():
                for rid, data in list(st.session_state.rooms_active.items()):
                    # חישוב הזמן שעבר בשניות ודקות
                    now = datetime.now()
                    diff = now - data['start']
                    total_seconds = int(diff.total_seconds())
                    elapsed_minutes = total_seconds / 60
                    
                    # הצגת הזמן בפורמט של שעון (דקות:שניות)
                    mins, secs = divmod(total_seconds, 60)
                    time_display = f"{mins:02d}:{secs:02d}"
                    
                    st.subheader(f"בחדר: {data['name']}")
                    
                    # חישוב המחיר המעודכן לשנייה זו
                    total_bill, per_person = calculate_price_logic(
                        data['total_people'], 
                        data['paying_people'], 
                        elapsed_minutes
                    )
                    
                    # תצוגה של השעון והמחיר שרצים
                    c1, c2, c3 = st.columns(3)
                    c1.metric("⏱️ זמן בחדר", time_display)
                    c2.metric("💰 סה\"כ", f"₪{total_bill:.2f}")
                    c3.metric("👤 לאדם", f"₪{per_person:.2f}")
                    
                    if st.button("💰 סיום ותשלום", key=f"end_{rid}_{total_seconds}"):
                        send_telegram(f"💸 {data['name']} סיימו. סה\"כ נגבה: ₪{total_bill:.2f}")
                        del st.session_state.rooms_active[rid]
                        st.rerun()
                    st.divider()
                
                # המתנה של שנייה אחת לפני העדכון הבא
                time.sleep(1)
                # פקודה שגורמת ל-Streamlit לרענן רק את הלולאה הזו
                if len(st.session_state.rooms_active) > 0:
                    continue
    else:
        st.info("אין חדרים פעילים. כנסי ללוח ההזמנות כדי להתחיל.")
 
with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    c_t = st.number_input("סה\"כ אנשים (לתעריף)", 1, 50, 4, key="calc_t")
    c_p = st.number_input("כמה משלמים?", 1, 50, 4, key="calc_p")
    c_m = st.number_input("כמה דקות?", 1, 600, 60, key="calc_m")
    res_t, res_p = calculate_price_logic(c_t, c_p, c_m)
    st.divider()
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("סה\"כ לכולם", f"₪{res_t:.2f}")
    res_c2.metric("מחיר לאדם", f"₪{res_p:.2f}")
