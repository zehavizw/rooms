import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- הגדרות חיבור ---
SOURCE_URL = st.secrets.get('SOURCE_URL') or st.secrets.get('SUPABASE_URL')
SOURCE_KEY = st.secrets.get('SOURCE_KEY') or st.secrets.get('SUPABASE_KEY')
MY_URL = st.secrets.get('MY_URL')
MY_KEY = st.secrets.get('MY_KEY')
REFRESH_TOKEN = st.secrets.get('REFRESH_TOKEN', '')

IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_simple_clock(total_seconds):
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"## **{hours:02d}:{minutes:02d}:{seconds:02d}**"

def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        res = requests.post(auth_url, json={"refresh_token": REFRESH_TOKEN}, headers={"apikey": SOURCE_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}
    except:
        pass
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {SOURCE_KEY}"}

def get_my_headers():
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=5)
        except: pass

def calculate_price_logic(total_p, paying_p, elapsed_m):
    if total_p == 1: rates = [50, 40, 30]
    elif 2 <= total_p <= 4: rates = [45, 35, 25]
    elif 5 <= total_p <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]
    if elapsed_m <= 120: p = (elapsed_m / 60) * rates[0]
    elif elapsed_m <= 180: p = (120/60 * rates[0]) + ((elapsed_m - 120) / 60 * rates[1])
    else: p = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_m - 180) / 60 * rates[2])
    total = p * total_p
    per = total / paying_p if paying_p > 0 else 0
    return total, per

def sync_and_cleanup(selected_date):
    q_date = selected_date.strftime("%Y-%m-%d")
    st.info(f"מבצע חיפוש לתאריך: {q_date}") # הודעת בדיקה
    
    headers = get_source_headers()
    # חיפוש רחב יותר (מסיר חלק מהפילטרים כדי לראות אם משהו מגיע)
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=headers, 
                       params={"booking_date": f"eq.{q_date}", "select": "*,room:rooms(*)"}, timeout=10)
    
    if res.status_code != 200:
        st.error(f"שגיאה: {res.status_code}")
        return []
        
    all_bookings = res.json()
    # סינון ידני של המבוטלים באפליקציה במקום ב-Database כדי למנוע טעויות
    active_bookings = [b for b in all_bookings if b.get('status') != 'cancelled']
    
    # ניקוי חדרים שבוטלו ב-Database הפרטי שלך
    my_res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers(), timeout=10)
    if my_res.status_code == 200:
        source_ids = [str(b['id']) for b in active_bookings]
        for r in my_res.json():
            if str(r['booking_id']) not in source_ids and r.get('status', 'active').startswith('active'):
                requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", headers=get_my_headers())
                
    return active_bookings

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

# תפריט צד לאיפוס
with st.sidebar:
    if st.button("🗑️ רענון עמוק (איפוס)"):
        st.session_state.clear()
        st.rerun()

# בחירת תאריך
selected_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    with st.spinner("מושך נתונים..."):
        st.session_state.web_bookings = sync_and_cleanup(selected_date)
        if st.session_state.web_bookings:
            st.success(f"נמצאו {len(st.session_state.web_bookings)} הזמנות!")
        else:
            st.warning("לא נמצאו הזמנות. נסי לבדוק את התאריך או לבצע 'רענון עמוק' מהתפריט בצד.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ עכשיו בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state and st.session_state.web_bookings:
        # בדיקה מי כבר בפעילות
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in active_ids: continue
            
            name = b.get('customer_name', 'לקוח')
            start = b.get('start_time', '--:--')
            dur = b.get('duration_minutes') or 60
            people = b.get('total_people') or 2
            
            with st.expander(f"⏳ {name} | {start} ({dur} דק')"):
                p = st.number_input("אנשים", 1, 50, int(people), key=f"p_{bid}")
                d = st.number_input("דקות", 15, 300, int(dur), key=f"d_{bid}")
                r_name = b.get('room', {}).get('name', 'לא הוקצה')
                r_act = st.text_input("חדר", value=r_name, key=f"r_{bid}")
                
                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    payload = {
                        "booking_id": bid, "name": name, "room_name": r_act,
                        "start_time": get_now().isoformat(), "total_people": p,
                        "paying_people": p, "planned_duration": d, "status": "active"
                    }
                    res = requests.post(f"{MY_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                    if res.status_code in [200, 201]:
                        send_telegram(f"✅ כניסה: {name} ל-{r_act}")
                        st.rerun()
    else:
        st.info("לוח הזמנות ריק. לחצי על סנכרן.")

with tab2:
    v = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True)
    @st.fragment(run_every=5)
    def active_timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = res.json()
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                # מציג רק מה ששייך ליום שנבחר
                if s_dt.date() == selected_date:
                    diff = get_now() - s_dt if r.get('status') != 'finished' else (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt)
                    st.subheader(f"📍 {r['room_name']} | {r['name']}")
                    if r.get('status').startswith('active'):
                        pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                        total, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            st.write(format_simple_clock(diff.total_seconds()))
                        c2.metric("💰 סה\"כ", f"₪{total:.2f}")
                        c3.metric("👤 לאדם", f"₪{per:.2f}")
                        if st.button(f"💰 סיום", key=f"e_{r['id']}", use_container_width=True):
                            requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                            st.rerun()
                    st.divider()
    active_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("סה\"כ", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("דקות", 1, 600, 60)
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    st.metric("לאדם", f"₪{p:.2f}")
