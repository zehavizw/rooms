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
    total_seconds = int(max(0, total_seconds))
    mins, secs = divmod(total_seconds, 60)
    time_str = f"{mins:02d}:{secs:02d}"
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{time_str} ({h} ש', {m} דק')"
    return f"{time_str} ({mins} דק')"

# --- 2. פונקציות ליבה (עוקף חסימות) ---
def get_headers(key):
    # שימוש ב-Bearer token כפול כדי לוודא שהשרת מאשר את הכניסה
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Range": "0-50" # מבטיח שנקבל תוצאות מהירות
    }

def calculate_price_logic(total_p, pay_p, mins):
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

def sync_data():
    """משיכת נתונים אגרסיבית ללא פילטרים בשרת"""
    # ניסיון משיכה פשוט של 50 ההזמנות האחרונות שנוצרו במערכת
    url = f"{S_URL}/rest/v1/bookings?select=*,room:rooms(*)&order=created_at.desc&limit=50"
    res = requests.get(url, headers=get_headers(S_KEY), timeout=10)
    
    if res.status_code != 200:
        st.error(f"⚠️ שגיאת שרת: {res.status_code}. הודעה: {res.text}")
        return []
    
    return res.json()

# --- 3. ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

# תפריט צד לאיפוס
with st.sidebar:
    if st.button("🗑️ נקה זיכרון"):
        st.session_state.clear()
        st.rerun()

view_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים עכשיו", use_container_width=True):
    with st.spinner("סורק את המערכת..."):
        st.session_state.raw_bookings = sync_data()
        if st.session_state.raw_bookings:
            st.success(f"הסנכרון הצליח! נסרקו {len(st.session_state.raw_bookings)} הזמנות.")
        else:
            st.warning("המערכת חזרה ריקה. וודאי שיש הזמנות רשומות במקור.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'raw_bookings' in st.session_state:
        # סינון מקומי בטלפון לפי התאריך שנבחר
        # בודק גם ב-booking_date וגם בתוך ה-start_time ליתר ביטחון
        day_list = []
        for b in st.session_state.raw_bookings:
            b_date = b.get('booking_date') or (b.get('start_time')[:10] if b.get('start_time') else '')
            if b_date == selected_str and b.get('status') != 'cancelled':
                day_list.append(b)
        
        if day_list:
            # בדיקה מי כבר בפעילות
            res_active = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
            active_ids = [str(a['booking_id']) for a in res_active.json()] if res_active.status_code == 200 else []
            
            for b in day_list:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or b.get('name') or 'לקוח'
                start = b.get('start_time', '--:--')
                if 'T' in start: start = start.split('T')[1][:5]
                people = b.get('total_people') or 2
                dur = b.get('duration_minutes') or 60
                
                with st.expander(f"⏳ {name} | {start} ({dur} דק')"):
                    p_in = st.number_input("אנשים", 1, 50, int(people), key=f"p_{bid}")
                    d_in = st.number_input("דקות", 15, 300, int(dur), key=f"d_{bid}")
                    r_name = b.get('room', {}).get('name') or 'חדר'
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        payload = {"booking_id": bid, "name": name, "room_name": r_name, "start_time": get_now().isoformat(), "total_people": p_in, "paying_people": p_in, "planned_duration": d_in, "status": "active"}
                        requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_headers(M_KEY))
                        st.rerun()
        else:
            st.info(f"לא נמצאו הזמנות ליום {selected_str}")
    else:
        st.info("לחצי על סנכרון.")

# טאב 2 ו-3 נשארים כפי שהיו...
with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True, key="v_mode_final")
    @st.fragment(run_every=5)
    def timer_ui():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
        if res.status_code == 200:
            rooms = res.json()
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                if s_dt.date() == view_date:
                    diff = get_now() - s_dt if r.get('status') != 'finished' else (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt)
                    st.subheader(f"📍 {r['room_name']} | {r['name']}")
                    if r.get('status').startswith('active'):
                        pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                        tot, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                        st.write(f"⏱️ **{format_duration(diff.total_seconds())}**")
                        st.write(f"💰 סה\"כ: ₪{tot:.2f} | 👤 לאדם: ₪{per:.2f}")
                        if st.button(f"💰 סיום", key=f"e_{r['id']}", use_container_width=True):
                            requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished", "end_time":get_now().isoformat(), "paying_people":pay}, headers=get_headers(M_KEY))
                            st.rerun()
                    st.divider()
    timer_ui()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("איש", 1, 50, 4, key="c1"), c2.number_input("משלמים", 1, 50, 4, key="c2"), c3.number_input("דקות", 1, 600, 60, key="c3")
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    st.metric("לאדם", f"₪{p:.2f}")
