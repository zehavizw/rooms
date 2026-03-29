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
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{mins:02d}:{secs:02d} ({h} ש', {m} דק')"
    return f"{mins:02d}:{secs:02d} ({mins} דק')"

# --- 2. פונקציות ליבה (חיפוש רחב ללא פילטר תאריך בשרת) ---
def get_headers(url_key):
    return {"apikey": url_key, "Authorization": f"Bearer {url_key}", "Content-Type": "application/json"}

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

def sync_all_recent():
    """מושך את 50 ההזמנות האחרונות בלי לסנן תאריך בשרת - כדי למנוע טעויות שעון"""
    res = requests.get(f"{S_URL}/rest/v1/bookings?select=*,room:rooms(*)&order=created_at.desc&limit=50", 
                       headers=get_headers(S_KEY), timeout=10)
    if res.status_code != 200:
        st.error(f"שגיאת חיבור: {res.status_code}")
        return []
    return res.json()

# --- 3. ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

# בחירת תאריך להצגה
view_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים מהענן", use_container_width=True):
    with st.spinner("סורק את כל ההזמנות האחרונות..."):
        st.session_state.raw_data = sync_all_recent()
        if st.session_state.raw_data:
            st.success("הסנכרון הצליח!")
        else:
            st.warning("לא נמצאו נתונים כלל.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'raw_data' in st.session_state:
        # סינון ידני בתוך האפליקציה לפי התאריך שנבחר
        day_bookings = [b for b in st.session_state.raw_data if (b.get('booking_date') or b.get('date') or (b.get('start_time')[:10] if b.get('start_time') else '')) == selected_str]
        
        if day_bookings:
            # בדיקה מי כבר בפנים
            res_a = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
            active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_bookings:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or 'לקוח'
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
                        requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_headers(M_KEY))
                        st.rerun()
        else:
            st.info(f"לא נמצאו הזמנות ליום {selected_str}. נסי לבדוק תאריך אחר.")
    else:
        st.info("לחצי על סנכרון.")

with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True, key="v_mode")
    @st.fragment(run_every=5)
    def active_ui():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
        if res.status_code == 200:
            rooms = res.json()
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                # מציג רק מה ששייך ליום הנבחר (או אתמול בלילה אם השעה מוקדמת)
                if s_dt.date() == view_date or (get_now().hour < 6 and s_dt.date() == view_date - timedelta(days=1)):
                    diff = get_now() - s_dt if r.get('status') != 'finished' else (datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ) - s_dt)
                    st.subheader(f"📍 {r['room_name']} | {r['name']}")
                    if r.get('status').startswith('active'):
                        pay = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                        tot, per = calculate_price(r['total_people'], pay, diff.total_seconds()/60)
                        st.write(f"⏱️ **{format_duration(diff.total_seconds())}**")
                        st.write(f"💰 סה\"כ: ₪{tot:.2f} | 👤 לאדם: ₪{per:.2f}")
                        if st.button(f"💰 סיום", key=f"e_{r['id']}", use_container_width=True):
                            requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished", "end_time":get_now().isoformat(), "paying_people":pay}, headers=get_headers(M_KEY))
                            st.rerun()
                    st.divider()
    active_ui()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("איש", 1, 50, 4, key="c1"), c2.number_input("משלמים", 1, 50, 4, key="c2"), c3.number_input("דקות", 1, 600, 60, key="c3")
    t, p = calculate_price(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    st.metric("לאדם", f"₪{p:.2f}")
