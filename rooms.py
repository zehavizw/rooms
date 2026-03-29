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

def cleanup_deleted_bookings(current_source_list):
    """מנגנון הניקוי: משווה ID ומנקה את מה שנמחק מהמקור"""
    current_ids = {str(b['id']) for b in current_source_list}
    
    # ניקוי חדרים פעילים
    active_keys = list(st.session_state.rooms_active.keys())
    for rid in active_keys:
        if rid not in current_ids:
            name = st.session_state.rooms_active[rid].get('name', 'לקוח')
            del st.session_state.rooms_active[rid]
            send_telegram(f"🗑️ ההזמנה של {name} נמחקה מהאתר המקורי והוסרה מהחדרים הפעילים.")
            
    # ניקוי הזמנות שהסתיימו
    finished_keys = list(st.session_state.finished_bookings.keys())
    for rid in finished_keys:
        if rid not in current_ids:
            del st.session_state.finished_bookings[rid]

# --- אתחול משתני מערכת ---
if 'rooms_active' not in st.session_state: st.session_state.rooms_active = {}
if 'finished_bookings' not in st.session_state: st.session_state.finished_bookings = {}
if 'notified_entries' not in st.session_state: st.session_state.notified_entries = set()

# --- ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 מרכז ניהול חכם - קריוקי")

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
        if st.button("🔄 סנכרן"):
            token = get_fresh_token()
            if token:
                today = datetime.now().strftime("%Y-%m-%d")
                headers = {"apikey": st.secrets["SUPABASE_KEY"], "Authorization": f"Bearer {token}"}
                params = [("select", "*,room:rooms(*)"), ("booking_date", f"eq.{today}"), ("status", "neq.cancelled")]
                res = requests.get(BOOKINGS_URL, headers=headers, params=params)
                if res.status_code == 200:
                    raw_list = res.json()
                    # מניעת כפילויות ועדכון רשימה
                    unique_list = list({b['id']: b for b in raw_list}.values())
                    st.session_state.web_bookings = unique_list
                    
                    # הפעלת ניקוי אוטומטי להזמנות שנמחקו
                    cleanup_deleted_bookings(raw_list)
                    
                    st.success("סונכרן ובוצע ניקוי להזמנות שנמחקו!")

    filter_choice = st.radio("הצג:", ["הכל", "טרם הופעלו", "בפעילות", "הסתיימו"], horizontal=True)

    if 'web_bookings' in st.session_state:
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            name = b.get('customer_name', 'לקוח')
            sched_time = b.get('start_time', '--:--')
            room_name = b.get('room', {}).get('name', 'חדר לא הוקצה')
            
            is_active = bid in st.session_state.rooms_active
            is_finished = bid in st.session_state.finished_bookings
            
            if filter_choice == "טרם הופעלו" and (is_active or is_finished): continue
            if filter_choice == "בפעילות" and not is_active: continue
            if filter_choice == "הסתיימו" and not is_finished: continue

            icon = "🏁" if is_finished else ("🔵" if is_active else "⏳")
            with st.expander(f"{icon} {name} | {sched_time} | {room_name}"):
                if is_finished:
                    st.write(f"✅ הסתיים בחדר {st.session_state.finished_bookings[bid].get('room_name')}")
                    c1, c2 = st.columns(2)
                    if c1.button("🔄 מחדש", key=f"re_{bid}"): del st.session_state.finished_bookings[bid]; st.rerun()
                    if c2.button("➕ המשך", key=f"co_{bid}"): st.session_state.rooms_active[bid] = st.session_state.finished_bookings[bid]; del st.session_state.finished_bookings[bid]; st.rerun()
                elif is_active:
                    st.info(f"בפעילות בחדר {st.session_state.rooms_active[bid].get('room_name')}")
                else:
                    col_p, col_d = st.columns(2)
                    p = col_p.number_input("אנשים", 1, 50, 2, key=f"p_{bid}")
                    d = col_d.number_input("דקות", 15, 300, 60, key=f"d_{bid}")
                    actual_r = st.text_input("חדר בפועל", value=room_name, key=f"r_edit_{bid}")
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        st.session_state.rooms_active[bid] = {
                            "name": name, "room_name": actual_r, "start": datetime.now(),
                            "total_people": p, "paying_people": p, "planned_duration": d
                        }
                        send_telegram(f"✅ {name} נכנסו ל-{actual_r}."); st.rerun()

# --- מקטע טיימר עצמאי (Fragment) ---
@st.fragment(run_every=5)
def active_rooms_timer():
    if st.session_state.rooms_active:
        for rid, data in list(st.session_state.rooms_active.items()):
            diff = datetime.now() - data['start']
            elapsed = diff.total_seconds() / 60
            mins, secs = divmod(int(diff.total_seconds()), 60)
            
            if elapsed >= data.get('planned_duration', 60) and f"out_{rid}" not in st.session_state.notified_entries:
                send_telegram(f"⏰ זמן נגמר ל-{data['name']}!")
                st.session_state.notified_entries.add(f"out_{rid}")

            st.subheader(f"📍 {data.get('room_name')} | {data['name']}")
            data['paying_people'] = st.number_input("משלמים", 1, 50, data['paying_people'], key=f"pay_{rid}")
            total, per_p = calculate_price_logic(data['total_people'], data['paying_people'], elapsed)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("⏱️ זמן", f"{mins:02d}:{secs:02d}")
            c2.metric("💰 סה\"כ", f"₪{total:.2f}")
            c3.metric("👤 לאדם", f"₪{per_p:.2f}")
            
            if st.button(f"💰 סיום ל-{data['name']}", key=f"end_{rid}"):
                send_telegram(f"💸 {data['name']} סיימו. נגבה ₪{total:.2f}")
                st.session_state.finished_bookings[rid] = data
                del st.session_state.rooms_active[rid]
                st.rerun()
            st.divider()
    else:
        st.info("אין חדרים פעילים.")

with tab2:
    active_rooms_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    calc_name = st.text_input("שם הלקוח", "כללי")
    c1, c2, c3 = st.columns(3)
    c_tot = c1.number_input("סה\"כ איש", 1, 50, 4)
    c_pay = c2.number_input("משלמים", 1, 50, 4)
    c_min = c3.number_input("דקות", 1, 600, 60)
    t_res, p_res = calculate_price_logic(c_tot, c_pay, c_min)
    st.divider()
    st.metric("סה\"כ", f"₪{t_res:.2f}"); st.metric("לאדם", f"₪{p_res:.2f}")
    if st.button("📤 שלח לטלגרם"):
        send_telegram(f"📝 בדיקה ל-{calc_name}: {c_min} דק', {c_tot} איש. סה\"כ: ₪{t_res:.2f}"); st.success("נשלח!")
