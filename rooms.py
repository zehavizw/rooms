import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- הגדרות חיבור ---
SOURCE_URL = st.secrets['SUPABASE_URL']
SOURCE_KEY = st.secrets['SUPABASE_KEY']
MY_URL = st.secrets['MY_URL']
MY_KEY = st.secrets['MY_KEY']
R_TOKEN = st.secrets.get('REFRESH_TOKEN', '')
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_duration(total_seconds):
    """הופכת שניות למחרוזת של שעות, דקות ושניות בסוגריים"""
    total_seconds = int(max(0, total_seconds))
    total_mins = total_seconds // 60
    seconds = total_seconds % 60
    time_str = f"{total_mins:02d}:{seconds:02d}"
    if total_mins >= 60:
        h, m = divmod(total_mins, 60)
        return f"{time_str} ({h} שעה, {m} דק', {seconds} ש') "
    return f"{time_str} ({total_mins} דק', {seconds} ש')"

# --- פונקציות ליבה עם הגנה מ-401 ---
def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        res = requests.post(auth_url, json={"refresh_token": R_TOKEN}, headers={"apikey": SOURCE_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}
    except: pass
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
    now = get_now()
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") if (selected_date == now.date() and now.hour < 6) else selected_date.strftime("%Y-%m-%d")
    
    headers = get_source_headers()
    # מושך 50 אחרונים כדי למנוע פספוסים
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=headers, params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"}, timeout=10)
    
    if res.status_code != 200:
        st.error(f"שגיאה {res.status_code} - נסי לרענן.")
        return []
    
    source_bookings = res.json()
    # ניקוי נתונים ישנים מהמסד שלך
    my_res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
    if my_res.status_code == 200:
        ids = [str(b['id']) for b in source_bookings]
        for r in my_res.json():
            if str(r['booking_id']) not in ids and r.get('status', 'active') == 'active':
                requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", headers=get_my_headers())
    return source_bookings

def get_shift_date(iso):
    if not iso: return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(IL_TZ)
        return (dt - timedelta(days=1)).date() if dt.hour < 6 else dt.date()
    except: return None

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זיכרון קבוע")

selected_date = st.date_input("📅 בחר תאריך", get_now().date())
if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.web_bookings = sync_and_cleanup(selected_date)
    st.success("הסנכרון הושלם!")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state:
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in a_ids: continue
            
            # משיכת נתונים מקוריים
            orig_p = b.get('total_people') or 2
            orig_d = b.get('duration_minutes') or 60
            name = b.get('customer_name') or 'לקוח'
            
            with st.expander(f"⏳ {name} | {b.get('start_time')} | {b.get('room',{}).get('name')}"):
                p = st.number_input("אנשים", 1, 50, int(orig_p), key=f"p_{bid}")
                d = st.number_input("דקות", 15, 300, int(orig_d), key=f"d_{bid}")
                r_act = st.text_input("חדר", value=b.get('room',{}).get('name'), key=f"r_{bid}")
                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    requests.post(f"{MY_URL}/rest/v1/active_sessions", json={"booking_id":bid,"name":name,"room_name":r_act,"start_time":get_now().isoformat(),"total_people":p,"paying_people":p,"planned_duration":d,"status":"active"}, headers=get_my_headers())
                    send_telegram(f"✅ כניסה: {name} ל-{r_act} ({p} איש)")
                    st.rerun()

with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True, key="v_mode_main")
    @st.fragment(run_every=5)
    def timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = [r for r in res.json() if get_shift_date(r['start_time']) == selected_date]
            disp = [r for r in rooms if r.get('status','active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                diff = (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt) if r.get('status') == 'finished' else (get_now() - s_dt)
                
                duration_display = format_duration(diff.total_seconds())
                st.subheader(f"📍 {r['room_name']} | {r['name']}")
                
                if r.get('status').startswith('active'):
                    pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                    total, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("⏱️ זמן", duration_display)
                    c2.metric("💰 סה\"כ", f"₪{total:.2f}")
                    c3.metric("👤 לאדם", f"₪{per:.2f}")
                    if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                        send_telegram(f"💸 סיום: {r['name']} נגבה ₪{total:.2f}")
                        st.rerun()
                else:
                    st.success(f"הסתיים. זמן: {duration_display}")
                st.divider()
    timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("איש", 1, 50, 4, key="c_t"), c2.number_input("משלמים", 1, 50, 4, key="c_p"), c3.number_input("דקות", 1, 600, 60, key="c_m")
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
