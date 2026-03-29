import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- 1. הגדרות וחיבורים ---
S_URL = st.secrets['SUPABASE_URL']
S_KEY = st.secrets['SUPABASE_KEY']
M_URL = st.secrets['MY_URL']
M_KEY = st.secrets['MY_KEY']
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_duration(total_seconds):
    """הופכת שניות למחרוזת ברורה של דקות ושניות"""
    total_seconds = int(max(0, total_seconds))
    mins, secs = divmod(total_seconds, 60)
    time_str = f"{mins:02d}:{secs:02d}"
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{time_str} ({h} שעה, {m} דק', {secs} ש')"
    return f"{time_str} ({mins} דק', {secs} ש')"

# --- 2. פונקציות ליבה (ללא REFRESH_TOKEN הבעייתי) ---
def get_source_headers():
    # משתמשים ישירות במפתח הראשי שעבר את הבדיקה בהצלחה
    return {"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}

def get_my_headers():
    return {"apikey": M_KEY, "Authorization": f"Bearer {M_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

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
    now = get_now()
    # חישוב תאריך משמרת (לפני 6 בבוקר נחשב אתמול)
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") if (selected_date == now.date() and now.hour < 6) else selected_date.strftime("%Y-%m-%d")
    
    headers = get_source_headers()
    # משיכת הזמנות מהמקור
    res = requests.get(f"{S_URL}/rest/v1/bookings", headers=headers, 
                       params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"}, timeout=10)
    
    if res.status_code != 200:
        st.error(f"שגיאה במשיכת נתונים: {res.status_code}")
        return []
    
    return res.json()

def get_shift_date(iso):
    if not iso: return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(IL_TZ)
        return (dt - timedelta(days=1)).date() if dt.hour < 6 else dt.date()
    except: return None

# --- 3. ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

with st.sidebar:
    if st.button("🗑️ איפוס אפליקציה"):
        st.session_state.clear()
        st.rerun()

view_date = st.date_input("📅 בחר תאריך להצגה", get_now().date())

if st.button("🔄 סנכרן נתונים עכשיו", use_container_width=True):
    with st.spinner("מעדכן רשימת הזמנות..."):
        st.session_state.web_bookings = sync_and_cleanup(view_date)
        if st.session_state.web_bookings:
            st.success(f"נמצאו {len(st.session_state.web_bookings)} הזמנות!")
        else:
            st.warning("לא נמצאו הזמנות לתאריך שנבחר.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state:
        # בדיקה מי כבר נכנס
        res_a = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
        active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in active_ids: continue
            
            name = b.get('customer_name') or 'לקוח'
            # משיכת נתונים מקוריים מההזמנה
            p_orig = b.get('total_people') or 2
            d_orig = b.get('duration_minutes') or 60
            
            with st.expander(f"⏳ {name} | {b.get('start_time')} | {b.get('room',{}).get('name')}"):
                p_in = st.number_input("אנשים", 1, 50, int(p_orig), key=f"p_{bid}")
                d_in = st.number_input("דקות", 15, 300, int(d_orig), key=f"d_{bid}")
                r_name = b.get('room', {}).get('name') or 'חדר'
                
                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    payload = {"booking_id": bid, "name": name, "room_name": r_name, "start_time": get_now().isoformat(), "total_people": p_in, "paying_people": p_in, "planned_duration": d_in, "status": "active"}
                    requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                    send_telegram(f"✅ כניסה: {name} ל-{r_name}")
                    st.rerun()
    else:
        st.info("לחצי על כפתור הסנכרון כדי לראות הזמנות.")

with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True, key="v_mode_final")
    
    @st.fragment(run_every=5)
    def active_timer():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = [r for r in res.json() if get_shift_date(r['start_time']) == view_date]
            disp = [r for r in rooms if r.get('status','active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                diff = (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt) if r.get('status') == 'finished' else (get_now() - s_dt)
                
                st.subheader(f"📍 {r['room_name']} | {r['name']}")
                if r.get('status').startswith('active'):
                    pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                    tot, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.write(f"⏱️ **{format_duration(diff.total_seconds())}**")
                    c2.metric("💰 סה\"כ", f"₪{tot:.2f}")
                    c3.metric("👤 לאדם", f"₪{per:.2f}")
                    if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                        st.rerun()
                else:
                    st.success(f"סיימו. זמן: {format_duration(diff.total_seconds())}")
                st.divider()
    active_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("אנשים", 1, 50, 4, key="c_tot"), c2.number_input("משלמים", 1, 50, 4, key="c_pay"), c3.number_input("דקות", 1, 600, 60, key="c_min")
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ לתשלום", f"₪{t:.2f}")
    st.metric("מחיר לאדם", f"₪{p:.2f}")
