import streamlit as st
import requests
from datetime import datetime
import time

# --- הגדרות חיבור ---
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

# --- אתחול משתני מערכת ---
if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
if 'finished_bookings' not in st.session_state: st.session_state.finished_bookings = {}
if 'notified_entries' not in st.session_state: st.session_state.notified_entries = set()

# --- ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - קריוקי")

with st.sidebar:
    st.header("כלי מערכת")
    if st.button("🗑️ איפוס זיכרון מלא"):
        st.session_state.rooms_active = {}
        st.session_state.finished_bookings = {}
        st.session_state.notified_entries = set()
        st.rerun()

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    col_sync, col_filter = st.columns([1, 2])
    with col_sync:
        if st.button("🔄 סנכרן מהאתר"):
            token = get_fresh_token()
            if token:
                today = datetime.now().strftime("%Y-%m-%d")
                headers = {"apikey": st.secrets["SUPABASE_KEY"], "Authorization": f"Bearer {token}"}
                params = [("select", "*,room:rooms(*)"), ("booking_date", f"eq.{today}"), ("status", "neq.cancelled")]
                res = requests.get(BOOKINGS_URL, headers=headers, params=params)
                if res.status_code == 200:
                    st.session_state.web_bookings = res.json()
                    st.success("עודכן!")

    filter_choice = st.radio("הצג הזמנות:", ["הכל", "טרם הופעלו", "בפעילות", "הסתיימו"], horizontal=True)

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            name = b.get('customer_name', 'לקוח')
            bid = str(b['id'])
            # שליפת החדר המקורי מההזמנה
            scheduled_room = b.get('room', {}).get('name', 'לא הוקצה')
            
            is_active = bid in st.session_state.rooms_active
            is_finished = bid in st.session_state.finished_bookings
            
            if filter_choice == "טרם הופעלו" and (is_active or is_finished): continue
            if filter_choice == "בפעילות" and not is_active: continue
            if filter_choice == "הסתיימו" and not is_finished: continue

            status_icon = "🏁" if is_finished else ("🔵" if is_active else "⏳")
            
            with st.expander(f"{status_icon} {name} | {b.get('start_time')} | {scheduled_room}"):
                if is_finished:
                    st.write(f"✅ האירוח בחדר **{st.session_state.finished_bookings[bid].get('room_name')}** הסתיים.")
                    c1, c2 = st.columns(2)
                    if c1.button("🔄 מחדש", key=f"re_{bid}"): del st.session_state.finished_bookings[bid]; st.rerun()
                    if c2.button("➕ המשך", key=f"co_{bid}"): st.session_state.rooms_active[bid] = st.session_state.finished_bookings[bid]; del st.session_state.finished_bookings[bid]; st.rerun()
                elif is_active: 
                    st.info(f"הקבוצה נמצאת כרגע בחדר: **{st.session_state.rooms_active[bid].get('room_name')}**")
                else:
                    col_p, col_d = st.columns(2)
                    p = col_p.number_input("אנשים", 1, 50, 2, key=f"p_{bid}")
                    d = col_d.number_input("זמן (דקות)", 15, 300, 60, key=f"d_{bid}")
                    
                    # התיקון החדש: אפשרות לערוך את החדר בכניסה
                    actual_room = st.text_input("לאיזה חדר הם נכנסים?", value=scheduled_room, key=f"room_edit_{bid}")
                    
                    if st.button("🚀 כניסה (צ'ק-אין)", key=f"in_{bid}", use_container_width=True):
                        st.session_state.rooms_active[bid] = {
                            "name": name, 
                            "room_name": actual_room, # שמירת החדר שנבחר בפועל
                            "start": datetime.now(), 
                            "total_people": p, 
                            "paying_people": p, 
                            "planned_duration": d
                        }
                        send_telegram(f"✅ {name} נכנסו לחדר **{actual_room}**.\nזמן מתוכנן: {d} דקות."); st.rerun()

with tab2:
    if st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            if 'start' not in data: continue
            diff = datetime.now() - data['start']
            elapsed_min = diff.total_seconds() / 60
            mins, secs = divmod(int(diff.total_seconds()), 60)
            
            st.subheader(f"📍 חדר: {data.get('room_name', 'לא ידוע')} | לקוח: {data['name']}")
            
            data['paying_people'] = st.number_input("משלמים בפועל", 1, 50, data['paying_people'], key=f"pay_{rid}")
            total_p, per_p = calculate_price_logic(data['total_people'], data['paying_people'], elapsed_min)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("⏱️ זמן", f"{mins:02d}:{secs:02d}")
            c2.metric("💰 סה\"כ", f"₪{total_p:.2f}")
            c3.metric("👤 לאדם", f"₪{per_p:.2f}")
            
            if st.button(f"💰 סיום ותשלום ל{data['name']}", key=f"end_{rid}"):
                send_telegram(f"💸 {data['name']} סיימו בחדר **{data.get('room_name')}**.\nנגבה סה\"כ: ₪{total_p:.2f}")
                st.session_state.finished_bookings[rid] = data; del st.session_state.rooms_active[rid]; st.rerun()
            st.divider()
        time.sleep(5); st.rerun()
    else: st.info("אין חדרים פעילים.")

with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    calc_name = st.text_input("שם הלקוח לבדיקה", "לקוח כללי")
    c_col1, c_col2, c_col3 = st.columns(3)
    calc_total = c_col1.number_input("סה\"כ אנשים בחדר", 1, 50, 4)
    calc_paying = c_col2.number_input("כמה משלמים?", 1, 50, 4)
    calc_minutes = c_col3.number_input("כמה דקות?", 1, 600, 60)
    total_res, per_res = calculate_price_logic(calc_total, calc_paying, calc_minutes)
    st.divider()
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("סה\"כ לכולם", f"₪{total_res:.2f}")
    res_c2.metric("מחיר לאדם", f"₪{per_res:.2f}")
    if st.button("📤 שלח תוצאת בדיקה לטלגרם", use_container_width=True):
        msg = f"📝 **בדיקת מחירון עבור: {calc_name}**\n⏰ זמן: {calc_minutes} דקות\n👥 סה\"כ בחדר: {calc_total} אנשים\n💰 סה\"כ לתשלום: ₪{total_res:.2f}\n👤 מחיר לאדם משלם ({calc_paying} איש): ₪{per_res:.2f}"
        send_telegram(msg); st.success(f"נשלח לטלגרם!")
