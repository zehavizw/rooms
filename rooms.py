import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- 1. הגדרות וחיבורים ---
S_URL = st.secrets.get('SUPABASE_URL')
S_KEY = st.secrets.get('SUPABASE_KEY')
M_URL = st.secrets.get('MY_URL')
M_KEY = st.secrets.get('MY_KEY')
R_TOKEN = st.secrets.get('REFRESH_TOKEN')
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_simple_clock(total_seconds):
    total_seconds = int(max(0, total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"## **{h:02d}:{m:02d}:{s:02d}**"

# --- 2. פונקציות תקשורת ---
def get_source_headers():
    auth_url = f"{S_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        res = requests.post(auth_url, json={"refresh_token": R_TOKEN}, headers={"apikey": S_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": S_KEY, "Authorization": f"Bearer {token}"}
    except: pass
    return {"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}

def get_my_headers():
    return {"apikey": M_KEY, "Authorization": f"Bearer {M_KEY}", "Content-Type": "application/json"}

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

def sync_data():
    headers = get_source_headers()
    # מושך 50 אחרונים כדי למצוא הזמנות גם אם יש הפרשי שעות של חצות
    res = requests.get(f"{S_URL}/rest/v1/bookings?select=*,room:rooms(*)&order=created_at.desc&limit=50", headers=headers, timeout=10)
    if res.status_code != 200:
        st.error(f"שגיאה {res.status_code} בסנכרון. נסי לרענן.")
        return []
    return res.json()

# --- 3. ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

with st.sidebar:
    if st.button("🗑️ איפוס נתונים"):
        st.session_state.clear()
        st.rerun()

view_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים מהענן", use_container_width=True):
    with st.spinner("מושך הזמנות..."):
        st.session_state.raw_data = sync_data()
        if st.session_state.raw_data:
            st.success(f"הסנכרון הצליח! נסרקו 50 פעולות.")
        else:
            st.warning("לא נמצאו נתונים.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'raw_data' in st.session_state:
        # חיפוש תאריך גמיש
        day_bookings = [b for b in st.session_state.raw_data if (b.get('booking_date') or b.get('date') or (b.get('start_time')[:10] if b.get('start_time') else '')) == selected_str]
        
        if day_bookings:
            res_a = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
            active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_bookings:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or b.get('name') or 'לקוח'
                start_raw = b.get('start_time', '--:--')
                start = start_raw.split('T')[1][:5] if 'T' in start_raw else start_raw[:5]
                dur = b.get('duration_minutes') or 60
                
                with st.expander(f"⏳ {name} | {start} ({dur} דק')"):
                    p = st.number_input("אנשים", 1, 50, int(b.get('total_people') or 2), key=f"p_{bid}")
                    d = st.number_input("דקות", 15, 300, int(dur), key=f"d_{bid}")
                    r_name = b.get('room', {}).get('name') or 'חדר'
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        payload = {"booking_id": bid, "name": name, "room_name": r_name, "start_time": get_now().isoformat(), "total_people": p, "paying_people": p, "planned_duration": d, "status": "active"}
                        requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                        send_telegram(f"✅ כניסה: {name} ל-{r_name}")
                        st.rerun()
        else:
            st.info(f"אין הזמנות ל-{selected_str}")
    else:
        st.info("לחצי על סנכרון.")

with tab2:
    v = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True)
    @st.fragment(run_every=5)
    def timer():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = [r for r in res.json() if r.get('status', 'active').startswith('active')] if v == "⚡ פעילים" else [r for r in res.json() if r.get('status') == 'finished']
            for r in rooms:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                if s_dt.date() == view_date:
                    diff = get_now() - s_dt
                    st.subheader(f"📍 {r['room_name']} | {r['name']} (הוזמן ל-{r.get('planned_duration')} דק')")
                    if r.get('status').startswith('active'):
                        pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                        tot, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1: st.write(format_simple_clock(diff.total_seconds()))
                        c2.metric("סה\"כ", f"₪{tot:.2f}")
                        c3.metric("לאדם", f"₪{per:.2f}")
                        if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                            requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                            st.rerun()
                    st.divider()
    timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("אנשים", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("דקות", 1, 600, 60)
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    st.metric("לאדם", f"₪{p:.2f}")
# --- 1. משיכת נתונים מה-Secrets ---
S_URL = st.secrets.get('SUPABASE_URL')
S_KEY = st.secrets.get('SUPABASE_KEY')
M_URL = st.secrets.get('MY_URL')
M_KEY = st.secrets.get('MY_KEY')
R_TOKEN = st.secrets.get('REFRESH_TOKEN')
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_clock(total_seconds):
    total_seconds = int(max(0, total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"## **{h:02d}:{m:02d}:{s:02d}**"

# --- 2. פונקציות ליבה עם תיקון ל-401 ---
def get_source_headers():
    """מנגנון עקיפה חכם לשגיאת 401"""
    auth_url = f"{S_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        # ניסיון ראשון: עם הטוקן הזמני
        res = requests.post(auth_url, json={"refresh_token": R_TOKEN}, headers={"apikey": S_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": S_KEY, "Authorization": f"Bearer {token}"}
    except:
        pass
    # אם נכשל (401) - ננסה להשתמש במפתח הראשי ישירות כגיבוי
    return {"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}

def get_my_headers():
    return {"apikey": M_KEY, "Authorization": f"Bearer {M_KEY}", "Content-Type": "application/json"}

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=5)
        except: pass

def calculate_price(total_p, pay_p, mins):
    if total_p == 1: rates = [50, 40, 30]
    elif 2 <= total_p <= 4: rates = [45, 35, 25]
    elif 5 <= total_p <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]
    if mins <= 120: cost = (mins / 60) * rates[0]
    elif mins <= 180: cost = (120/60 * rates[0]) + ((mins - 120) / 60 * rates[1])
    else: cost = (120/60 * rates[0]) + (60/60 * rates[1]) + ((mins - 180) / 60 * rates[2])
    total = cost * total_p
    per = total / pay_p if pay_p > 0 else 0
    return total, per

def sync_from_source():
    headers = get_source_headers()
    # אנחנו מבקשים את כל ההזמנות בלי שום סינון, כדי לראות אם משהו בכלל עובר
    res = requests.get(f"{S_URL}/rest/v1/bookings?select=*", headers=headers, timeout=10)
    
    if res.status_code != 200:
        # כאן האפליקציה תגיד לנו בדיוק מה הבעיה (Password wrong, Expired, וכו')
        st.error(f"⚠️ שגיאה מהשרת: {res.status_code} - {res.text}")
        return []
        
    data = res.json()
    if not data:
        st.warning("התחברתי בהצלחה, אבל הטבלה במערכת המקורית פשוט ריקה!")
    return data

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

with st.sidebar:
    if st.button("🗑️ איפוס אפליקציה"):
        st.session_state.clear()
        st.rerun()

view_date = st.date_input("📅 הזמנות ליום:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    with st.spinner("מושך נתונים..."):
        st.session_state.raw_data = sync_from_source()
        # ניקוי נתונים ישנים מהמסד שלך (בירוק)
        requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
        st.success("הסנכרון הושלם!")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'raw_data' in st.session_state:
        day_list = [b for b in st.session_state.raw_data if (b.get('booking_date') or b.get('date') or (b.get('start_time')[:10] if b.get('start_time') else '')) == selected_str]
        
        if day_list:
            res_active = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
            active_ids = [str(a['booking_id']) for a in res_active.json()] if res_active.status_code == 200 else []
            
            for b in day_list:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or b.get('name') or 'לקוח'
                start = b.get('start_time', '--:--')
                if 'T' in start: start = start.split('T')[1][:5]
                dur = b.get('duration_minutes') or 60
                people = b.get('total_people') or 2
                
                with st.expander(f"⏳ {name} | {start} ({dur} דק')"):
                    p_in = st.number_input("אנשים", 1, 50, int(people), key=f"p_{bid}")
                    d_in = st.number_input("דקות", 15, 300, int(dur), key=f"d_{bid}")
                    r_name = b.get('room', {}).get('name') or 'חדר'
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        payload = {"booking_id": bid, "name": name, "room_name": r_name, "start_time": get_now().isoformat(), "total_people": p_in, "paying_people": p_in, "planned_duration": d_in, "status": "active"}
                        res_p = requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                        if res_p.status_code in [200, 201]:
                            send_telegram(f"✅ כניסה: {name} ({p_in} איש)")
                            st.rerun()
                        else:
                            st.error(f"שגיאת כניסה: {res_p.text}")
        else:
            st.info(f"אין הזמנות ל-{selected_str}")

with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True)
    @st.fragment(run_every=5)
    def timer_ui():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = res.json()
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                if s_dt.date() != view_date: continue
                
                diff = get_now() - s_dt if r.get('status') != 'finished' else (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt)
                st.subheader(f"📍 {r['room_name']} | {r['name']} (ל-{r['planned_duration']} דק')")
                
                if r.get('status').startswith('active'):
                    pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                    tot, per = calculate_price(r['total_people'], pay, diff.total_seconds()/60)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.write(format_clock(diff.total_seconds()))
                    c2.metric("סה\"כ", f"₪{tot:.2f}")
                    c3.metric("לאדם", f"₪{per:.2f}")
                    if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished", "end_time":get_now().isoformat(), "paying_people":pay}, headers=get_my_headers())
                        st.rerun()
                st.divider()
    timer_ui()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("סה\"כ איש", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("זמן דק'", 1, 600, 60)
    t, p = calculate_price(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    st.metric("לאדם", f"₪{p:.2f}")
