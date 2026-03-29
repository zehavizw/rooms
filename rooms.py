import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- 1. חיבורים (מושך מה-Secrets שעדכנת) ---
S_URL = st.secrets['SUPABASE_URL']
S_KEY = st.secrets['SUPABASE_KEY']
M_URL = st.secrets['MY_URL']
M_KEY = st.secrets['MY_KEY']
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

# --- 2. פונקציות ליבה (עוקף את בעיית הרפרש) ---
def get_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def sync_data():
    """מושך 50 הזמנות אחרונות ישירות עם המפתח הקבוע"""
    url = f"{S_URL}/rest/v1/bookings?select=*,room:rooms(*)&order=created_at.desc&limit=50"
    res = requests.get(url, headers=get_headers(S_KEY), timeout=10)
    if res.status_code == 200:
        return res.json()
    st.error(f"שגיאת חיבור למקור: {res.status_code}")
    return []

# --- 3. ממשק משתמש ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - גרסה יציבה")

view_date = st.date_input("📅 בחר תאריך להצגה:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים מהענן", use_container_width=True):
    with st.spinner("מעדכן..."):
        st.session_state.raw_data = sync_data()
        if st.session_state.raw_data:
            st.success(f"הסנכרון הצליח! נסרקו {len(st.session_state.raw_data)} הזמנות.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'raw_data' in st.session_state:
        # סינון מקומי לפי התאריך שנבחר
        day_list = [b for b in st.session_state.raw_data if (b.get('booking_date') or (b.get('start_time')[:10] if b.get('start_time') else '')) == selected_str]
        
        if day_list:
            # בדיקה מי כבר נמצא ב-Database הפרטי שלך
            res_a = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
            active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_list:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or 'לקוח'
                start = b.get('start_time', '--:--')
                if 'T' in start: start = start.split('T')[1][:5]
                
                with st.expander(f"⏳ {name} | {start}"):
                    r_name = b.get('room', {}).get('name') or 'חדר'
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        # שמירה במסד שלך - עכשיו יעבוד כי MY_KEY הוא Secret
                        payload = {
                            "booking_id": bid, 
                            "name": name, 
                            "room_name": r_name, 
                            "start_time": get_now().isoformat(), 
                            "status": "active",
                            "total_people": b.get('total_people', 2),
                            "paying_people": b.get('total_people', 2)
                        }
                        requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_headers(M_KEY))
                        st.rerun()
        else:
            st.info(f"לא נמצאו הזמנות ליום {selected_str}. (נסי לבדוק תאריך סמוך)")
    else:
        st.info("לחצי על סנכרון.")

with tab2:
    v_mode = st.radio("תצוגה:", ["⚡ פעילים", "🏁 סיימו"], horizontal=True)
    @st.fragment(run_every=5)
    def timer():
        res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
        if res.status_code == 200:
            rooms = res.json()
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v_mode == "⚡ פעילים" else [r for r in rooms if r.get('status') == 'finished']
            for r in disp:
                st.subheader(f"📍 {r['room_name']} | {r['name']}")
                if r.get('status') == 'active':
                    if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished", "end_time":get_now().isoformat()}, headers=get_headers(M_KEY))
                        st.rerun()
                st.divider()
    timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c_tot = st.number_input("כמות אנשים", 1, 50, 4)
    st.metric("סה\"כ (לפי 45 שח)", f"₪{c_tot * 45}")
